#!/usr/bin/env python3
"""
SEC EDGAR Filing Fetcher — Inspection Intel

Downloads new SEC filings (10-K, 10-Q, 8-K, 20-F, 6-K) for tracked companies.
Uses only Python standard library. Designed for weekly cron/launchd execution.

Usage:
  python3 edgar_fetcher.py              # Fetch new filings for all active companies
  python3 edgar_fetcher.py --backfill   # Fetch all filings since 2022 (initial load)
  python3 edgar_fetcher.py --dry-run    # Show what would be downloaded
  python3 edgar_fetcher.py --company CLH  # Single company only
"""

import os
import sys
import ssl
import json
import time
import gzip
import logging
import argparse
import certifi
from pathlib import Path
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# SSL context using certifi certificates (macOS Python needs this)
SSL_CTX = ssl.create_default_context(cafile=certifi.where())

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parent
COMPANY_DIR = PROJECT_DIR / "Companies"
REGISTRY_FILE = SCRIPT_DIR / "edgar_company_registry.json"
LOG_DIR = SCRIPT_DIR / "logs"

# ---------------------------------------------------------------------------
# SEC EDGAR endpoints
# ---------------------------------------------------------------------------
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVES_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{primary_doc}"
)

# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------
REQUEST_DELAY = 0.15          # seconds between requests (keeps us under 10/s)
MAX_RETRIES = 3
BACKFILL_CUTOFF = "2022-01-01"
WEEKLY_LOOKBACK_DAYS = 10     # overlap window for weekly runs

# ---------------------------------------------------------------------------
# Form-type mapping  (SEC form name -> local directory + filename prefix)
# ---------------------------------------------------------------------------
FORM_TYPE_MAP = {
    "10-K":   {"dir": "10-K", "prefix": "10-K"},
    "10-K/A": {"dir": "10-K", "prefix": "10-K_A"},
    "10-Q":   {"dir": "10-Q", "prefix": "10-Q"},
    "10-Q/A": {"dir": "10-Q", "prefix": "10-Q_A"},
    "8-K":    {"dir": "8-K",  "prefix": "8-K"},
    "8-K/A":  {"dir": "8-K",  "prefix": "8-K_A"},
    "20-F":   {"dir": "10-K", "prefix": "20-F"},
    "20-F/A": {"dir": "10-K", "prefix": "20-F_A"},
    "6-K":    {"dir": "8-K",  "prefix": "6-K"},
    "6-K/A":  {"dir": "8-K",  "prefix": "6-K_A"},
}


# ===================================================================
# Logging
# ===================================================================
def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = LOG_DIR / f"edgar_fetcher_{date_str}.log"

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)

    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)

    logger = logging.getLogger("edgar_fetcher")
    logger.setLevel(logging.INFO)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


# ===================================================================
# Registry
# ===================================================================
def load_registry():
    with open(REGISTRY_FILE, "r") as f:
        data = json.load(f)
    user_agent = data["user_agent"]
    companies = [c for c in data["companies"] if c.get("active", True)]
    return user_agent, companies


# ===================================================================
# HTTP helpers
# ===================================================================
def sec_request(url, user_agent, logger):
    """Rate-limited, retrying GET against SEC EDGAR. Returns bytes or None."""
    headers = {
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json, text/html, */*",
    }
    for attempt in range(MAX_RETRIES):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=30, context=SSL_CTX) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw
        except HTTPError as e:
            if e.code == 429:
                wait = 2 ** (attempt + 1)
                logger.warning(f"Rate limited (429). Retrying in {wait}s …")
                time.sleep(wait)
                continue
            if e.code == 404:
                logger.warning(f"Not found (404): {url}")
                return None
            logger.error(f"HTTP {e.code}: {url}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)
                continue
            return None
        except (URLError, OSError) as e:
            logger.error(f"Network error: {e} — {url}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2)
                continue
            return None
    return None


# ===================================================================
# SEC filing discovery
# ===================================================================
def get_company_filings(cik, user_agent, logger):
    """Return list of dicts with keys: form, filingDate, accessionNumber, primaryDocument."""
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
        filings.append({
            "form": recent["form"][i],
            "filingDate": recent["filingDate"][i],
            "accessionNumber": recent["accessionNumber"][i],
            "primaryDocument": recent["primaryDocument"][i],
        })

    # Pagination — older filing batches
    for file_entry in data.get("filings", {}).get("files", []):
        older_url = f"https://data.sec.gov/submissions/{file_entry['name']}"
        time.sleep(REQUEST_DELAY)
        older_raw = sec_request(older_url, user_agent, logger)
        if not older_raw:
            continue
        older = json.loads(older_raw)
        older_count = len(older.get("accessionNumber", []))
        for i in range(older_count):
            filings.append({
                "form": older["form"][i],
                "filingDate": older["filingDate"][i],
                "accessionNumber": older["accessionNumber"][i],
                "primaryDocument": older["primaryDocument"][i],
            })

    return filings


# ===================================================================
# Filename / URL builders
# ===================================================================
def build_filename(ticker, form_type, filing_date):
    """Returns (subdir_name, filename) or (None, None) if form type unknown."""
    mapping = FORM_TYPE_MAP.get(form_type)
    if not mapping:
        return None, None
    filename = f"{ticker}_{mapping['prefix']}_{filing_date}.htm"
    return mapping["dir"], filename


def build_download_url(cik, accession_number, primary_document):
    cik_clean = str(int(cik))
    accession_dashes = accession_number.replace("-", "")
    return SEC_ARCHIVES_URL.format(
        cik=cik_clean, accession=accession_dashes, primary_doc=primary_document
    )


# ===================================================================
# Deduplication
# ===================================================================
def scan_existing_filings(company_path):
    """Return set of .htm filenames already on disk for a company."""
    existing = set()
    p = Path(company_path)
    if not p.exists():
        return existing
    for subdir in p.iterdir():
        if subdir.is_dir() and not subdir.name.startswith("."):
            for f in subdir.iterdir():
                if f.is_file() and f.suffix == ".htm":
                    existing.add(f.name)
    return existing


# ===================================================================
# Per-company pipeline
# ===================================================================
def process_company(company, user_agent, logger, backfill=False, dry_run=False):
    ticker = company["ticker"]
    cik = company["cik"]
    folder = company["folder"]
    category = company["category"]
    form_types = set(company["form_types"])

    # Auto-include amendment variants
    target_forms = set()
    for ft in form_types:
        target_forms.add(ft)
        target_forms.add(f"{ft}/A")

    company_path = COMPANY_DIR / category / folder
    logger.info(f"Processing {ticker} (CIK: {cik})")

    # 1. Fetch filing index from SEC
    time.sleep(REQUEST_DELAY)
    filings = get_company_filings(cik, user_agent, logger)
    if not filings:
        logger.warning(f"  [{ticker}] No filings returned")
        return {"ticker": ticker, "downloaded": 0, "skipped": 0, "errors": 0}

    # 2. Filter by form type and date range
    if backfill:
        cutoff = BACKFILL_CUTOFF
    else:
        cutoff = (datetime.now() - timedelta(days=WEEKLY_LOOKBACK_DAYS)).strftime(
            "%Y-%m-%d"
        )

    relevant = [
        f for f in filings if f["form"] in target_forms and f["filingDate"] >= cutoff
    ]
    logger.info(
        f"  [{ticker}] {len(relevant)} relevant filings since {cutoff}"
        f" (of {len(filings)} total on EDGAR)"
    )

    # 3. Dedup against files already on disk
    existing = scan_existing_filings(company_path)

    # 4. Download new filings
    downloaded = 0
    skipped = 0
    errors = 0

    for filing in relevant:
        subdir_name, filename = build_filename(
            ticker, filing["form"], filing["filingDate"]
        )
        if not filename:
            continue

        if filename in existing:
            skipped += 1
            continue

        target_dir = company_path / subdir_name
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / filename

        url = build_download_url(cik, filing["accessionNumber"], filing["primaryDocument"])

        if dry_run:
            logger.info(f"    [DRY RUN] Would download: {filename}")
            downloaded += 1
            continue

        time.sleep(REQUEST_DELAY)
        content = sec_request(url, user_agent, logger)
        if content:
            target_path.write_bytes(content)
            downloaded += 1
            logger.info(f"    Downloaded: {filename} ({len(content):,} bytes)")
        else:
            errors += 1
            logger.error(f"    FAILED: {filename} — {url}")

    logger.info(
        f"  [{ticker}] Done — {downloaded} new, {skipped} existing, {errors} errors"
    )
    return {"ticker": ticker, "downloaded": downloaded, "skipped": skipped, "errors": errors}


# ===================================================================
# Main
# ===================================================================
def main():
    parser = argparse.ArgumentParser(
        description="SEC EDGAR Filing Fetcher — Inspection Intel"
    )
    parser.add_argument(
        "--backfill", action="store_true",
        help="Download all filings since 2022 (initial load)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be downloaded without downloading",
    )
    parser.add_argument(
        "--company", type=str,
        help="Process only one company by ticker (e.g. CLH)",
    )
    parser.add_argument(
        "--category", type=str,
        help="Process only one category (e.g. Industrial_Inspection)",
    )
    args = parser.parse_args()

    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("SEC EDGAR Filing Fetcher — Inspection Intel")
    mode = "Backfill" if args.backfill else "Weekly"
    if args.dry_run:
        mode += " (DRY RUN)"
    logger.info(f"Mode: {mode}")
    logger.info("=" * 60)

    try:
        user_agent, companies = load_registry()
    except FileNotFoundError:
        logger.error(f"Registry not found: {REGISTRY_FILE}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in registry: {e}")
        sys.exit(1)

    if args.company:
        companies = [c for c in companies if c["ticker"].upper() == args.company.upper()]
        if not companies:
            logger.error(f"Company '{args.company}' not found or not active")
            sys.exit(1)
    if args.category:
        companies = [c for c in companies if c["category"] == args.category]

    logger.info(f"Active companies to process: {len(companies)}")

    results = []
    for company in companies:
        try:
            result = process_company(
                company, user_agent, logger,
                backfill=args.backfill, dry_run=args.dry_run,
            )
            results.append(result)
        except Exception as e:
            logger.error(f"  [{company['ticker']}] Unhandled error: {e}", exc_info=True)
            results.append({
                "ticker": company["ticker"],
                "downloaded": 0, "skipped": 0, "errors": 1,
            })

    # Summary
    total_new = sum(r["downloaded"] for r in results)
    total_skip = sum(r["skipped"] for r in results)
    total_err = sum(r["errors"] for r in results)
    failed = [r["ticker"] for r in results if r["errors"] > 0]

    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info(f"  New filings downloaded : {total_new}")
    logger.info(f"  Already existing       : {total_skip}")
    logger.info(f"  Errors                 : {total_err}")
    if failed:
        logger.warning(f"  Companies with errors  : {', '.join(failed)}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
