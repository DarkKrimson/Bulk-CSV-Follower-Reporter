#!/usr/bin/env python3

import configparser
import csv
import datetime as dt
import os
import re
import sys

try:
    from twitch_lookup import TwitchClient
except ImportError:  # lookup is optional; the report still works without it
    TwitchClient = None

FAST_FOLLOW_SECONDS = 10 * 60
NAME_RE = re.compile(r"(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})")
DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")
CAVEAT = (
    "An ID that is missing from a later export may have unfollowed you, or the "
    "account may have been banned or deleted. The exports do not say which."
)


def parse_dt(text):
    text = (text or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def snapshot_time(path):
    m = NAME_RE.search(os.path.basename(path))
    if m:
        try:
            return dt.datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H-%M-%S")
        except ValueError:
            pass
    return dt.datetime.fromtimestamp(os.path.getmtime(path))


def collect_files(args):
    files = []
    for a in args:
        a = a.strip().strip('"')
        if not a:
            continue
        if os.path.isdir(a):
            for name in sorted(os.listdir(a)):
                if name.lower().endswith(".csv"):
                    files.append(os.path.join(a, name))
        elif os.path.isfile(a) and a.lower().endswith(".csv"):
            files.append(a)
        else:
            print(f"Skipping (not a CSV or folder): {a}")
    seen, out = set(), []
    for f in files:
        key = os.path.abspath(f).lower()
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def load_snapshot(path):
    users = {}
    skipped = 0
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            uid = (row.get("userID") or "").strip()
            if not uid:
                skipped += 1
                continue
            if uid not in users:
                row = dict(row)
                row["userName"] = (row.get("userName") or "").strip().lstrip("@")
                users[uid] = row
    return snapshot_time(path), users, skipped


def app_folder():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def config_path():
    return os.path.join(app_folder(), "config.ini")


def read_saved_credentials():
    path = config_path()
    if not os.path.exists(path):
        return "", ""
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    return (parser.get("twitch", "client_id", fallback="").strip(),
            parser.get("twitch", "client_secret", fallback="").strip())


def save_config(client_id, client_secret):
    parser = configparser.ConfigParser(interpolation=None)
    parser["twitch"] = {"client_id": client_id.strip(), "client_secret": client_secret.strip()}
    with open(config_path(), "w", encoding="utf-8") as fh:
        parser.write(fh)
    return config_path()


def is_placeholder(value):
    return not value or value.upper().startswith("PASTE_")


def load_twitch_client():
    if TwitchClient is None:
        return None, "twitch_lookup.py is missing from the program folder"
    if not os.path.exists(config_path()):
        return None, "no config.ini next to the program"
    client_id, client_secret = read_saved_credentials()
    if is_placeholder(client_id) or is_placeholder(client_secret):
        return None, "config.ini is missing the Client ID or Secret"
    return TwitchClient(client_id, client_secret), ""


def fetch_current_names(client, uids):
    users = client.get_users_by_ids(sorted(uids, key=ukey))
    return {u["id"]: u for u in users}


def ask_yes_no(question, default):
    if not (sys.stdin.isatty() or getattr(sys, "frozen", False)):
        return default
    try:
        answer = input(question).strip().lower()
    except EOFError:
        return default
    if not answer:
        return default
    return answer.startswith("y")


def write_csv(path, header, rows, current=None):
    if current is not None:
        header = list(header) + ["current_username_on_twitch"]
        rows = [list(r) + [current.get(r[0], "not found on Twitch")] for r in rows]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def ukey(uid):
    return (0, int(uid), "") if uid.isdigit() else (1, 0, uid)


def is_flag(value, wanted):
    return (value or "").strip().lower() == wanted


def sort_for_reading(rows, status_index, name_of):
    def key(r):
        following = status_index is not None and r[status_index] == "following"
        return (1 if following else 0, name_of(r[0]))
    return sorted(rows, key=key)


def pause():
    if sys.stdin.isatty() or getattr(sys, "frozen", False):
        input("Press Enter to close...")


def generate(files, lookup, log=print, given_client=None):
    snaps = sorted((load_snapshot(f) for f in files), key=lambda s: s[0])
    times = [s[0] for s in snaps]
    maps = [s[1] for s in snaps]
    skipped = [s[2] for s in snaps]
    labels = [t.strftime("%Y-%m-%d %H:%M:%S") for t in times]
    latest = maps[-1]
    latest_label = labels[-1]

    # Every snapshot index where each userID appears
    appearances = {}
    for i, users in enumerate(maps):
        for uid in users:
            appearances.setdefault(uid, []).append(i)

    def names_seen(uid):
        out = []
        for i in appearances[uid]:
            n = maps[i][uid]["userName"]
            if n not in out:
                out.append(n)
        return " > ".join(out)

    def status_now(uid):
        return "following" if uid in latest else "not in latest export"

    # ---- Returned followers: in an export, absent later, then back again ----
    returned_rows = []
    for uid in sorted(appearances, key=ukey):
        idxs = appearances[uid]
        gaps = [(a, b) for a, b in zip(idxs, idxs[1:]) if b - a > 1]
        if not gaps:
            continue
        left_at, back_at = gaps[0]
        returned_rows.append([uid, maps[left_at][uid]["userName"], maps[idxs[-1]][uid]["userName"],
                              labels[left_at], labels[back_at], len(gaps), status_now(uid)])

    # ---- Not in the latest export, but seen in an earlier one --------------
    unfollowed_rows = []
    for uid in sorted(appearances, key=ukey):
        if uid in latest:
            continue
        idxs = appearances[uid]
        first, last = idxs[0], idxs[-1]
        r = maps[last][uid]
        unfollowed_rows.append([uid, maps[first][uid]["userName"], r["userName"],
                                labels[first], labels[last],
                                r.get("followCreatedAt", ""), r.get("accCreatedAt", ""),
                                r.get("broadcasterType", ""), r.get("isKnownBot", "")])

    # ---- Username changes (same ID, different name) -------------------------
    rename_rows = []
    for uid in sorted(appearances, key=ukey):
        idxs = appearances[uid]
        for a, b in zip(idxs, idxs[1:]):
            old = maps[a][uid]["userName"]
            new = maps[b][uid]["userName"]
            if old.lower() != new.lower():
                rename_rows.append([uid, old, new, labels[a], labels[b]])
    renamed_ids = {r[0] for r in rename_rows}

    # ---- Bots ---------------------------------------------------------------
    bot_rows = []
    for uid in sorted(appearances, key=ukey):
        idxs = [i for i in appearances[uid] if is_flag(maps[i][uid].get("isKnownBot"), "yes")]
        if idxs:
            bot_rows.append([uid, names_seen(uid), labels[idxs[0]], labels[idxs[-1]],
                             len(idxs), status_now(uid)])

    # ---- Affiliates and partners ---------------------------------------------
    def type_list(kind):
        rows = []
        for uid in sorted(appearances, key=ukey):
            idxs = [i for i in appearances[uid]
                    if is_flag(maps[i][uid].get("broadcasterType"), kind)]
            if not idxs:
                continue
            r = maps[idxs[-1]][uid]
            rows.append([uid, names_seen(uid), labels[idxs[0]], labels[idxs[-1]],
                         status_now(uid), r.get("followCreatedAt", ""), r.get("accCreatedAt", "")])
        return rows

    affiliate_rows = type_list("affiliate")
    partner_rows = type_list("partner")

    # ---- Followed within 10 minutes of account creation ----------------------
    fast_rows = []
    seen_fast = set()
    for users in maps:
        for uid, r in users.items():
            if uid in seen_fast:
                continue
            created = parse_dt(r.get("accCreatedAt"))
            followed = parse_dt(r.get("followCreatedAt"))
            if not created or not followed:
                continue
            delta = (followed - created).total_seconds()
            if 0 <= delta <= FAST_FOLLOW_SECONDS:
                seen_fast.add(uid)
                fast_rows.append([uid, names_seen(uid), r.get("accCreatedAt", ""),
                                  r.get("followCreatedAt", ""), int(delta), status_now(uid)])
    fast_rows.sort(key=lambda x: x[4])

    # ---- Timeline -----------------------------------------------------------
    timeline_rows = []
    for i, users in enumerate(maps):
        bots = sum(1 for r in users.values() if is_flag(r.get("isKnownBot"), "yes"))
        aff = sum(1 for r in users.values() if is_flag(r.get("broadcasterType"), "affiliate"))
        par = sum(1 for r in users.values() if is_flag(r.get("broadcasterType"), "partner"))
        if i == 0:
            timeline_rows.append([labels[i], len(users), "", "", "", bots, aff, par, skipped[i]])
            continue
        prev = maps[i - 1]
        new_ids = len(set(users) - set(prev))
        gone_ids = len(set(prev) - set(users))
        renamed = sum(1 for uid in set(users) & set(prev)
                      if prev[uid]["userName"].lower() != users[uid]["userName"].lower())
        timeline_rows.append([labels[i], len(users), new_ids, gone_ids, renamed,
                              bots, aff, par, skipped[i]])

    # ---- Optional Twitch lookup: current username for every ID ---------------
    uids = sorted(appearances, key=ukey)
    current_map = None
    lookup_users = {}
    lookup_text = "Not run."
    if not lookup:
        client, why = None, "not selected"
    elif given_client is not None:
        client, why = given_client, ""
    else:
        client, why = load_twitch_client()
    if client is None:
        lookup_text = f"Not run: {why}."
        if lookup:
            log(f"Twitch lookup skipped: {why}")
    else:
        try:
            lookup_users = fetch_current_names(client, [u for u in uids if u.isdigit()])
            current_map = {uid: (lookup_users[uid].get("login", "") if uid in lookup_users
                                 else "not found on Twitch") for uid in uids}
            found = sum(1 for uid in uids if uid in lookup_users)
            lookup_text = (f"Looked up {len(uids)} IDs: {found} found, "
                           f"{len(uids) - found} not found on Twitch (deleted or suspended).")
        except Exception as e:
            lookup_text = f"Failed: {e}"
            log(f"Twitch lookup failed: {e}")

    def reading_name(uid):
        current = current_map.get(uid) if current_map else None
        if current and current != "not found on Twitch":
            return current.lower()
        return names_seen(uid).split(" > ")[0].lower()

    def csv_out(path, header, rows):
        write_csv(path, header, rows, current_map)

    # ---- Output folder and CSV files ----------------------------------------
    out_dir = os.path.join(os.path.dirname(os.path.abspath(files[0])),
                           "bulk_csv_report_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out_dir, exist_ok=True)

    csv_out(os.path.join(out_dir, "unfollowed_now.csv"),
              ["userID", "username_first_seen", "username_before_leaving", "first_seen_in",
               "last_seen_in", "followCreatedAt", "accCreatedAt", "broadcasterType", "isKnownBot"],
              sort_for_reading(unfollowed_rows, None, reading_name))
    csv_out(os.path.join(out_dir, "returned_followers.csv"),
              ["userID", "username_before_leaving", "username_now_in_exports",
               "last_seen_before_leaving", "returned_in", "times_left", "status_now"],
              sort_for_reading(returned_rows, 6, reading_name))
    def changed_name_order(r):
        current = current_map.get(r[0]) if current_map else None
        if current and current != "not found on Twitch":
            return current.lower()
        return r[2].lower()

    csv_out(os.path.join(out_dir, "changed_username.csv"),
              ["userID", "username_before", "username_after", "last_seen_with_old_name",
               "first_seen_with_new_name"], sorted(rename_rows, key=changed_name_order))
    csv_out(os.path.join(out_dir, "bots.csv"),
              ["userID", "usernames", "first_seen", "last_seen", "snapshot_count", "status_now"],
              sort_for_reading(bot_rows, 5, reading_name))
    csv_out(os.path.join(out_dir, "affiliates.csv"),
              ["userID", "usernames", "first_seen", "last_seen", "status_now",
               "followCreatedAt", "accCreatedAt"], sort_for_reading(affiliate_rows, 4, reading_name))
    csv_out(os.path.join(out_dir, "partners.csv"),
              ["userID", "usernames", "first_seen", "last_seen", "status_now",
               "followCreatedAt", "accCreatedAt"], sort_for_reading(partner_rows, 4, reading_name))
    csv_out(os.path.join(out_dir, "fast_follows.csv"),
              ["userID", "usernames", "accCreatedAt", "followCreatedAt",
               "seconds_after_creation", "status_now"], sort_for_reading(fast_rows, 5, reading_name))
    if current_map is not None:
        current_rows = []
        for uid in uids:
            u = lookup_users.get(uid, {})
            current_rows.append([uid, current_map[uid], u.get("display_name", ""), status_now(uid),
                                 labels[appearances[uid][0]], labels[appearances[uid][-1]], names_seen(uid)])
        def current_names_order(r):
            # Group 0: not found on Twitch. Group 1: not in latest export. Group 2: following.
            if r[1] == "not found on Twitch":
                group, name = 0, r[6].split(" > ")[0]
            elif r[3] == "not in latest export":
                group, name = 1, r[1]
            else:
                group, name = 2, r[1]
            return (group, name.lower())
        current_rows.sort(key=current_names_order)
        write_csv(os.path.join(out_dir, "current_names.csv"),
                  ["userID", "current_username", "display_name", "status_now", "first_seen",
                   "last_seen", "usernames_in_exports"], current_rows)
    write_csv(os.path.join(out_dir, "timeline.csv"),
              ["snapshot", "followers", "new_ids_since_previous", "missing_ids_since_previous",
               "renamed_since_previous", "bots", "affiliates", "partners", "rows_skipped_no_id"],
              timeline_rows)

    # ---- Summary ------------------------------------------------------------
    lines = []
    add = lines.append
    add("BULK CSV FOLLOWER REPORTER (matched by userID)")
    add("=" * 60)
    add(f"Snapshots compared: {len(snaps)}")
    for label, users, skip in zip(labels, maps, skipped):
        extra = f"  ({skip} rows without a userID skipped)" if skip else ""
        add(f"  {label}  ({len(users)} accounts){extra}")
    add("")
    add("UNFOLLOWED AT SOME POINT, NOT IN LATEST EXPORT")
    add("-" * 60)
    add(f"Latest export: {latest_label}")
    add(f"Accounts seen earlier that are not in the latest export: {len(unfollowed_rows)}")
    add("Details: unfollowed_now.csv (shows the username before leaving)")
    add("")
    add("RETURNED FOLLOWERS (left at some point, then came back)")
    add("-" * 60)
    add(f"Accounts that left and came back: {len(returned_rows)}")
    add(f"Of those, still following: {sum(1 for r in returned_rows if r[6] == 'following')}")
    add("Details: returned_followers.csv (username before leaving and after returning)")
    add("")
    add("USERNAME CHANGES")
    add("-" * 60)
    add(f"Username change events: {len(rename_rows)}")
    add(f"Unique accounts that changed username: {len(renamed_ids)}")
    add("Details: changed_username.csv (username before and after)")
    add("")
    add("CURRENT USERNAMES (Twitch lookup)")
    add("-" * 60)
    add(lookup_text)
    if current_map is not None:
        add("Details: current_names.csv, plus a current_username_on_twitch column in the other CSVs")
    add("")
    add("BOT FOLLOWS (isKnownBot = Yes)")
    add("-" * 60)
    add(f"Unique accounts ever flagged as bots: {len(bot_rows)}")
    last_bots = sum(1 for r in latest.values() if is_flag(r.get("isKnownBot"), "yes"))
    add(f"Flagged as bots in the latest export: {last_bots} of {len(latest)} "
        f"({100 * last_bots / max(len(latest), 1):.1f}%)")
    add("Details: bots.csv")
    add("")
    add("AFFILIATES")
    add("-" * 60)
    add(f"Unique affiliate accounts ever seen: {len(affiliate_rows)}")
    add(f"Affiliates still following: {sum(1 for r in affiliate_rows if r[4] == 'following')}")
    add("Details: affiliates.csv")
    add("")
    add("PARTNERS")
    add("-" * 60)
    add(f"Unique partner accounts ever seen: {len(partner_rows)}")
    add(f"Partners still following: {sum(1 for r in partner_rows if r[4] == 'following')}")
    add("Details: partners.csv")
    add("")
    add("FAST FOLLOWS (followed within 10 minutes of account creation)")
    add("-" * 60)
    add(f"Unique accounts: {len(fast_rows)}")
    add("Details: fast_follows.csv")
    add("")
    add("TIMELINE")
    add("-" * 60)
    for row in timeline_rows:
        add(f"  {row[0]}: {row[1]} accounts, +{row[2] or 0} new IDs, -{row[3] or 0} missing IDs, "
            f"{row[4] or 0} renamed, {row[5]} bots, {row[6]} affiliates, {row[7]} partners")
    add("Details: timeline.csv")

    text = "\n".join(lines) + "\n"
    with open(os.path.join(out_dir, "report.txt"), "w", encoding="utf-8") as fh:
        fh.write(text)
    log(text)
    log(f"Report saved to: {out_dir}")
    return out_dir


def channel_label(path):
    m = re.search(r"followerlist_(.+?)__", os.path.basename(path))
    return m.group(1) if m else os.path.splitext(os.path.basename(path))[0]


def compare_channels(path_a, path_b, log=print):
    _, users_a, skip_a = load_snapshot(path_a)
    _, users_b, skip_b = load_snapshot(path_b)
    la, lb = channel_label(path_a), channel_label(path_b)
    if la == lb:
        la, lb = la + "_1", lb + "_2"

    both = set(users_a) & set(users_b)
    only_a = set(users_a) - set(users_b)
    only_b = set(users_b) - set(users_a)

    rows = []
    for uid in sorted(both, key=ukey):
        ra, rb = users_a[uid], users_b[uid]
        rows.append([uid, ra["userName"], rb["userName"],
                     ra.get("followCreatedAt", ""), rb.get("followCreatedAt", "")])
    rows.sort(key=lambda r: (r[1].lower(), r[0]))

    out_dir = os.path.join(os.path.dirname(os.path.abspath(path_a)),
                           "channel_compare_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out_dir, exist_ok=True)
    write_csv(os.path.join(out_dir, "both_channels.csv"),
              ["userID", f"username_{la}", f"username_{lb}",
               f"followed_{la}_at", f"followed_{lb}_at"], rows)

    pct_a = 100 * len(both) / max(len(users_a), 1)
    pct_b = 100 * len(both) / max(len(users_b), 1)
    lines = [
        "BULK CSV FOLLOWER REPORTER - CHANNEL COMPARE (matched by userID)",
        "=" * 60,
        f"Channel 1: {la}  ({len(users_a)} followers, file: {os.path.basename(path_a)})",
        f"Channel 2: {lb}  ({len(users_b)} followers, file: {os.path.basename(path_b)})",
        "",
        f"Follow both channels: {len(both)}",
        f"Only {la}: {len(only_a)}",
        f"Only {lb}: {len(only_b)}",
        f"Overlap: {pct_a:.1f}% of {la}, {pct_b:.1f}% of {lb}",
    ]
    if skip_a or skip_b:
        lines.append(f"Rows skipped (no userID): {la} {skip_a}, {lb} {skip_b}")
    lines += ["", "Details: both_channels.csv (sorted by name)"]
    text = "\n".join(lines) + "\n"
    with open(os.path.join(out_dir, "compare_report.txt"), "w", encoding="utf-8") as fh:
        fh.write(text)
    log(text)
    log(f"Saved to: {out_dir}")
    return out_dir


def main():
    args = sys.argv[1:]
    if not args:
        print("Drop CSV files or a folder here, or type paths separated by ';'.")
        args = input("Paths: ").split(";")
    files = collect_files(args)
    if not files:
        print("No CSV files found.")
        pause()
        return
    lookup = False
    if load_twitch_client()[0] is not None:
        lookup = ask_yes_no("Look up current usernames on Twitch? [Y/n]: ", True)
    generate(files, lookup, print)
    pause()


if __name__ == "__main__":
    main()
