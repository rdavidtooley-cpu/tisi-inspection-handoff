#!/usr/bin/env python3
"""
Monthly Koyfin Login Reminder

Sends a short email reminding you to visit app.koyfin.com in Chrome
so the refresh_token cookie stays fresh for automated transcript downloads.

Scheduled via launchd to run on the 15th of each month at 9 AM.
Sends via Mail.app (AppleScript) — no credentials to store.

Usage:
  python3 koyfin_login_reminder.py            # Send the reminder email
  python3 koyfin_login_reminder.py --check    # Preview without sending
"""

import os, sys, json, argparse, subprocess
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(SCRIPT_DIR, "koyfin_token.json")
TO_EMAIL = "__ADMIN_EMAIL__"


def get_token_status():
    """Check current token expiration."""
    if not os.path.exists(TOKEN_FILE):
        return "unknown", 0
    with open(TOKEN_FILE) as f:
        data = json.load(f)
    expires = data.get("expires", "")
    if expires:
        exp_date = datetime.strptime(expires, "%Y-%m-%d")
        days_left = (exp_date - datetime.now()).days
        return expires, days_left
    return "unknown", 0


def send_via_mail_app(to, subject, body):
    """Send email using Mail.app via AppleScript."""
    # Escape special characters for AppleScript
    body_escaped = body.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    subject_escaped = subject.replace("\\", "\\\\").replace('"', '\\"')

    script = f'''
    tell application "Mail"
        set newMessage to make new outgoing message with properties {{subject:"{subject_escaped}", content:"{body_escaped}", visible:false}}
        tell newMessage
            make new to recipient at end of to recipients with properties {{address:"{to}"}}
        end tell
        send newMessage
    end tell
    '''

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=30
    )
    return result.returncode == 0, result.stderr.strip()


def main():
    parser = argparse.ArgumentParser(description="Koyfin login reminder email")
    parser.add_argument("--check", action="store_true", help="Preview without sending")
    args = parser.parse_args()

    expires, days_left = get_token_status()
    now = datetime.now().strftime("%B %d, %Y")

    if days_left > 10:
        urgency = f"Your current token is still good ({days_left} days left, expires {expires}), but logging in now keeps the automation running smoothly."
    elif days_left > 0:
        urgency = f"Your token expires in {days_left} days ({expires}). Please log in soon to avoid a gap in transcript downloads."
    else:
        urgency = f"Your token has EXPIRED (was {expires}). Transcript downloads are paused until you log in."

    subject = f"Koyfin Login Reminder — {datetime.now().strftime('%B %Y')}"
    body = f"""Monthly Koyfin Login Reminder — {now}

{urgency}

What to do:
  1. Open Chrome
  2. Go to app.koyfin.com
  3. Make sure you're logged in (if already logged in, just loading the page is enough)

That's it. The automation extracts the fresh token from Chrome automatically.

This keeps the weekly transcript downloads running for both Inspection Intel and Gaming Intel.

---
Sent automatically by koyfin_login_reminder.py"""

    if args.check:
        print(f"To: {TO_EMAIL}")
        print(f"Subject: {subject}")
        print(f"---")
        print(body)
        print(f"---")
        print(f"(check mode — not sending)")
        return

    print(f"Sending Koyfin login reminder to {TO_EMAIL}...")
    success, err = send_via_mail_app(TO_EMAIL, subject, body)
    if success:
        print(f"  Reminder sent. Token status: {days_left} days left (expires {expires})")
    else:
        print(f"  Failed to send via Mail.app: {err}")
        # Fallback: macOS notification
        print("  Falling back to macOS notification...")
        subprocess.run([
            "osascript", "-e",
            f'display notification "Log into app.koyfin.com in Chrome to keep transcript automation running. Token expires {expires}." with title "Koyfin Login Reminder"'
        ])
        print("  Notification sent.")


if __name__ == "__main__":
    main()
