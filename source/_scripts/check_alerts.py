#!/usr/bin/env python3
"""
Inspection Intel — Daily Alerts
===================================
Runs after the dashboard refresh. Sends an email via Resend when:
  1. Any stock moved >5% today (big movers)
  2. Any new 8-K filing was added today
  3. Any company reports earnings tomorrow

Reads market_data.json from the Dashboard directory.
Reads .env from ${PROJECT_ROOT}/.env for RESEND_API_KEY.

Usage:
  python3 check_alerts.py
  python3 check_alerts.py --dry-run   # Print alerts without emailing
"""

import json
import os
import sys
from datetime import datetime, timedelta, date
from pathlib import Path
from urllib.request import Request, urlopen

# ── Paths (all relative to this script) ──────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parent
DASHBOARD_DIR = PROJECT_DIR / "Dashboard"
MARKET_DATA = DASHBOARD_DIR / "market_data.json"
COMPANY_DIR = PROJECT_DIR / "Companies"
ENV_FILE = PROJECT_DIR.parent / ".env"

# ── Config ───────────────────────────────────────────────────
FROM_EMAIL = "Inspection Intel <__FROM_EMAIL__>"
TO_EMAIL = "__ADMIN_EMAIL__"
BIG_MOVER_THRESHOLD = 5.0  # percent


def load_env():
    """Load .env file from project root."""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                env[key.strip()] = val.strip()
    return env


def load_market_data():
    """Load and return market_data.json as a dict."""
    if not MARKET_DATA.exists():
        print(f"  market_data.json not found at {MARKET_DATA}")
        return {}
    with open(MARKET_DATA) as f:
        return json.load(f)


def check_big_movers(data):
    """Return list of (ticker, company, pct) where |daily_change_pct| > threshold."""
    movers = []
    for ticker, info in data.items():
        pct = info.get("daily_change_pct")
        if pct is not None and abs(pct) > BIG_MOVER_THRESHOLD:
            movers.append((
                ticker,
                info.get("company", info.get("name", ticker)),
                pct,
            ))
    movers.sort(key=lambda x: abs(x[2]), reverse=True)
    return movers


def check_new_8k_filings():
    """Scan Companies/*/*/8-K/ for files modified today."""
    today_str = date.today().isoformat()
    new_filings = []
    if not COMPANY_DIR.exists():
        return new_filings
    for category_dir in COMPANY_DIR.iterdir():
        if not category_dir.is_dir():
            continue
        for company_dir in category_dir.iterdir():
            if not company_dir.is_dir():
                continue
            filing_dir = company_dir / "8-K"
            if not filing_dir.exists():
                continue
            for f in filing_dir.iterdir():
                if not f.is_file():
                    continue
                mod_date = datetime.fromtimestamp(f.stat().st_mtime).date().isoformat()
                if mod_date == today_str:
                    new_filings.append((
                        company_dir.name.replace("_", " "),
                        f.name,
                    ))
    return new_filings


def check_earnings_tomorrow(data):
    """Return list of (ticker, company, date) reporting earnings tomorrow."""
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    upcoming = []
    for ticker, info in data.items():
        earn_date = info.get("next_earnings_date", "")
        if earn_date == tomorrow:
            upcoming.append((
                ticker,
                info.get("company", info.get("name", ticker)),
                earn_date,
            ))
    upcoming.sort(key=lambda x: x[1])
    return upcoming


def build_html(movers, filings, earnings):
    """Build a dark-themed HTML email body."""
    date_str = datetime.now().strftime("%B %d, %Y")
    sections = []

    # ── Big Movers ────────────────────────────────────────────
    if movers:
        rows = ""
        for ticker, company, pct in movers:
            color = "#4caf50" if pct > 0 else "#f44336"
            arrow = "+" if pct > 0 else ""
            rows += (
                f'<tr>'
                f'<td style="padding:6px 12px;color:#e8eaed;font-weight:600;">{ticker}</td>'
                f'<td style="padding:6px 12px;color:#9aa0a6;">{company}</td>'
                f'<td style="padding:6px 12px;color:{color};font-weight:600;text-align:right;">{arrow}{pct:.1f}%</td>'
                f'</tr>'
            )
        sections.append(f"""
        <div style="background:#1a1d29;border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:20px;margin-bottom:16px;">
            <div style="font-size:15px;font-weight:700;color:#ffd54f;margin-bottom:12px;">Big Movers (>{BIG_MOVER_THRESHOLD:.0f}%)</div>
            <table style="width:100%;border-collapse:collapse;font-size:13px;">
                <tr style="border-bottom:1px solid rgba(255,255,255,0.1);">
                    <th style="padding:6px 12px;text-align:left;color:#9aa0a6;font-weight:500;">Ticker</th>
                    <th style="padding:6px 12px;text-align:left;color:#9aa0a6;font-weight:500;">Company</th>
                    <th style="padding:6px 12px;text-align:right;color:#9aa0a6;font-weight:500;">Change</th>
                </tr>
                {rows}
            </table>
        </div>""")

    # ── New 8-K Filings ───────────────────────────────────────
    if filings:
        items = "".join(
            f'<li style="color:#e8eaed;margin:4px 0;font-size:13px;">'
            f'<strong>{company}</strong> &mdash; {filename}</li>'
            for company, filename in filings
        )
        sections.append(f"""
        <div style="background:#1a1d29;border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:20px;margin-bottom:16px;">
            <div style="font-size:15px;font-weight:700;color:#42a5f5;margin-bottom:12px;">New 8-K Filings Today</div>
            <ul style="margin:0;padding-left:20px;">{items}</ul>
        </div>""")

    # ── Earnings Tomorrow ─────────────────────────────────────
    if earnings:
        items = "".join(
            f'<li style="color:#e8eaed;margin:4px 0;font-size:13px;">'
            f'<strong>{ticker}</strong> &mdash; {company}</li>'
            for ticker, company, _ in earnings
        )
        sections.append(f"""
        <div style="background:#1a1d29;border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:20px;margin-bottom:16px;">
            <div style="font-size:15px;font-weight:700;color:#66bb6a;margin-bottom:12px;">Earnings Tomorrow</div>
            <ul style="margin:0;padding-left:20px;">{items}</ul>
        </div>""")

    body = "\n".join(sections)

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0f1117;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:600px;margin:0 auto;padding:20px;">
  <div style="background:linear-gradient(135deg,#1a237e,#283593);border-radius:10px;padding:20px 24px;margin-bottom:20px;">
    <div style="font-size:20px;font-weight:700;color:#fff;">Inspection Intel &mdash; Daily Alerts</div>
    <div style="font-size:13px;color:rgba(255,255,255,0.7);margin-top:4px;">{date_str}</div>
  </div>
  {body}
  <div style="text-align:center;padding:12px 0;color:#666;font-size:11px;">
    <a href="https://inspection.__PROJECT_DOMAIN__" style="color:#42a5f5;text-decoration:none;">inspection.__PROJECT_DOMAIN__</a>
  </div>
</div></body></html>"""


def send_email(api_key, subject, html):
    """Send email via Resend API."""
    payload = json.dumps({
        "from": FROM_EMAIL,
        "to": [TO_EMAIL],
        "subject": subject,
        "html": html,
    }).encode()

    req = Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "InspectionIntel-Alerts/1.0",
        },
        method="POST",
    )

    with urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())
        print(f"  Email sent to {TO_EMAIL} (id: {result.get('id', '?')})")


def main():
    dry_run = "--dry-run" in sys.argv

    # Email alerts disabled — remove this line to re-enable
    if not dry_run:
        print("  Alert emails disabled. Run with --dry-run to preview.")
        return

    print("Inspection Intel — Daily Alert Check")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Load market data
    data = load_market_data()
    if not data:
        print("  No market data found. Skipping alerts.")
        return

    # Run checks
    movers = check_big_movers(data)
    filings = check_new_8k_filings()
    earnings = check_earnings_tomorrow(data)

    # Summary
    print(f"  Big movers (>{BIG_MOVER_THRESHOLD:.0f}%): {len(movers)}")
    print(f"  New 8-K filings:  {len(filings)}")
    print(f"  Earnings tomorrow: {len(earnings)}")
    print()

    total_alerts = len(movers) + len(filings) + len(earnings)
    if total_alerts == 0:
        print("  No alerts to send.")
        return

    # Build email
    parts = []
    if movers:
        parts.append(f"{len(movers)} big mover{'s' if len(movers) != 1 else ''}")
    if filings:
        parts.append(f"{len(filings)} new 8-K{'s' if len(filings) != 1 else ''}")
    if earnings:
        parts.append(f"{len(earnings)} reporting tomorrow")

    subject = f"Inspection Alert: {', '.join(parts)} ({datetime.now().strftime('%b %d')})"
    html = build_html(movers, filings, earnings)

    if dry_run:
        print(f"  [DRY RUN] Would send: {subject}")
        for t, c, p in movers:
            print(f"    Mover: {t} ({c}) {p:+.1f}%")
        for c, f in filings:
            print(f"    8-K: {c} — {f}")
        for t, c, d in earnings:
            print(f"    Earnings: {t} ({c}) on {d}")
        return

    # Send
    env = load_env()
    api_key = env.get("RESEND_API_KEY") or os.environ.get("RESEND_API_KEY")
    if not api_key:
        print(f"  ERROR: No RESEND_API_KEY found in {ENV_FILE} or environment.")
        sys.exit(1)

    try:
        send_email(api_key, subject, html)
    except Exception as e:
        print(f"  ERROR sending email: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
