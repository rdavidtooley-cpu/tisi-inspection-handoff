#!/usr/bin/env python3
"""
Koyfin Earnings Transcript Downloader for Inspection Intel
Downloads earnings call transcripts from Koyfin's API.

Usage:
  python3 koyfin_transcripts.py                  # Download all available transcripts
  python3 koyfin_transcripts.py --recent 14      # Only last 14 days (for weekly runs)
  python3 koyfin_transcripts.py --token <jwt>     # Update stored token
"""

import os, sys, json, time, re, argparse
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

# ── Configuration ──────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)  # Inspection_Intel/
COMPANY_DIR = os.path.join(PROJECT_DIR, "Companies")
TOKEN_FILE = os.path.join(SCRIPT_DIR, "koyfin_token.json")

BASE_URL = "https://app.koyfin.com"
HEADERS_TEMPLATE = {
    "Origin": "https://app.koyfin.com",
    "Referer": "https://app.koyfin.com/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/json"
}

MAX_WORKERS = 6
SEARCH_DELAY = 0.15   # seconds between ticker searches
DOWNLOAD_DELAY = 0.08  # seconds between transcript downloads
MAX_RETRIES = 3
CUTOFF_DATE = datetime(2023, 1, 1)  # 3 years back

# ── Token Management ──────────────────────────────────────────────────────

def load_token():
    """Load refresh token from JSON file."""
    if not os.path.exists(TOKEN_FILE):
        print(f"ERROR: Token file not found at {TOKEN_FILE}")
        print("Run with --token <jwt> to save a token, or extract from Koyfin cookies.")
        sys.exit(1)
    with open(TOKEN_FILE) as f:
        data = json.load(f)
    token = data.get("refresh_token", "")
    expires = data.get("expires", "")
    if expires:
        exp_date = datetime.strptime(expires, "%Y-%m-%d")
        days_left = (exp_date - datetime.now()).days
        if days_left < 0:
            print(f"WARNING: Token expired {-days_left} days ago! Please refresh.")
            print("Log into app.koyfin.com and extract new refresh_token from cookies.")
            sys.exit(1)
        elif days_left < 3:
            print(f"WARNING: Token expires in {days_left} days. Refresh soon!")
    return token


def save_token(token):
    """Save a new token to disk."""
    import base64
    try:
        payload = token.split('.')[1]
        payload += '=' * (4 - len(payload) % 4)
        decoded = json.loads(base64.b64decode(payload))
        exp_ts = decoded.get("exp", 0)
        exp_date = datetime.fromtimestamp(exp_ts).strftime("%Y-%m-%d")
    except Exception:
        exp_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

    with open(TOKEN_FILE, 'w') as f:
        json.dump({"refresh_token": token, "expires": exp_date}, f, indent=2)
    print(f"Token saved. Expires: {exp_date}")


# ── Company Discovery ─────────────────────────────────────────────────────

def discover_companies():
    """Scan Companies/{category}/{Name_TICKER}/ for company directories.

    Folder naming convention: CompanyName_TICKER (e.g., MistrasGroup_MG)
    Ticker is everything after the last underscore.
    """
    companies = []
    for category in sorted(os.listdir(COMPANY_DIR)):
        cat_path = os.path.join(COMPANY_DIR, category)
        if not os.path.isdir(cat_path) or category.startswith('.'):
            continue
        for entry in sorted(os.listdir(cat_path)):
            full_path = os.path.join(cat_path, entry)
            if not os.path.isdir(full_path) or entry.startswith('.'):
                continue
            # Extract ticker: everything after the last underscore
            parts = entry.rsplit('_', 1)
            if len(parts) == 2:
                ticker = parts[1]
                companies.append({
                    "ticker": ticker,
                    "folder_name": entry,
                    "folder_path": full_path,
                    "category": category,
                    "transcripts_dir": os.path.join(full_path, "Transcripts")
                })
    return companies


# ── Koyfin API ─────────────────────────────────────────────────────────────

def make_session(token):
    """Create a requests session with auth headers."""
    s = requests.Session()
    s.headers.update(HEADERS_TEMPLATE)
    s.headers["Authorization"] = f"Bearer {token}"
    return s


def search_ticker(session, ticker, prefer_us=True):
    """Resolve ticker to Koyfin equity ID (KID)."""
    url = f"{BASE_URL}/api/v1/bfc/tickers/search"
    payload = {
        "searchString": ticker,
        "categories": ["Equity"],
        "domains": ["NONE"],
        "primaryOnly": False
    }
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                matches = data.get("data", [])
                if prefer_us:
                    # Prefer US listing with exact ticker match
                    us_match = next((m for m in matches if m.get("country") == "US" and m.get("ticker") == ticker), None)
                    any_match = next((m for m in matches if m.get("ticker") == ticker), None)
                    match = us_match or any_match
                    if match:
                        return match["KID"], match["name"]
                    # Try first US result
                    us_any = next((m for m in matches if m.get("country") == "US"), None)
                    if us_any:
                        return us_any["KID"], us_any["name"]
                else:
                    # For foreign filers, take exact ticker match regardless of country
                    exact = next((m for m in matches if m.get("ticker") == ticker), None)
                    if exact:
                        return exact["KID"], exact["name"]
                # Fallback: first result
                if matches:
                    return matches[0]["KID"], matches[0]["name"]
            elif resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)
    return None, None


def get_transcript_list(session, kid, recent_days=None):
    """Get list of earnings call transcripts for a company."""
    url = f"{BASE_URL}/api/v1/pubhub/transcript/list/{kid}?limit=100"
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if not isinstance(data, list):
                    return []
                # Filter to earnings calls only
                earnings = [t for t in data if t.get("eventType") in ("Earnings Calls", "Earnings Call")]
                # Apply date filter
                if recent_days:
                    cutoff = datetime.now() - timedelta(days=recent_days)
                    earnings = [t for t in earnings if datetime.fromisoformat(t["eventDateTime"].replace("Z","")) >= cutoff]
                else:
                    earnings = [t for t in earnings if datetime.fromisoformat(t["eventDateTime"].replace("Z","")) >= CUTOFF_DATE]
                return earnings
            elif resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)
    return []


def get_transcript_content(session, key_dev_id):
    """Download full transcript content."""
    url = f"{BASE_URL}/api/v1/pubhub/v2/transcript/{key_dev_id}"
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            elif resp.status_code == 401:
                print(f"    AUTH ERROR for transcript {key_dev_id} - token may be expired")
                return None
        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)
    return None


def format_transcript(data, meta):
    """Format transcript data into readable text."""
    header = data.get("header", {})
    title = header.get("title", meta.get("formattedTitle", "Earnings Call"))
    date_str = meta.get("eventDateTime", header.get("eventDateTime", ""))
    company = header.get("companyName", "")

    lines = [
        title,
        f"Date: {date_str}",
        f"Type: Earnings Call",
        f"Company: {company}",
        "=" * 64,
        ""
    ]

    for component in data.get("components", []):
        speaker = component.get("speakerName", "Unknown")
        role = component.get("speakerType", "")
        text = component.get("text", "")
        lines.append(f"[{speaker} - {role}]")
        lines.append(text)
        lines.append("")

    return "\n".join(lines)


# ── Ticker Overrides and Foreign Filer Handling ───────────────────────────

# Companies where the folder ticker doesn't match what Koyfin expects.
# OTC tickers (BVRDF, ERFSF, etc.) may need the primary exchange ticker.
# "prefer_us": False means search globally, not just US listings.
TICKER_OVERRIDES = {
    # Global NDT — international exchange tickers
    "SGSN":  {"search": "SGS SA",           "prefer_us": False},
    "BVI":   {"search": "Bureau Veritas",   "prefer_us": False},
    "ITRK":  {"search": "Intertek",         "prefer_us": False},
    "COTN":  {"search": "Comet Group",      "prefer_us": False},
    # NDT Services
    "XPRO":  {"search": "Expro Group",      "prefer_us": True},
    # Flow Control — LSE-listed foreign filers
    "ROR":   {"search": "Rotork",           "prefer_us": False},
    "IMI":   {"search": "IMI plc",          "prefer_us": False},
    "SPX":   {"search": "Spirax Group",     "prefer_us": False},
    "WEIR":  {"search": "Weir Group",       "prefer_us": False},
    # Legacy TIC_Majors (may still have folders)
    "ALQ":   {"search": "ALS Limited",     "prefer_us": False},
    "BVRDF": {"search": "Bureau Veritas",   "prefer_us": False},
    "ERFSF": {"search": "Eurofins",         "prefer_us": False},
    "ITRKY": {"search": "Intertek",         "prefer_us": False},
    "SGSOF": {"search": "SGS SA",           "prefer_us": False},
    "ULSLF": {"search": "UL Solutions",     "prefer_us": True},
}

# Companies with no Koyfin coverage (skip cleanly)
NO_COVERAGE = set()
# Previously skipped: "TIC" (Acuren) — re-tested 2026-04 after NYSE uplisting; Koyfin now covers.


# ── Per-Company Pipeline ──────────────────────────────────────────────────

def process_company(token, company, recent_days=None):
    """Full pipeline for one company: search -> list -> download."""
    ticker = company["ticker"]
    transcripts_dir = company["transcripts_dir"]

    # Skip companies with known no coverage
    if ticker in NO_COVERAGE:
        print(f"  [{ticker}] No Koyfin coverage - skipping")
        return {"ticker": ticker, "status": "no_coverage", "downloaded": 0}

    os.makedirs(transcripts_dir, exist_ok=True)

    session = make_session(token)

    # Step 1: Resolve ticker to KID
    override = TICKER_OVERRIDES.get(ticker)
    if override:
        search_term = override["search"]
        prefer_us = override.get("prefer_us", True)
        kid, name = search_ticker(session, search_term, prefer_us=prefer_us)
    else:
        kid, name = search_ticker(session, ticker, prefer_us=True)

    if not kid:
        print(f"  [{ticker}] Could not resolve Koyfin ID - skipping")
        return {"ticker": ticker, "status": "no_kid", "downloaded": 0}

    time.sleep(SEARCH_DELAY)

    # Step 2: Get transcript list
    transcripts = get_transcript_list(session, kid, recent_days)
    if not transcripts:
        print(f"  [{ticker}] No earnings transcripts found (KID: {kid})")
        return {"ticker": ticker, "status": "no_transcripts", "downloaded": 0, "kid": kid}

    # Step 3: Download each transcript
    downloaded = 0
    skipped = 0
    for t in transcripts:
        fq = t.get("fiscalQuarter", 0)
        fy = t.get("fiscalYear", 0)
        key_dev_id = t.get("keyDevId")

        filename = f"{ticker}_Q{fq}_{fy}_Earnings_Call.txt"
        filepath = os.path.join(transcripts_dir, filename)

        # Skip if already exists and is substantial
        if os.path.exists(filepath) and os.path.getsize(filepath) > 100:
            skipped += 1
            continue

        content = get_transcript_content(session, key_dev_id)
        if content and content.get("header"):
            text = format_transcript(content, t)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(text)
            downloaded += 1
            time.sleep(DOWNLOAD_DELAY)
        else:
            print(f"    [{ticker}] Failed to download Q{fq} {fy}")

    status = "ok" if downloaded > 0 or skipped > 0 else "empty"
    print(f"  [{ticker}] {downloaded} downloaded, {skipped} skipped (of {len(transcripts)} total)")
    return {"ticker": ticker, "status": status, "downloaded": downloaded, "skipped": skipped, "total": len(transcripts)}


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Download Koyfin earnings transcripts (Inspection Intel)")
    parser.add_argument("--recent", type=int, help="Only download transcripts from last N days")
    parser.add_argument("--token", type=str, help="Save a new refresh token")
    parser.add_argument("--category", type=str, help="Only process one category (e.g., TIC_Majors)")
    args = parser.parse_args()

    if args.token:
        save_token(args.token)
        print("Token updated. Run again without --token to download transcripts.")
        return

    token = load_token()
    companies = discover_companies()

    if args.category:
        companies = [c for c in companies if c["category"] == args.category]

    if not companies:
        print("No company folders found in Companies/")
        sys.exit(1)

    print(f"\nKoyfin Transcript Downloader — Inspection Intel")
    print(f"{'='*50}")
    print(f"Companies found: {len(companies)}")
    if args.category:
        print(f"Category filter: {args.category}")
    print(f"Mode: {'Last ' + str(args.recent) + ' days' if args.recent else 'Full history (since 2023)'}")
    print(f"{'='*50}\n")

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_company, token, c, args.recent): c
            for c in companies
        }
        for future in as_completed(futures):
            company = futures[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                print(f"  [{company['ticker']}] ERROR: {e}")
                results.append({"ticker": company["ticker"], "status": "error", "downloaded": 0})

    # Summary
    total_downloaded = sum(r.get("downloaded", 0) for r in results)
    total_skipped = sum(r.get("skipped", 0) for r in results)
    failed = [r["ticker"] for r in results if r["status"] in ("no_kid", "error")]
    no_transcripts = [r["ticker"] for r in results if r["status"] == "no_transcripts"]

    print(f"\n{'='*50}")
    print(f"SUMMARY")
    print(f"{'='*50}")
    print(f"Total downloaded: {total_downloaded}")
    print(f"Total skipped (existing): {total_skipped}")
    if failed:
        print(f"Failed to resolve: {', '.join(failed)}")
    if no_transcripts:
        print(f"No transcripts available: {', '.join(no_transcripts)}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
