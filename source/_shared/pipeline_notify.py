#!/usr/bin/env python3
"""
Pipeline Failure Notifier
==========================
Reads a pipeline log file, checks for failures, and sends an alert
email via Resend if any steps failed.

Usage:
  python3 pipeline_notify.py <pipeline_name> <log_file>

Example:
  python3 pipeline_notify.py "Oil & Gas Intel" /path/to/morning_pipeline_2026-03-18.log

Requires .env at ${PROJECT_ROOT}/.env with:
  RESEND_API_KEY=re_...
  ALERT_EMAIL=you@example.com
  ALERT_FROM=Pipeline Alerts <alerts@__PROJECT_DOMAIN__>
"""

import sys
import os
import json
from urllib.request import Request, urlopen
from datetime import datetime
from pathlib import Path

# Load .env from project root
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
UNSUBSCRIBED_FILE = Path(__file__).resolve().parent / "unsubscribed.txt"


def is_unsubscribed(email):
    if not UNSUBSCRIBED_FILE.exists():
        return False
    unsub = {line.strip().lower() for line in UNSUBSCRIBED_FILE.read_text().splitlines() if line.strip()}
    return email.strip().lower() in unsub

def load_env():
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                env[key.strip()] = val.strip()
    return env

def extract_failures(log_path):
    """Pull out lines containing FAILED from the log."""
    failures = []
    try:
        with open(log_path) as f:
            for line in f:
                if "FAILED" in line:
                    failures.append(line.strip())
    except FileNotFoundError:
        failures.append(f"Log file not found: {log_path}")
    return failures

def send_alert(api_key, from_email, to_email, pipeline_name, failures, log_path):
    """Send failure alert via Resend API."""
    failure_items = "".join(
        f'<li style="color:#f44336;margin:4px 0;">{f}</li>' for f in failures
    )
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    log_name = os.path.basename(log_path)

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0f1117;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:600px;margin:0 auto;padding:20px;">
  <div style="background:linear-gradient(135deg,#c62828,#e53935);border-radius:10px;padding:20px 24px;margin-bottom:20px;">
    <div style="font-size:20px;font-weight:700;color:#fff;">Pipeline Alert</div>
    <div style="font-size:13px;color:rgba(255,255,255,0.7);margin-top:4px;">{pipeline_name} &mdash; {date_str}</div>
  </div>
  <div style="background:#1a1d29;border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:20px;margin-bottom:16px;">
    <div style="font-size:14px;font-weight:600;color:#e8eaed;margin-bottom:12px;">Failed Steps</div>
    <ul style="margin:0;padding-left:20px;font-size:13px;">{failure_items}</ul>
  </div>
  <div style="text-align:center;padding:12px 0;color:#666;font-size:11px;border-top:1px solid rgba(255,255,255,0.06);margin-top:16px;">
    <p style="margin:0 0 6px;">Log file: {log_name}</p>
    <a href="https://__PROJECT_DOMAIN__" style="color:#42a5f5;text-decoration:none;">__PROJECT_DOMAIN__</a>
    &nbsp;&nbsp;|&nbsp;&nbsp;
    <span style="color:#555;font-size:10px;">To stop pipeline alerts, add your email to _shared/unsubscribed.txt</span>
  </div>
</div></body></html>"""

    subject = f"Pipeline FAILED: {pipeline_name} ({datetime.now().strftime('%b %d')})"

    payload = json.dumps({
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": html,
    }).encode()

    req = Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "SectorIntel-PipelineNotify/1.0",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            print(f"  Alert sent to {to_email} (id: {result.get('id', '?')})")
    except Exception as e:
        print(f"  Failed to send alert: {e}")


def main():
    if len(sys.argv) < 3:
        print("Usage: pipeline_notify.py <pipeline_name> <log_file>")
        sys.exit(1)

    pipeline_name = sys.argv[1]
    log_path = sys.argv[2]

    failures = extract_failures(log_path)
    if not failures:
        print(f"  No failures detected — no alert sent.")
        return

    env = load_env()
    api_key = env.get("RESEND_API_KEY")
    to_email = env.get("ALERT_EMAIL")
    from_email = env.get("ALERT_FROM", "Pipeline Alerts <alerts@__PROJECT_DOMAIN__>")

    if not api_key or not to_email:
        print(f"  Missing RESEND_API_KEY or ALERT_EMAIL in {ENV_FILE}")
        sys.exit(1)

    if is_unsubscribed(to_email):
        print(f"  {to_email} is unsubscribed — alert suppressed.")
        return

    print(f"  {len(failures)} failure(s) detected — sending alert...")
    send_alert(api_key, from_email, to_email, pipeline_name, failures, log_path)


if __name__ == "__main__":
    main()
