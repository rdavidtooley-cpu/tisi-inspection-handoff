#!/usr/bin/env python3
"""Nightly 8-K M&A scanner for EDGAR.

Usage: python3 fetch_ma_edgar.py <SiteFolder>
  e.g. python3 fetch_ma_edgar.py Inspection_Intel

Reads {site}/_scripts/edgar_company_registry.json for CIKs.
For each active CIK, fetches the EDGAR submissions JSON and filters
for 8-K filings with Item 1.01 (Material Definitive Agreement) or
2.01 (Completion of Acquisition). Parses the primary HTML document
to extract target, value_m, and status. Writes to:
  {site}/Dashboard/ma_deals_edgar.json

Rate limit: 0.15s between requests (< 10 req/sec per SEC policy).
User-Agent header is required by SEC; uses the one in the registry.
"""

import json
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# How far back to scan (days)
LOOKBACK_DAYS = 90
# Seconds between EDGAR API calls
RATE_LIMIT = 0.15

# Items that indicate M&A activity
MA_ITEMS = {"1.01", "2.01"}

# Phrases that precede a target company name
TARGET_PHRASES = [
    r"acquire[sd]?\s+(?:all\s+of\s+the\s+outstanding\s+(?:shares|interests)\s+of\s+)?",
    r"acquisition\s+of\s+",
    r"agreement\s+to\s+acquire\s+",
    r"purchase\s+(?:all\s+of\s+the\s+outstanding\s+shares\s+of\s+)?(?:the\s+)?",
    r"merger\s+with\s+",
    r"acquired\s+",
    r"to\s+purchase\s+(?:all\s+of\s+the\s+outstanding\s+shares\s+of\s+)?",
]

# Phrases that precede deal value
VALUE_PHRASES = [
    r"purchase\s+price\s+of\s+approximately\s+",
    r"aggregate\s+(?:purchase\s+price|consideration|merger\s+consideration)\s+of\s+approximately\s+",
    r"total\s+(?:consideration|purchase\s+price)\s+of\s+approximately\s+",
    r"aggregate\s+value\s+of\s+approximately\s+",
    r"consideration\s+of\s+approximately\s+",
    r"valued\s+at\s+approximately\s+",
    r"aggregate\s+merger\s+consideration\s+of\s+",
    r"for\s+approximately\s+",
    r"aggregate\s+transaction\s+value\s+of\s+approximately\s+",
]


# ─────────────────────────── helpers ───────────────────────────

def _ua(registry: dict) -> str:
    return registry.get("user_agent", "MasterIntelligence __ADMIN_EMAIL__")


def _get(url: str, ua: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "application/json,text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            return b""
        raise


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode common entities."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&amp;", "&").replace("&nbsp;", " ").replace("&#160;", " ")
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return re.sub(r"\s+", " ", text).strip()


def _extract_target(text: str) -> str | None:
    """Find the target company name after known acquisition phrases."""
    for phrase in TARGET_PHRASES:
        m = re.search(phrase + r'([A-Z][A-Za-z0-9&,\'\. ]{3,60}?)(?:\s*[,\.;]|\s+for\s+|\s+in\s+a|\s+(?:a|an)\s+transaction)',
                      text, re.IGNORECASE)
        if m:
            target = m.group(1).strip().rstrip(".,;")
            # Filter out generic phrases
            low = target.lower()
            skip = {"the company", "all", "certain", "its", "our", "their", "such", "each", "any"}
            if low in skip or len(target) < 3:
                continue
            # Must start with capital letter
            if not target[0].isupper():
                continue
            return target
    return None


def _extract_value_m(text: str) -> float | None:
    """Extract dollar value in millions."""
    for phrase in VALUE_PHRASES:
        m = re.search(phrase + r'\$\s*([\d,]+(?:\.\d+)?)\s*(million|billion|bn|mm)',
                      text, re.IGNORECASE)
        if m:
            raw = float(m.group(1).replace(",", ""))
            unit = m.group(2).lower()
            if unit in ("billion", "bn"):
                return round(raw * 1000, 1)
            return round(raw, 1)
    # Fallback: any $X million/billion
    m = re.search(r'\$\s*([\d,]+(?:\.\d+)?)\s*(million|billion|bn|mm)',
                  text, re.IGNORECASE)
    if m:
        raw = float(m.group(1).replace(",", ""))
        unit = m.group(2).lower()
        if unit in ("billion", "bn"):
            return round(raw * 1000, 1)
        return round(raw, 1)
    return None


def _items_has_ma(items_str: str) -> bool:
    """Check if filings items string contains 1.01 or 2.01."""
    if not items_str:
        return False
    for item in MA_ITEMS:
        if item in items_str:
            return True
    return False


# ─────────────────────────── core scanner ───────────────────────────

def scan_site(site_folder: str) -> list:
    """Scan EDGAR for M&A 8-K filings for a given site's ticker universe."""
    site_dir = BASE / site_folder
    registry_path = site_dir / "_scripts" / "edgar_company_registry.json"
    if not registry_path.exists():
        print(f"ERROR: No registry at {registry_path}")
        sys.exit(1)

    with open(registry_path) as f:
        registry = json.load(f)

    ua = _ua(registry)
    cutoff = datetime.now() - timedelta(days=LOOKBACK_DAYS)

    # Import make_deal_id from ma_core
    sys.path.insert(0, str(Path(__file__).parent))
    from ma_core import make_deal_id

    deals = []
    active_companies = [c for c in registry["companies"] if c.get("active") and c.get("cik")]
    print(f"{site_folder}: scanning {len(active_companies)} active CIKs...")

    for company in active_companies:
        cik = company["cik"]
        ticker = company["ticker"]
        # Registry schema varies: Inspection uses "name", Casino/Metal use "folder" as label
        name = company.get("name") or company.get("folder", ticker).replace("_", " ")

        # Fetch submissions JSON
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        time.sleep(RATE_LIMIT)
        raw = _get(url, ua)
        if not raw:
            print(f"  {ticker}: submissions fetch failed (empty response)")
            continue

        try:
            sub = json.loads(raw)
        except json.JSONDecodeError:
            print(f"  {ticker}: JSON decode error")
            continue

        filings = sub.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        dates = filings.get("filingDate", [])
        accessions = filings.get("accessionNumber", [])
        primary_docs = filings.get("primaryDocument", [])
        items_list = filings.get("items", [])

        hit_count = 0
        for i, form in enumerate(forms):
            if form != "8-K":
                continue
            filing_date_str = dates[i] if i < len(dates) else ""
            if not filing_date_str:
                continue
            try:
                filing_date = datetime.strptime(filing_date_str, "%Y-%m-%d")
            except ValueError:
                continue
            if filing_date < cutoff:
                # Filings are sorted newest first — once we go past cutoff, done
                break

            items_str = items_list[i] if i < len(items_list) else ""
            if not _items_has_ma(items_str):
                continue

            # Determine status from item
            status = "completed" if "2.01" in str(items_str) else "pending"

            acc = accessions[i] if i < len(accessions) else ""
            primary_doc = primary_docs[i] if i < len(primary_docs) else ""
            acc_nodash = acc.replace("-", "")

            # Filing index URL
            cik_int = int(cik)
            index_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik_int}&type=8-K&dateb=&owner=include&count=40"
            source_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{primary_doc}"

            # Fetch primary document
            time.sleep(RATE_LIMIT)
            doc_raw = _get(source_url, ua)
            if not doc_raw:
                # Try fetching index to find the right document
                index_url2 = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/"
                time.sleep(RATE_LIMIT)
                doc_raw = _get(index_url2, ua)

            if not doc_raw:
                continue

            try:
                doc_text = doc_raw.decode("utf-8", errors="replace")
            except Exception:
                continue

            # Strip HTML for text parsing
            plain = _strip_html(doc_text)

            target = _extract_target(plain)
            if not target:
                continue  # Skip if we can't identify the target

            value_m = _extract_value_m(plain)
            deal_id = make_deal_id(name, target, filing_date_str)

            deal = {
                "id": deal_id,
                "date": filing_date_str,
                "acquirer": name,
                "acquirer_ticker": ticker,
                "target": target,
                "target_ticker": None,
                "value_m": value_m,
                "ev_revenue": None,
                "ev_ebitda": None,
                "sector": company.get("category", ""),
                "rationale": f"8-K filing: {form} Item {items_str}",
                "status": status,
                "source": "8-K",
                "source_url": source_url,
            }
            deals.append(deal)
            hit_count += 1
            print(f"  {ticker}: found deal → {name} → {target} ({filing_date_str}) ${value_m}M [{status}]")

        if hit_count == 0:
            pass  # Quiet — most tickers won't have M&A filings

    # Sort by date desc
    deals.sort(key=lambda x: x.get("date", ""), reverse=True)
    return deals


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 fetch_ma_edgar.py <SiteFolder>")
        print("  e.g. python3 fetch_ma_edgar.py Inspection_Intel")
        sys.exit(1)

    site_folder = sys.argv[1]
    deals = scan_site(site_folder)

    out_path = BASE / site_folder / "Dashboard" / "ma_deals_edgar.json"
    with open(out_path, "w") as f:
        json.dump(deals, f, indent=2)

    print(f"\nWrote {len(deals)} deals to {out_path}")


if __name__ == "__main__":
    main()
