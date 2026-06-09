#!/usr/bin/env python3
"""
OSHA Inspection Data Fetcher — Inspection Intel

Queries OSHA establishment search for tracked companies and by NAICS codes.
Saves inspection records and violation details to CSV files.

Usage:
  python3 osha_fetcher.py              # Fetch new inspections (last 30 days)
  python3 osha_fetcher.py --backfill   # Fetch all inspections since 2022
  python3 osha_fetcher.py --dry-run    # Show what would be fetched
  python3 osha_fetcher.py --company CLH  # Single company only
"""

import csv
import io
import json
import logging
import re
import ssl
import sys
import time
import argparse
import certifi
from pathlib import Path
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError

SSL_CTX = ssl.create_default_context(cafile=certifi.where())

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parent
OSHA_DIR = PROJECT_DIR / "Industry_Data" / "OSHA"
REGISTRY_FILE = SCRIPT_DIR / "edgar_company_registry.json"
LOG_DIR = SCRIPT_DIR / "logs"

INSPECTIONS_CSV = OSHA_DIR / "osha_inspections.csv"
VIOLATIONS_CSV = OSHA_DIR / "osha_violations.csv"

# ---------------------------------------------------------------------------
# OSHA endpoints
# ---------------------------------------------------------------------------
OSHA_SEARCH_URL = "https://www.osha.gov/ords/imis/establishment.search"
OSHA_DETAIL_URL = "https://www.osha.gov/ords/imis/establishment.inspection_detail?id={activity_nr}"

# ---------------------------------------------------------------------------
# NAICS codes for industry-wide searches
# ---------------------------------------------------------------------------
NAICS_CODES = [
    "541380",  # Testing Laboratories
    "541710",  # R&D in Physical/Engineering Sciences
    "811310",  # Commercial & Industrial Machinery Repair
]

# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------
REQUEST_DELAY = 1.0   # OSHA is a government site — be polite
MAX_RETRIES = 3
BACKFILL_YEAR = 2022
WEEKLY_LOOKBACK_DAYS = 30

# ---------------------------------------------------------------------------
# CSV field names
# ---------------------------------------------------------------------------
INSPECTION_FIELDS = [
    "activity_nr", "date_opened", "state", "inspection_type", "scope",
    "naics_code", "violations_count", "establishment_name",
    "search_source", "fetch_date",
]
VIOLATION_FIELDS = [
    "activity_nr", "citation_id", "citation_type", "standard_cited",
    "issuance_date", "abatement_due_date", "current_penalty",
    "initial_penalty", "latest_event", "fetch_date",
]


# ===================================================================
# Logging
# ===================================================================
def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = LOG_DIR / f"osha_fetcher_{date_str}.log"

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)

    logger = logging.getLogger("osha_fetcher")
    logger.setLevel(logging.INFO)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


# ===================================================================
# HTTP
# ===================================================================
def osha_request(url, logger, data=None):
    """Make a rate-limited request to OSHA. Returns HTML string or None."""
    headers = {
        "User-Agent": "InspectionIntel RobertTooley __ADMIN_EMAIL__",
        "Accept": "text/html,application/xhtml+xml,*/*",
    }
    if data:
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    for attempt in range(MAX_RETRIES):
        try:
            req = Request(url, data=data, headers=headers)
            with urlopen(req, timeout=30, context=SSL_CTX) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except HTTPError as e:
            if e.code == 429:
                wait = 5 * (attempt + 1)
                logger.warning(f"Rate limited (429). Retrying in {wait}s …")
                time.sleep(wait)
                continue
            logger.error(f"HTTP {e.code}: {url}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2)
                continue
            return None
        except (URLError, OSError) as e:
            logger.error(f"Network error: {e} — {url}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(3)
                continue
            return None
    return None


# ===================================================================
# Search OSHA by establishment name
# ===================================================================
def search_by_establishment(company_name, start_date, logger):
    """Search OSHA for inspections of a company. Returns list of inspection dicts."""
    sd = datetime.strptime(start_date, "%Y-%m-%d")
    params = urlencode({
        "p_logger": "1",
        "establishment": company_name,
        "State": "all",
        "officetype": "",
        "Office": "",
        "sitezip": "",
        "startmonth": f"{sd.month:02d}",
        "startday": f"{sd.day:02d}",
        "startyear": str(sd.year),
        "endmonth": "",
        "endday": "",
        "endyear": "",
        "p_case": "all",
        "p_violations_exist": "",
    }).encode("utf-8")

    time.sleep(REQUEST_DELAY)
    html = osha_request(OSHA_SEARCH_URL, logger, data=params)
    if not html:
        return []

    return parse_search_results(html, f"company:{company_name}")


# ===================================================================
# Search OSHA by NAICS code
# ===================================================================
def search_by_naics(naics_code, start_date, logger):
    """Search OSHA for inspections in a NAICS code. Returns list of inspection dicts."""
    url = "https://www.osha.gov/ords/imis/industry.search"
    sd = datetime.strptime(start_date, "%Y-%m-%d")
    params = urlencode({
        "p_logger": "1",
        "naession": naics_code,
        "State": "all",
        "officetype": "",
        "Office": "",
        "sitezip": "",
        "startmonth": f"{sd.month:02d}",
        "startday": f"{sd.day:02d}",
        "startyear": str(sd.year),
        "endmonth": "",
        "endday": "",
        "endyear": "",
        "p_case": "all",
        "p_violations_exist": "",
    }).encode("utf-8")

    time.sleep(REQUEST_DELAY)
    html = osha_request(url, logger, data=params)
    if not html:
        return []

    return parse_search_results(html, f"naics:{naics_code}")


# ===================================================================
# Parse search result HTML
# ===================================================================
def parse_search_results(html, search_source):
    """Parse OSHA search result HTML into list of inspection dicts."""
    inspections = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)

    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        if len(cells) < 8:
            continue

        clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]

        # Extract activity_nr from link
        link_match = re.search(
            r'inspection_detail\?id=([0-9.]+)', row
        )
        if not link_match:
            continue

        activity_nr = link_match.group(1)

        # Row structure: ['', '#', activity_nr, date, RID, ST, Type, Scope, SIC, NAICS, Violations, Name]
        # But column count varies — find by position relative to activity_nr
        try:
            # Find index of activity_nr in clean cells
            act_idx = None
            for i, c in enumerate(clean):
                if c == activity_nr:
                    act_idx = i
                    break

            if act_idx is None:
                continue

            date_opened = clean[act_idx + 1] if act_idx + 1 < len(clean) else ""
            state = clean[act_idx + 3] if act_idx + 3 < len(clean) else ""
            insp_type = clean[act_idx + 4] if act_idx + 4 < len(clean) else ""
            scope = clean[act_idx + 5] if act_idx + 5 < len(clean) else ""
            naics = clean[act_idx + 7] if act_idx + 7 < len(clean) else ""
            violations = clean[act_idx + 8] if act_idx + 8 < len(clean) else ""
            estab_name = clean[-1] if clean[-1] else ""

            # Clean up non-breaking spaces
            for field in [naics, violations, estab_name]:
                field = field.replace("\xa0", "").replace("&nbsp;", "")

            inspections.append({
                "activity_nr": activity_nr,
                "date_opened": date_opened,
                "state": state,
                "inspection_type": insp_type,
                "scope": scope,
                "naics_code": naics.replace("\xa0", "").replace("&nbsp;", ""),
                "violations_count": violations.replace("\xa0", "").replace("&nbsp;", ""),
                "establishment_name": estab_name.replace("\xa0", "").replace("&nbsp;", ""),
                "search_source": search_source,
                "fetch_date": datetime.now().strftime("%Y-%m-%d"),
            })
        except (IndexError, ValueError):
            continue

    return inspections


# ===================================================================
# Fetch violation details for an inspection
# ===================================================================
def fetch_violations(activity_nr, logger):
    """Fetch the detail page for an inspection and extract violations."""
    url = OSHA_DETAIL_URL.format(activity_nr=activity_nr)
    time.sleep(REQUEST_DELAY)
    html = osha_request(url, logger)
    if not html:
        return []

    violations = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)

    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        if len(cells) < 8:
            continue

        clean = [re.sub(r"<[^>]+>", "", c).strip().replace("\xa0", "").replace("&nbsp;", "") for c in cells]

        # Violation rows have a citation ID like "01001", "01002" etc.
        if not clean[0]:
            continue
        if not re.match(r"^\d{4,6}$", clean[0]):
            continue

        violations.append({
            "activity_nr": activity_nr,
            "citation_id": clean[0],
            "citation_type": clean[1] if len(clean) > 1 else "",
            "standard_cited": clean[2] if len(clean) > 2 else "",
            "issuance_date": clean[3] if len(clean) > 3 else "",
            "abatement_due_date": clean[4] if len(clean) > 4 else "",
            "current_penalty": clean[5] if len(clean) > 5 else "",
            "initial_penalty": clean[6] if len(clean) > 6 else "",
            "latest_event": clean[8] if len(clean) > 8 else "",
            "fetch_date": datetime.now().strftime("%Y-%m-%d"),
        })

    return violations


# ===================================================================
# CSV I/O
# ===================================================================
def load_existing_ids(csv_path, key_field):
    """Load set of existing IDs from a CSV file."""
    ids = set()
    if not csv_path.exists():
        return ids
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if key_field in row and row[key_field]:
                ids.add(row[key_field])
    return ids


def append_to_csv(csv_path, fieldnames, rows):
    """Append rows to a CSV file, creating with headers if new."""
    file_exists = csv_path.exists() and csv_path.stat().st_size > 0
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


# ===================================================================
# Registry
# ===================================================================
def load_companies():
    """Load active companies from the registry."""
    with open(REGISTRY_FILE, "r") as f:
        data = json.load(f)
    return [c for c in data["companies"] if c.get("active", True)]


# ===================================================================
# Main
# ===================================================================
def main():
    parser = argparse.ArgumentParser(
        description="OSHA Inspection Fetcher — Inspection Intel"
    )
    parser.add_argument("--backfill", action="store_true",
                        help="Fetch all inspections since 2022")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be fetched")
    parser.add_argument("--company", type=str,
                        help="Single company ticker (e.g. CLH)")
    parser.add_argument("--skip-naics", action="store_true",
                        help="Skip NAICS industry-wide searches")
    parser.add_argument("--skip-violations", action="store_true",
                        help="Skip fetching violation details")
    args = parser.parse_args()

    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("OSHA Inspection Fetcher — Inspection Intel")
    mode = "Backfill" if args.backfill else "Weekly"
    if args.dry_run:
        mode += " (DRY RUN)"
    logger.info(f"Mode: {mode}")
    logger.info("=" * 60)

    OSHA_DIR.mkdir(parents=True, exist_ok=True)

    # Date range
    if args.backfill:
        start_date = f"{BACKFILL_YEAR}-01-01"
    else:
        start_date = (datetime.now() - timedelta(days=WEEKLY_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    # Load existing inspection IDs for dedup
    existing_ids = load_existing_ids(INSPECTIONS_CSV, "activity_nr")
    existing_viol_keys = set()
    if VIOLATIONS_CSV.exists():
        with open(VIOLATIONS_CSV, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = f"{row.get('activity_nr', '')}_{row.get('citation_id', '')}"
                existing_viol_keys.add(key)

    logger.info(f"Existing inspections on disk: {len(existing_ids)}")
    logger.info(f"Existing violations on disk: {len(existing_viol_keys)}")

    all_inspections = []
    all_violations = []

    # 1. Search by company name
    companies = load_companies()
    if args.company:
        companies = [c for c in companies if c["ticker"].upper() == args.company.upper()]

    for company in companies:
        name = company["name"]
        ticker = company["ticker"]
        logger.info(f"Searching OSHA for: {name} ({ticker})")

        results = search_by_establishment(name, start_date, logger)
        new = [r for r in results if r["activity_nr"] not in existing_ids]
        logger.info(f"  [{ticker}] {len(results)} results, {len(new)} new")

        for r in new:
            existing_ids.add(r["activity_nr"])
            all_inspections.append(r)

    # 2. Search by NAICS codes (industry-wide)
    if not args.skip_naics and not args.company:
        for naics in NAICS_CODES:
            logger.info(f"Searching OSHA NAICS: {naics}")
            results = search_by_naics(naics, start_date, logger)
            new = [r for r in results if r["activity_nr"] not in existing_ids]
            logger.info(f"  [NAICS {naics}] {len(results)} results, {len(new)} new")

            for r in new:
                existing_ids.add(r["activity_nr"])
                all_inspections.append(r)

    # 3. Fetch violation details for new inspections
    if not args.skip_violations:
        for insp in all_inspections:
            act = insp["activity_nr"]
            if args.dry_run:
                logger.info(f"  [DRY RUN] Would fetch violations for {act}")
                continue

            viols = fetch_violations(act, logger)
            new_viols = [
                v for v in viols
                if f"{v['activity_nr']}_{v['citation_id']}" not in existing_viol_keys
            ]
            if new_viols:
                logger.info(f"  {act}: {len(new_viols)} violations")
                all_violations.extend(new_viols)
                for v in new_viols:
                    existing_viol_keys.add(f"{v['activity_nr']}_{v['citation_id']}")

    # 4. Write to CSV
    if not args.dry_run:
        if all_inspections:
            append_to_csv(INSPECTIONS_CSV, INSPECTION_FIELDS, all_inspections)
        if all_violations:
            append_to_csv(VIOLATIONS_CSV, VIOLATION_FIELDS, all_violations)

    # Summary
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info(f"  New inspections  : {len(all_inspections)}")
    logger.info(f"  New violations   : {len(all_violations)}")
    if args.dry_run:
        logger.info("  (DRY RUN — nothing written to disk)")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
