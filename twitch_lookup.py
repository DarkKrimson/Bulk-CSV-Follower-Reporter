#!/usr/bin/env python3

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
API_BASE = "https://api.twitch.tv/helix"
MAX_IDS_PER_REQUEST = 100  # Helix limit for /users


class TwitchError(Exception):
    pass


class TwitchClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._token = None
        self._token_expires_at = 0.0

    def _fetch_token(self) -> None:
        data = urllib.parse.urlencode({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }).encode()
        req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as e:
            raise TwitchError(f"Token request failed ({e.code}): {e.read().decode(errors='replace')}")
        except urllib.error.URLError as e:
            raise TwitchError(f"Network error requesting token: {e.reason}")

        self._token = payload["access_token"]
        # Refresh a minute early to avoid using a token right at expiry.
        self._token_expires_at = time.time() + payload.get("expires_in", 3600) - 60

    def _get_token(self) -> str:
        if not self._token or time.time() >= self._token_expires_at:
            self._fetch_token()
        return self._token

    def get(self, path: str, params: list[tuple[str, str]]) -> dict:
        query = urllib.parse.urlencode(params)
        url = f"{API_BASE}/{path}?{query}"
        req = urllib.request.Request(url, headers={
            "Client-Id": self.client_id,
            "Authorization": f"Bearer {self._get_token()}",
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                # Token may have been revoked; force a refresh once and retry.
                self._token = None
                req.headers["Authorization"] = f"Bearer {self._get_token()}"
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return json.load(resp)
            raise TwitchError(f"API error {e.code} on {path}: {e.read().decode(errors='replace')}")
        except urllib.error.URLError as e:
            raise TwitchError(f"Network error calling {path}: {e.reason}")

    def get_users_by_ids(self, user_ids: list[str]) -> list[dict]:
        users = []
        for i in range(0, len(user_ids), MAX_IDS_PER_REQUEST):
            chunk = user_ids[i:i + MAX_IDS_PER_REQUEST]
            params = [("id", uid) for uid in chunk]
            users.extend(self.get("users", params).get("data", []))
        return users

    def get_live_streams(self, user_ids: list[str]) -> dict[str, dict]:
        live = {}
        for i in range(0, len(user_ids), MAX_IDS_PER_REQUEST):
            chunk = user_ids[i:i + MAX_IDS_PER_REQUEST]
            params = [("user_id", uid) for uid in chunk]
            for stream in self.get("streams", params).get("data", []):
                live[stream["user_id"]] = stream
        return live


def validate_ids(raw_ids: list[str]) -> list[str]:
    cleaned = []
    for raw in raw_ids:
        uid = raw.strip()
        if not uid.isdigit():
            raise ValueError(f"'{raw}' is not a valid numeric Twitch user ID")
        cleaned.append(uid)
    # Preserve order, drop duplicates.
    return list(dict.fromkeys(cleaned))


def format_user(user: dict, stream: dict | None) -> str:
    lines = [
        f"{user.get('display_name', '?')} (@{user.get('login', '?')})",
        f"  ID:           {user.get('id')}",
        f"  Type:         {user.get('type') or 'normal'}",
        f"  Broadcaster:  {user.get('broadcaster_type') or 'none'}",
        f"  Created:      {user.get('created_at', '?')}",
        f"  Channel URL:  https://www.twitch.tv/{user.get('login', '')}",
    ]
    if user.get("description"):
        lines.append(f"  Description:  {user['description']}")
    if stream is not None:
        lines.append(f"  Live now:     yes - \"{stream.get('title', '')}\" "
                     f"({stream.get('viewer_count', 0)} viewers, playing {stream.get('game_name') or 'unknown'})")
    elif stream is None and user.get("_checked_live"):
        lines.append("  Live now:     no")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Look up Twitch accounts/channels by user ID.")
    parser.add_argument("user_ids", nargs="+", help="One or more numeric Twitch user IDs")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of formatted text")
    parser.add_argument("--live", action="store_true", help="Also check whether each channel is live")
    parser.add_argument("--url", action="store_true", help="Print only the channel URL for each ID")
    args = parser.parse_args()

    client_id = os.environ.get("TWITCH_CLIENT_ID")
    client_secret = os.environ.get("TWITCH_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("Error: set TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET environment variables.", file=sys.stderr)
        return 1

    try:
        ids = validate_ids(args.user_ids)
        client = TwitchClient(client_id, client_secret)
        users = client.get_users_by_ids(ids)
        streams = client.get_live_streams([u["id"] for u in users]) if args.live and users else {}
    except (ValueError, TwitchError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    found_ids = {u["id"] for u in users}
    missing = [uid for uid in ids if uid not in found_ids]

    if args.url:
        for user in users:
            print(f"https://www.twitch.tv/{user.get('login', '')}")
        for uid in missing:
            print(f"Not found: {uid}", file=sys.stderr)
        return 0 if users else 1

    if args.json:
        output = {
            "users": users,
            "not_found": missing,
        }
        if args.live:
            output["live_streams"] = streams
        print(json.dumps(output, indent=2))
    else:
        if not users:
            print("No users found for the given IDs.")
        for user in users:
            if args.live:
                user["_checked_live"] = True
            print(format_user(user, streams.get(user["id"])))
            print()
        if missing:
            print("Not found: " + ", ".join(missing))

    return 0


if __name__ == "__main__":
    sys.exit(main())
