# 08 — LaunchAgent Setup (macOS daily refresh)

This sets up the macOS scheduler to run `morning_pipeline.sh` once per day. Linux equivalent at the bottom.

## What gets scheduled

The original site runs 6 LaunchAgents across different times. For a fresh deployment, you only need **one** that runs `morning_pipeline.sh` once a day — the script orchestrates all the fetchers in sequence.

## The plist file

Create `~/Library/LaunchAgents/com.<your-project>.daily.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.tisi.intel.daily</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-c</string>
    <string>cd /Users/YOU/code/tisi-intel && PROJECT_ROOT=$(pwd) bash morning_pipeline.sh >> logs/daily.log 2>&1</string>
  </array>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>5</integer>
    <key>Minute</key>
    <integer>30</integer>
  </dict>

  <key>StandardOutPath</key>
  <string>/Users/YOU/code/tisi-intel/logs/daily.stdout.log</string>

  <key>StandardErrorPath</key>
  <string>/Users/YOU/code/tisi-intel/logs/daily.stderr.log</string>

  <key>RunAtLoad</key>
  <false/>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
  </dict>
</dict>
</plist>
```

Replace `/Users/YOU/code/tisi-intel` with the actual project path.

## Loading the agent

```bash
launchctl load ~/Library/LaunchAgents/com.tisi.intel.daily.plist
launchctl list | grep tisi
```

The second command should show the agent loaded with PID `-` (idle, will fire at scheduled time).

## Testing

Force an immediate run:

```bash
launchctl start com.tisi.intel.daily
tail -f ~/code/tisi-intel/logs/daily.log
```

If it doesn't fire, check:

- `launchctl list | grep tisi` — agent is loaded
- The script is executable: `chmod +x morning_pipeline.sh`
- `PROJECT_ROOT` is set correctly inside the script
- macOS Full Disk Access granted to `/bin/bash` (System Settings → Privacy & Security)

## Reloading after changes

```bash
launchctl unload ~/Library/LaunchAgents/com.tisi.intel.daily.plist
launchctl load   ~/Library/LaunchAgents/com.tisi.intel.daily.plist
```

## Multiple staggered agents (advanced)

The original site splits the pipeline across 6 agents to avoid one long blocking run. Example schedule:

| Time (ET) | Job |
|---|---|
| 6:12 AM | OSHA data |
| 6:30 AM | IR data |
| 7:30 AM | News collector (morning) |
| 7:35 AM | Dashboard refresh |
| 11:30 PM | News collector (evening) |
| 12:30 AM | Government data |

For a fresh deployment, **don't bother** unless you hit a real problem with the single-agent approach. One job at 5:30 AM that runs everything is simpler to debug.

## Email-on-failure

`morning_pipeline.sh` already includes:

```bash
trap notify_failure EXIT
```

`notify_failure` calls `_shared/pipeline_notify.py`, which reads `.env` for `RESEND_API_KEY` and emails the admin. This means a silent failure becomes an immediately-visible email.

**Do not remove this trap.** Success-path-only notifications miss silent fails — which is the most dangerous failure mode for a daily cron.

## Logs

Logs go to `logs/daily.log` (combined stdout+stderr from the script) and `logs/daily.stdout.log` / `daily.stderr.log` (separated by macOS launchd). Rotate manually or with `logrotate` if they grow large.

## Linux equivalent

If running on Linux instead, use cron:

```bash
crontab -e
```

Add:

```cron
30 5 * * * cd /home/USER/code/tisi-intel && PROJECT_ROOT=$(pwd) PYTHONUNBUFFERED=1 bash morning_pipeline.sh >> logs/daily.log 2>&1
```

Make sure the shell can find `python3`, `node`, and `git` — cron has a minimal PATH by default.

## Verifying the schedule

After loading, the next morning, check:

- `logs/daily.log` was updated around the scheduled time
- `Dashboard/market_data.json` has today's date
- Live site shows fresh data

If any of those fail: read the log, fix the issue, reload the agent.
