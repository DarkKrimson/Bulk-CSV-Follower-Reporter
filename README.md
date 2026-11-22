# Bulk CSV Follower Reporter
![License](https://img.shields.io/badge/License-GPLv3-blue.svg)

A Windows tool for tracking Twitch followers over time.

![alt text](https://github.com/DarkKrimson/Bulk-CSV-Follower-Reporter/blob/master/Program_Preview.PNG "Bulk CSV Follower Reporter.exe")

**Bulk CSV Follower Reporter**: can quickly analyze many follower list .CSV files exported using https://twitch-tools.rootonline.de/followerlist_viewer.php. It will create lists of who unfollowed, re-followed, changed their username, and more.

You will need to save a few of these over time to capture enough data to see changes so by getting your initial .CSV today and then wait some time and grab another .CSV file to see results. It's good practice to remember to save your follower .CSV weekly, monthly, or yearly to get the full benefit of this program. The more .CSV files you have, the better the results will be

If you want to start using the program today, you can try the compare function. It can compare two different channels to find the follower overlap or followers in common.

Now you and your homie can answer the question, how many followers do we have in common?

---

## What is in the project

```
followers_gui.py        Window app (tkinter). Start here.
followers_report.py     Report engine. Used by the window and by the command-line mode.
twitch_lookup.py        Twitch API client for looking up user IDs.
config.ini              Twitch Client ID and Secret (the window app can create it).
```

Keep these files in the same folder.

---

## Requirements

- Windows 10 or 11
- Python 3.10 or newer from python.org. During install, tick **"Add python.exe to PATH."**
- For the Twitch lookup only: a Twitch developer application (Client ID and Client Secret). Create one at https://dev.twitch.tv/console/apps. If you generate a new secret, the old one stops working.

---

## Building the Windows executable.

1. Put `followers_gui.py`, `followers_report.py`, and `twitch_lookup.py` in one folder, for example `C:\BulkCSVReporter`.
2. Open Command Prompt in that folder: click the address bar in Explorer, type `cmd`, and press Enter.
3. Install PyInstaller:

   ```
   python -m pip install --upgrade pyinstaller
   ```

4. Build the app:

   ```
   python -m PyInstaller --onefile --windowed --name BulkCSVFollowerReporter followers_gui.py
   ```

5. When the command finishes, the app is at `dist\BulkCSVFollowerReporter.exe`.

If you use the Twitch lookup, put `config.ini` in the `dist` folder next to the exe. You can also create it from inside the app (see below).

**Common fixes:**

- **"python is not recognized":** reinstall Python with "Add to PATH" ticked, or use `py` in place of `python` in each command.
- **"No module named PyInstaller" after step 3:** run step 3 again and check that it finished without errors.
- **Build errors mentioning a missing file:** make sure all three Python files are in the folder you're in.

### Optional: command-line version

To build the console version, run this in the same folder:

```
python -m PyInstaller --onefile --console --name followers_report followers_report.py
```

The exe is at `dist\followers_report.exe`. Drag CSV files or a folder onto it, or run it and type paths when asked.

---

## Using the program

Double-click `BulkCSVFollowerReporter.exe`. The window has two areas.

### Follower report (top box)

- **Browse...** picks the folder that holds your CSV exports. The window shows how many CSV files it found.
- **Twitch lookup (optional)** adds current Twitch usernames to the output. Tick **Look up current usernames on Twitch**, enter your Client ID and Client Secret, and click **Save to config.ini**. The file is saved next to the exe, so you won't have to enter them again. **Show** reveals the secret.
- **Run report** builds the report. **Open report folder** opens the result when it's done.

### Extra: compare two channels (below the divider)

This is a separate tool. Browse to a CSV for Channel 1 and one for Channel 2, then click **Find accounts following both**.

### Log

The bottom box shows progress and any errors.

Both tools write their results to a new folder next to the first CSV they read. The folder name shows the date and time.

---

## Using the follower report

Put all your exports for one channel in one folder, then click **Run report**. You can add exports from any date. Accounts are compared by **user ID**, which doesn't change when someone renames their account.

The report folder contains:

| File | What it shows |
| --- | --- |
| `report.txt` | Summary of everything below. |
| `unfollowed_now.csv` | Accounts seen in an earlier export that aren't in the latest one. Shows the name they had before leaving. |
| `returned_followers.csv` | Accounts that left at some point and then came back. Shows the name before leaving and the name now. |
| `changed_username.csv` | Accounts that changed their username between exports. Sorted by current name. |
| `bots.csv` | Accounts that are flagged as known bots by CommanderRoot. |
| `affiliates.csv` | Every Twitch Affiliate account seen, and whether it still follows. |
| `partners.csv` | Every Twitch Partner account seen, and whether it still follows. |
| `fast_follows.csv` | Accounts that followed within 10 minutes of creating their account. |
| `current_names.csv` | Only if the Twitch lookup ran. The current name for every account and all their past username changes. |
| `timeline.csv` | Follower counts and changes for each export. |

**Sorting:** in most files follow a group hierarchy of these criteria:

1. "not found on Twitch" (the account was deleted or suspended)
2. "not in latest export" (not following as of your newest CSV)
3. "following"

Each group is then sorted A-Z by current username (if the Twitch lookup ran) and if not, the username from the .CSV export will be used.

Usernames missing from your .CSV export may have unfollowed, been banned, deleted their account, changed this username, or you removed them as a follower using https://twitch-tools.rootonline.de/follower_remover.php. It is difficult to know but with this tool we can see if accounts are still intact or suspended/banned. The tool also uses user ID's to avoid considering a follower who changed their username as an unfollow. Changing your username, doesn't change your ID. It's static and never changes. This give us confirmation that user is either following but by a different name, or they did in fact unfollow.

---

## Comparing two channels

Use this to find accounts that follow both of your channels.

1. Browse to a CSV for Channel 1 and one for Channel 2.
2. Click **Find accounts following both**.

The output folder contains:

- `both_channels.csv`: every account following both channels, with its name and follow date on each.
- `compare_report.txt`: the counts. It shows how many follow both, how many follow only one, and the overlap percentage.

Channel names come from the file names. If a file name doesn't use the `followerlist_<channel>__<date>.csv` format, the file name is used instead.

---

## The Twitch lookup

The lookup uses the Twitch API to look up user IDs to find the current username. This is optional step but recommended for the best results.

How to get your Client ID and Secret ID:

1. Create an application at https://dev.twitch.tv/console/apps

   ```
   Name: This can be anything you want
   OAuth Redirect URLs: This isn't important either. It can be left as http://localhost
   Category: Analytic Tools
   Client Type: Confidential
   
2. In the Windows app, tick **Look up current usernames on Twitch**, copy & paste both the Client ID and Secret ID, and click **Save to config.ini**.

NOTE: Config.ini will be be saved in the same directory as your .exe. Keep it private, and don't share it or zip it with the exe.
Anyone with the Client ID and Secret ID can use them to run other unrelated programs on your behalf.

If the lookup can't run, the report will still finish. The log and summary will say why, for example "config.ini still has the placeholder values."

---

## Troubleshooting

| Problem | What to do |
| --- | --- |
| Window doesn't open after building | Check the build output for errors, then rebuild. |
| "No CSV files in that folder" | Make sure the exports end in `.csv` and are in the folder you picked. |
| Lookup says "placeholder values" | Replace the placeholders in `config.ini`, or enter the credentials and click **Save to config.ini**. |
| Lookup fails with an authorization error | The Client ID or Secret is wrong. Generate a new secret and save it. |
| Many accounts "not found on Twitch" | They were probably deleted or suspended. This is expected for old exports. |

---

## Privacy and safety

- `config.ini` holds your Twitch Client ID and Secret ID. Keep it private!

---

## Disclaimer

This project is not affiliated with, endorsed by, or sponsored by CommanderRoot or the Twitch Tools website (https://twitch-tools.rootonline.de/). The follower CSV files this tool reads come from that third-party site's "Export all as CSV" feature. Use of that site is subject to its own terms, and you are responsible for complying with them. This project is also not affiliated with or endorsed by Twitch Interactive, Inc.
