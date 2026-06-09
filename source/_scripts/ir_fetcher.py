#!/usr/bin/env python3
"""
International IR Fetcher — Inspection Intel

Downloads annual reports, interim reports, and press releases from company
investor relations pages for non-SEC filers (SGS, Bureau Veritas, Intertek,
Comet Group). Also checks SEDAR+ for Canadian filers.

Usage:
  python3 ir_fetcher.py              # Fetch new IR documents
  python3 ir_fetcher.py --dry-run    # Show what would be downloaded
  python3 ir_fetcher.py --backfill   # Attempt deeper historical fetch
"""

import json
import logging
import os
import re
import ssl
import sys
import time
import argparse
import certifi
from pathlib import Path
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SSL_CTX = ssl.create_default_context(cafile=certifi.where())

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parent
COMPANY_RESEARCH_DIR = PROJECT_DIR / "Companies"
LOG_DIR = SCRIPT_DIR / "logs"
REGISTRY_FILE = SCRIPT_DIR / "edgar_company_registry.json"

# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------
REQUEST_DELAY = 2.0
MAX_RETRIES = 3

USER_AGENT = "InspectionIntel RobertTooley __ADMIN_EMAIL__"

# ---------------------------------------------------------------------------
# IR Source Configuration
# ---------------------------------------------------------------------------
IR_SOURCES = {
    'SGSN.SW': {
        'name': 'SGS SA',
        'category': 'Global_NDT',
        'folder': 'SGS_SGSN',
        'ir_url': 'https://www.sgs.com/en/investor-relations/financial-reports',
        'pdf_pattern': r'href="([^"]*\.pdf[^"]*)"',
        'annual_keywords': ['annual', 'yearly', 'full-year', 'integrated'],
        'interim_keywords': ['half-year', 'interim', 'semi-annual', 'h1', 'h2'],
    },
    'BVI.PA': {
        'name': 'Bureau Veritas',
        'category': 'Global_NDT',
        'folder': 'BureauVeritas_BVI',
        'ir_url': 'https://group.bureauveritas.com/investors/regulated-information/annual-reports',
        'pdf_pattern': r'href="([^"]*\.pdf[^"]*)"',
        'annual_keywords': ['annual', 'registration', 'universal', 'urd'],
        'interim_keywords': ['half-year', 'interim', 'semi-annual', 'h1'],
    },
    'ITRK.L': {
        'name': 'Intertek Group',
        'category': 'Global_NDT',
        'folder': 'Intertek_ITRK',
        'ir_url': 'https://www.intertek.com/investors/reports-presentations/',
        'pdf_pattern': r'href="([^"]*\.pdf[^"]*)"',
        'annual_keywords': ['annual', 'full-year'],
        'interim_keywords': ['interim', 'half-year', 'h1'],
    },
    'COTN.SW': {
        'name': 'Comet Group',
        'category': 'Global_NDT',
        'folder': 'CometGroup_COTN',
        'ir_url': 'https://www.comet-group.com/en/investors/reports-publications',
        'pdf_pattern': r'href="([^"]*\.pdf[^"]*)"',
        'annual_keywords': ['annual', 'full-year'],
        'interim_keywords': ['half-year', 'interim', 'h1', 'h2'],
    },
}


# ===================================================================
# Logging
# ===================================================================
def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = LOG_DIR / f"ir_fetcher_{date_str}.log"

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)

    logger = logging.getLogger("ir_fetcher")
    logger.setLevel(logging.INFO)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


# ===================================================================
# HTTP
# ===================================================================
def fetch_url(url, logger, binary=False):
    """Rate-limited GET. Returns string (or bytes if binary) or None."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    for attempt in range(MAX_RETRIES):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=60, context=SSL_CTX) as resp:
                data = resp.read()
                return data if binary else data.decode("utf-8", errors="replace")
        except HTTPError as e:
            logger.error(f"HTTP {e.code}: {url}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return None
        except (URLError, OSError) as e:
            logger.error(f"Network error: {e} — {url}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(3 * (attempt + 1))
                continue
            return None
    return None


def download_pdf(url, dest_path, logger):
    """Download a PDF file to dest_path. Returns True on success."""
    logger.info(f"    Downloading: {url}")
    data = fetch_url(url, logger, binary=True)
    if not data:
        return False
    if len(data) < 1000:
        logger.warning(f"    Suspiciously small file ({len(data)} bytes), skipping")
        return False
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, 'wb') as f:
        f.write(data)
    logger.info(f"    Saved: {dest_path.name} ({len(data):,} bytes)")
    return True


# ===================================================================
# PDF Link Discovery
# ===================================================================
def find_pdf_links(html, base_url, logger):
    """Extract all PDF links from HTML page."""
    links = []
    # Find all href attributes pointing to PDFs
    matches = re.findall(r'href="([^"]*\.pdf[^"]*)"', html, re.IGNORECASE)
    for href in matches:
        if href.startswith("http"):
            full_url = href
        elif href.startswith("//"):
            full_url = "https:" + href
        elif href.startswith("/"):
            # Extract base domain
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            full_url = f"{parsed.scheme}://{parsed.netloc}{href}"
        else:
            full_url = base_url.rstrip("/") + "/" + href

        # Clean URL
        full_url = full_url.split("#")[0]
        if full_url not in links:
            links.append(full_url)

    return links


def classify_report(url, filename, annual_keywords, interim_keywords):
    """Classify a PDF as annual, interim, or other based on URL/filename."""
    text = (url + " " + filename).lower()
    for kw in annual_keywords:
        if kw in text:
            return "10-K"
    for kw in interim_keywords:
        if kw in text:
            return "10-Q"
    return "Other"


def get_existing_files(folder_path):
    """Get set of existing filenames in a folder tree."""
    existing = set()
    if folder_path.exists():
        for f in folder_path.rglob("*.pdf"):
            existing.add(f.name.lower())
    return existing


# ===================================================================
# Per-Company Fetchers
# ===================================================================
def fetch_ir_reports(ticker, config, dry_run, logger):
    """Fetch IR reports for a single company."""
    name = config['name']
    folder = config['folder']
    category = config['category']
    ir_url = config['ir_url']
    annual_kw = config['annual_keywords']
    interim_kw = config['interim_keywords']

    logger.info(f"\n--- {name} ({ticker}) ---")
    logger.info(f"  IR URL: {ir_url}")

    company_dir = COMPANY_RESEARCH_DIR / category / folder
    existing_files = get_existing_files(company_dir)
    logger.info(f"  Existing files on disk: {len(existing_files)}")

    time.sleep(REQUEST_DELAY)
    html = fetch_url(ir_url, logger)
    if not html:
        logger.warning(f"  Could not fetch IR page for {name}")
        return 0

    pdf_links = find_pdf_links(html, ir_url, logger)
    logger.info(f"  Found {len(pdf_links)} PDF links on page")

    downloaded = 0
    for pdf_url in pdf_links:
        # Extract filename from URL
        filename = pdf_url.split("/")[-1].split("?")[0]
        if not filename.endswith(".pdf"):
            filename += ".pdf"

        # Skip if already downloaded
        if filename.lower() in existing_files:
            continue

        # Classify the report
        report_type = classify_report(pdf_url, filename, annual_kw, interim_kw)
        dest_path = company_dir / report_type / filename

        if dry_run:
            logger.info(f"  [DRY RUN] Would download: {filename} → {report_type}")
            downloaded += 1
        else:
            time.sleep(REQUEST_DELAY)
            if download_pdf(pdf_url, dest_path, logger):
                downloaded += 1

    logger.info(f"  {name}: {downloaded} new reports {'(dry run)' if dry_run else 'downloaded'}")
    return downloaded


# ===================================================================
# SEDAR+ for Canadian filers (Acuren/TIC)
# ===================================================================
def fetch_sedar_filings(logger, dry_run=False):
    """Check SEDAR+ for Acuren Group filings."""
    logger.info("\n--- SEDAR+ (Acuren Group) ---")
    # SEDAR+ API endpoint for document search
    # Note: SEDAR+ requires specific API calls; this is a simplified version
    sedar_url = "https://www.sedarplus.ca/csa-party/records/filter"

    # SEDAR+ is a complex SPA; for now we'll check the IR page directly
    acuren_sedar = "https://www.sedarplus.ca/landingPage/en/default.html"
    logger.info(f"  SEDAR+ URL: {acuren_sedar}")
    logger.info("  Note: SEDAR+ requires interactive search. Check manually or use API when available.")
    logger.info("  Acuren SEC filings are fetched by edgar_fetcher.py (CIK: 0002032966)")
    return 0


# ===================================================================
# Main
# ===================================================================
def main():
    parser = argparse.ArgumentParser(
        description="International IR Fetcher — Inspection Intel"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be downloaded")
    parser.add_argument("--backfill", action="store_true",
                        help="Attempt deeper historical fetch")
    parser.add_argument("--company", type=str,
                        help="Fetch for specific ticker only")
    args = parser.parse_args()

    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("International IR Fetcher — Inspection Intel")
    if args.dry_run:
        logger.info("Mode: DRY RUN")
    if args.backfill:
        logger.info("Mode: BACKFILL")
    logger.info("=" * 60)

    total_downloaded = 0

    for ticker, config in IR_SOURCES.items():
        if args.company and args.company != ticker:
            continue
        try:
            count = fetch_ir_reports(ticker, config, args.dry_run, logger)
            total_downloaded += count
        except Exception as e:
            logger.error(f"Error processing {ticker}: {e}", exc_info=True)

    # SEDAR+ check
    if not args.company or args.company == 'TIC':
        try:
            total_downloaded += fetch_sedar_filings(logger, args.dry_run)
        except Exception as e:
            logger.error(f"Error checking SEDAR+: {e}", exc_info=True)

    logger.info("=" * 60)
    logger.info(f"SUMMARY: {total_downloaded} new reports {'found (dry run)' if args.dry_run else 'downloaded'}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
