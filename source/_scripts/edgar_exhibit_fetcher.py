#!/usr/bin/env python3
"""
SEC EDGAR 8-K Exhibit Fetcher — Inspection_Intel

Downloads presentation exhibits (EX-99.x) from 8-K filings. These contain
earnings presentations, press releases, investor day slides, and supplemental
data that companies file alongside their 8-K announcements.

Companion to edgar_fetcher.py — this grabs the exhibits, not the primary filing.

Usage:
  python3 edgar_exhibit_fetcher.py              # Fetch recent exhibits (last 30 days)
  python3 edgar_exhibit_fetcher.py --backfill   # Fetch all since 2022
  python3 edgar_exhibit_fetcher.py --dry-run    # Show what would be downloaded
  python3 edgar_exhibit_fetcher.py --company MG  # Single company only
"""

import json
import logging
import os
import re
import ssl
import sys
import time
import gzip
import argparse
import certifi
from pathlib import Path
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SSL_CTX = ssl.create_default_context(cafile=certifi.where())

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parent
COMPANIES_DIR = PROJECT_DIR / "Companies"
REGISTRY_FILE = SCRIPT_DIR / "edgar_company_registry.json"
LOG_DIR = SCRIPT_DIR / "logs"

# ---------------------------------------------------------------------------
# SEC endpoints
# ---------------------------------------------------------------------------
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_FILING_INDEX_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
)

# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------
REQUEST_DELAY = 0.15          # stay under SEC 10 req/s limit
MAX_RETRIES = 3
BACKFILL_CUTOFF = "2022-01-01"
DAILY_LOOKBACK_DAYS = 30      # wider window since we only need new exhibits
MIN_FILE_SIZE = 5_000         # 5 KB min (skip stubs)
MAX_FILE_SIZE = 50_000_000    # 50 MB max

# Forms that carry exhibits (8-K, 6-K for international filers)
EXHIBIT_FORMS = {"8-K", "8-K/A", "6-K", "6-K/A"}

# Exhibit patterns to download (99.x = press releases/presentations)
EXHIBIT_PATTERN = re.compile(
    r'(ex[\-_]?(?:99|991|992|993)[\-_.].*?\.(?:htm|pdf|txt))',
    re.IGNORECASE
)


def classify_exhibit(filename, description=""):
    """Classify an exhibit into a subfolder."""
    text = (filename + " " + description).lower()
    if any(kw in text for kw in ['presentation', 'slide', 'deck', 'investor day']):
        return "Presentations"
    if any(kw in text for kw in ['press release', 'press-release', 'earnings release']):
        return "Press_Releases"
    if any(kw in text for kw in ['supplemental', 'supplement', 'statistical']):
        return "Supplementals"
    # Default: press releases are most common 99.1 exhibits
    return "Press_Releases"


# ===================================================================
# Logging
# ===================================================================
def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = LOG_DIR / f"exhibit_fetcher_{date_str}.log"

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)

    logger = logging.getLogger("exhibit_fetcher")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        logger.addHandler(fh)
        logger.addHandler(sh)
    return logger


# ===================================================================
# HTTP
# ===================================================================
def sec_request(url, user_agent, logger, binary=False):
    """Rate-limited GET against SEC EDGAR."""
    headers = {
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "text/html, application/json, */*",
    }
    for attempt in range(MAX_RETRIES):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=30, context=SSL_CTX) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw if binary else raw.decode("utf-8", errors="replace")
        except HTTPError as e:
            if e.code == 429:
                wait = 2 ** (attempt + 1)
                logger.warning(f"  Rate limited. Retrying in {wait}s...")
                time.sleep(wait)
                continue
            if e.code == 404:
                return None
            logger.error(f"  HTTP {e.code}: {url}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)
                continue
            return None
        except (URLError, OSError) as e:
            logger.error(f"  Network error: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2)
                continue
            return None
    return None


# ===================================================================
# Filing discovery
# ===================================================================
def get_8k_filings(cik, user_agent, logger, cutoff_date):
    """Get 8-K/6-K filings from EDGAR since cutoff_date."""
    cik_padded = cik.lstrip("0").zfill(10)
    url = SEC_SUBMISSIONS_URL.format(cik=cik_padded)

    raw = sec_request(url, user_agent, logger)
    if not raw:
        return []

    data = json.loads(raw)
    recent = data.get("filings", {}).get("recent", {})

    filings = []
    count = len(recent.get("accessionNumber", []))
    for i in range(count):
        form = recent["form"][i]
        date = recent["filingDate"][i]
        if form in EXHIBIT_FORMS and date >= cutoff_date:
            filings.append({
                "form": form,
                "filingDate": date,
                "accessionNumber": recent["accessionNumber"][i],
                "primaryDocument": recent["primaryDocument"][i],
            })

    return filings


def find_exhibit_documents(cik, accession, user_agent, logger):
    """Parse a filing's structured index page to find exhibit 99.x documents."""
    cik_clean = str(int(cik))
    accession_clean = accession.replace("-", "")
    # Use the structured -index.html which has proper Seq/Description/Document/Type/Size columns
    index_url = f"https://www.sec.gov/Archives/edgar/data/{cik_clean}/{accession_clean}/{accession}-index.html"

    time.sleep(REQUEST_DELAY)
    html = sec_request(index_url, user_agent, logger)
    if not html:
        return []

    exhibits = []

    # Parse table rows: columns are Seq, Description, Document (with link), Type, Size
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)

    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 4:
            continue

        # Type is in column index 3 (0-indexed: Seq=0, Desc=1, Doc=2, Type=3, Size=4)
        doc_type = re.sub(r'<[^>]+>', '', cells[3]).strip()
        description = re.sub(r'<[^>]+>', '', cells[1]).strip()

        # Only grab EX-99.x exhibits (press releases, presentations, supplementals)
        if not re.match(r'EX-99', doc_type, re.IGNORECASE):
            continue

        # Extract document link from the Document column
        link_match = re.search(r'href="([^"]+)"', cells[2], re.IGNORECASE)
        if not link_match:
            continue

        doc_path = link_match.group(1)
        doc_name = doc_path.split("/")[-1]

        # Build full URL
        if doc_path.startswith("http"):
            full_url = doc_path
        elif doc_path.startswith("/"):
            full_url = f"https://www.sec.gov{doc_path}"
        else:
            base = f"https://www.sec.gov/Archives/edgar/data/{cik_clean}/{accession_clean}/"
            full_url = base + doc_path

        exhibits.append({
            "url": full_url,
            "filename": doc_name,
            "type": doc_type,
            "description": description,
        })

    return exhibits


# ===================================================================
# Per-company pipeline
# ===================================================================
def process_company(company, user_agent, logger, cutoff, dry_run=False):
    """Fetch exhibit documents for a single company."""
    ticker = company["ticker"]
    cik = company["cik"]
    folder = company["folder"]
    category = company["category"]

    # Find the company folder in Companies/<category>/<folder>/
    company_dir = COMPANIES_DIR / category / folder

    logger.info(f"\n  {folder}")

    # Get existing files to avoid re-downloading
    existing = set()
    for sub in ["Presentations", "Press_Releases", "Supplementals"]:
        subdir = company_dir / sub
        if subdir.exists():
            for f in subdir.rglob("*"):
                if f.is_file():
                    existing.add(f.name.lower())

    # Get 8-K filings
    time.sleep(REQUEST_DELAY)
    filings = get_8k_filings(cik, user_agent, logger, cutoff)
    logger.info(f"    {len(filings)} 8-K/6-K filings since {cutoff}")

    downloaded = 0
    skipped = 0

    for filing in filings:
        # Get exhibit documents from the filing index
        exhibits = find_exhibit_documents(
            cik, filing["accessionNumber"], user_agent, logger
        )

        for exhibit in exhibits:
            # Build local filename: TICKER_8-K_DATE_exhibit.ext
            ext = Path(exhibit["filename"]).suffix or ".htm"
            local_name = f"{ticker}_{filing['form'].replace('/', '_')}_{filing['filingDate']}_{exhibit['type'].replace(' ', '_').replace('-', '')}{ext}"

            if local_name.lower() in existing:
                skipped += 1
                continue

            # Classify and set destination
            doc_class = classify_exhibit(exhibit["filename"], exhibit["description"])
            dest_path = company_dir / doc_class / local_name

            if dry_run:
                logger.info(f"    [DRY RUN] {local_name} → {doc_class}/")
                downloaded += 1
            else:
                time.sleep(REQUEST_DELAY)
                data = sec_request(exhibit["url"], user_agent, logger, binary=True)
                if data and MIN_FILE_SIZE <= len(data) <= MAX_FILE_SIZE:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(dest_path, "wb") as f:
                        f.write(data)
                    size_kb = len(data) / 1024
                    logger.info(f"    Saved: {local_name} ({size_kb:,.0f} KB) → {doc_class}/")
                    downloaded += 1
                elif data:
                    logger.warning(f"    Skipped {local_name} (size: {len(data):,} bytes)")

    logger.info(f"    Result: {downloaded} new, {skipped} already had")
    return downloaded


# ===================================================================
# Main
# ===================================================================
def main():
    parser = argparse.ArgumentParser(description="8-K Exhibit Fetcher — Inspection Intel")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be downloaded")
    parser.add_argument("--backfill", action="store_true", help="Fetch all since 2022")
    parser.add_argument("--company", type=str, help="Fetch for specific ticker only")
    args = parser.parse_args()

    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("8-K Exhibit Fetcher — Inspection Intel")
    logger.info(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if args.dry_run:
        logger.info("  Mode: DRY RUN")
    if args.backfill:
        logger.info("  Mode: BACKFILL (since 2022)")
    logger.info("=" * 60)

    with open(REGISTRY_FILE) as f:
        registry = json.load(f)

    user_agent = registry["user_agent"]
    companies = [c for c in registry["companies"] if c.get("active", True)]

    if args.company:
        companies = [c for c in companies if c["ticker"] == args.company.upper()]
        if not companies:
            logger.error(f"Ticker '{args.company}' not found")
            sys.exit(1)

    cutoff = BACKFILL_CUTOFF if args.backfill else (
        datetime.now() - timedelta(days=DAILY_LOOKBACK_DAYS)
    ).strftime("%Y-%m-%d")

    total = 0
    for company in companies:
        try:
            count = process_company(company, user_agent, logger, cutoff, args.dry_run)
            total += count
        except Exception as e:
            logger.error(f"  Error: {company['ticker']}: {e}", exc_info=True)

    logger.info("\n" + "=" * 60)
    logger.info(f"SUMMARY: {total} new exhibits {'found (dry run)' if args.dry_run else 'downloaded'}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
