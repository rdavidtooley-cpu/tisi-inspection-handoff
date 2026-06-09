#!/usr/bin/env python3
"""
Fetch SEC EDGAR filings for every Intel site (except Inspection, which already
has its own pipeline) and splice the resulting articles into each site's
deployed News Dashboard HTML.

Why: the SEC Filings tab added by `add_sec_filings_tab.py` filters
`NEWS_DATA.articles` for source/p == "SEC EDGAR". Inspection's pipeline
already emits those rows; the other 12 sites have empty SEC tabs until we
inject EDGAR data here.

This script:
  1. Walks every `*_Intel/_scripts/edgar_company_registry.json`.
  2. For each active+CIK company, hits SEC EDGAR's Atom feed and pulls
     up to N most recent filings.
  3. Reads the deployed `*_News_Dashboard.html`, finds `NEWS_DATA = {...}`,
     parses, removes any prior SEC EDGAR rows, prepends fresh ones, and
     writes back.
  4. Auto-detects each site's article schema (compact `t,s,d,p,...` vs full
     `title,source,...`) by inspecting the first non-EDGAR article.

Idempotent — safe to run repeatedly. Re-running just refreshes the EDGAR
slice. Designed to run daily after morning refreshes; morning refresh
rebuilds NEWS_DATA from CSV/JSON sources without EDGAR, then this script
re-splices EDGAR rows on top.

Usage:
    python3 edgar_news_injector.py                # dry-run (default)
    python3 edgar_news_injector.py --apply        # write changes
    python3 edgar_news_injector.py --apply --site Oil_Gas_Intel  # one site
    python3 edgar_news_injector.py --max 5        # cap filings per ticker
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import time
from datetime import datetime
from html import unescape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

import certifi  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
SSL_CTX = ssl.create_default_context(cafile=certifi.where())
USER_AGENT = "__PROJECT_NAME__ News Injector __ADMIN_EMAIL__"
REQUEST_DELAY = 2.0  # seconds; SEC asks for <=10 req/s but we're polite
MAX_RETRIES = 3
DEFAULT_MAX_PER_TICKER = 10

# Sites to process. Inspection has its own pipeline. Media has a non-tabbed
# News Dashboard with no Company Headlines tab.
SITES = [
    'Aerospace_Defense_Intel',
    'Autos_Intel',
    'Casino_Gaming_Intel',
    'Chemicals_Intel',
    'Homebuilders_Intel',
    'Metal_Mining_Intel',
    'Oil_Gas_Intel',
    'Power_Utilities_Intel',
    'REITs_Intel',
    'Rail_Logistics_Intel',
    'Semiconductors_Intel',
    'Shipping_Intel',
]

# News Dashboard filename per site (matches add_sec_filings_tab.py SITES list)
DASHBOARD_NAME = {
    'Aerospace_Defense_Intel': 'AD_News_Dashboard.html',
    'Autos_Intel': 'AUTO_News_Dashboard.html',
    'Casino_Gaming_Intel': 'CG_News_Dashboard.html',
    'Chemicals_Intel': 'CHM_News_Dashboard.html',
    'Homebuilders_Intel': 'HOME_News_Dashboard.html',
    'Metal_Mining_Intel': 'MM_News_Dashboard.html',
    'Oil_Gas_Intel': 'OG_News_Dashboard.html',
    'Power_Utilities_Intel': 'PU_News_Dashboard.html',
    'REITs_Intel': 'REIT_News_Dashboard.html',
    'Rail_Logistics_Intel': 'RL_News_Dashboard.html',
    'Semiconductors_Intel': 'SEMI_News_Dashboard.html',
    'Shipping_Intel': 'SHP_News_Dashboard.html',
}

# ---------------------------------------------------------------- HTTP
def fetch_url(url: str) -> str | None:
    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'application/atom+xml,text/xml,*/*',
    }
    for attempt in range(MAX_RETRIES):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=30, context=SSL_CTX) as resp:
                return resp.read().decode('utf-8', errors='replace')
        except HTTPError as e:
            if e.code == 429:
                time.sleep(5 + attempt * 5)
                continue
            print(f'    HTTP {e.code}: {url}', file=sys.stderr)
            return None
        except (URLError, OSError) as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(3)
                continue
            print(f'    Network error: {e}', file=sys.stderr)
            return None
    return None


# ---------------------------------------------------------------- EDGAR fetch
def fetch_edgar_for_company(cik: str, ticker: str, name: str, max_per_ticker: int) -> list[dict]:
    """Return a list of filings as full-schema dicts."""
    cik_padded = str(cik).lstrip('0')
    url = (
        f'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany'
        f'&CIK={cik_padded}&type=&dateb=&owner=include&count=40&output=atom'
    )
    time.sleep(REQUEST_DELAY)
    xml_text = fetch_url(url)
    if not xml_text:
        return []
    try:
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    out: list[dict] = []
    for entry in root.findall('atom:entry', ns)[:max_per_ticker]:
        title_el = entry.find('atom:title', ns)
        link_el = entry.find('atom:link', ns)
        updated_el = entry.find('atom:updated', ns)
        summary_el = entry.find('atom:summary', ns)

        title = (title_el.text or '').strip() if title_el is not None else ''
        link = link_el.get('href', '') if link_el is not None else ''
        date_str = ''
        if updated_el is not None and updated_el.text:
            try:
                dt = datetime.fromisoformat(updated_el.text.replace('Z', '+00:00'))
                date_str = dt.strftime('%Y-%m-%d')
            except (ValueError, TypeError):
                date_str = updated_el.text[:10]

        summary = ''
        if summary_el is not None and summary_el.text:
            raw = unescape(summary_el.text)
            summary = re.sub(r'<[^>]+>', '', raw).strip()
            summary = ' '.join(summary.split())[:200]

        if title and link:
            out.append({
                'date': date_str,
                'source': 'SEC EDGAR',
                'title': title,
                'url': link,
                'summary': summary,
                'company': name,
                'ticker': ticker,
            })
    return out


def fetch_all_for_site(site: str, max_per_ticker: int) -> list[dict]:
    registry_path = ROOT / site / '_scripts' / 'edgar_company_registry.json'
    if not registry_path.exists():
        return []
    data = json.loads(registry_path.read_text())
    companies = data.get('companies', [])
    rows: list[dict] = []
    for c in companies:
        if not c.get('active') or not c.get('cik'):
            continue
        ticker = c.get('ticker', '')
        name = c.get('name', ticker)
        rows.extend(fetch_edgar_for_company(c['cik'], ticker, name, max_per_ticker))
    return rows


# ---------------------------------------------------------------- HTML splice
NEWS_DATA_RE = re.compile(r'(\bvar\s+NEWS_DATA\s*=\s*)(\{)', re.MULTILINE)


def find_news_data_block(html: str) -> tuple[int, int] | None:
    """Return (start, end) indices of the JSON object in `var NEWS_DATA = {...};`.

    `start` is the index of the opening `{`; `end` is index of the matching
    closing `}` plus 1.
    """
    m = NEWS_DATA_RE.search(html)
    if not m:
        return None
    start = m.start(2)  # the '{'
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(html)):
        ch = html[i]
        if escape:
            escape = False
            continue
        if in_str:
            if ch == '\\':
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return start, i + 1
    return None


def to_compact_row(r: dict) -> dict:
    """Convert a full-schema EDGAR row to the OG/scaffolded compact schema."""
    return {
        't': r.get('title', ''),
        's': r.get('summary', ''),
        'd': r.get('date', ''),
        'p': 'SEC EDGAR',
        'u': r.get('url', ''),
        'tc': 1,
        'tk': [r.get('ticker', '')],
        'ss': [],
        'c': 'Company-Specific',
    }


def to_full_row(r: dict) -> dict:
    """Match the Casino/Mining schema (full keys + matched_tickers list)."""
    return {
        'title': r.get('title', ''),
        'url': r.get('url', ''),
        'source': 'SEC EDGAR',
        'published': r.get('date', ''),
        'matched_tickers': [r.get('ticker', '')],
        'sector': '',
        'category': 'Company-Specific',
        'relevance_score': 5.0,
        'company': r.get('company', ''),
        'ticker': r.get('ticker', ''),
        'summary': r.get('summary', ''),
    }


def detect_schema(articles: list[dict]) -> str:
    """Return 'compact' or 'full' based on existing articles' keys.

    Looks at the first non-EDGAR article. Falls back to 'full' on empty.
    """
    for a in articles:
        if not isinstance(a, dict):
            continue
        # Skip our own prior injections
        src = (a.get('source') or a.get('p') or '').lower()
        if src == 'sec edgar':
            continue
        if 't' in a and 'd' in a and 'p' in a:
            return 'compact'
        if 'title' in a and 'source' in a:
            return 'full'
    return 'full'


def splice(html: str, edgar_rows: list[dict]) -> tuple[str, str]:
    """Return (new_html, status). status: 'patched', 'no_news_data', or 'error: ...'."""
    span = find_news_data_block(html)
    if span is None:
        return html, 'no_news_data'
    start, end = span
    raw = html[start:end]
    try:
        nd = json.loads(raw)
    except json.JSONDecodeError as e:
        return html, f'error: NEWS_DATA JSON parse failed at offset {start}: {e}'

    articles = nd.get('articles', [])
    if not isinstance(articles, list):
        return html, 'error: NEWS_DATA.articles is not a list'

    # Strip prior EDGAR rows
    def is_edgar(a: dict) -> bool:
        if not isinstance(a, dict):
            return False
        return (a.get('source') or a.get('p') or '').lower() == 'sec edgar'

    cleaned = [a for a in articles if not is_edgar(a)]

    # Detect schema and convert EDGAR rows
    schema = detect_schema(cleaned) if cleaned else (
        'compact' if 'compact' in html and 'NEWS_DATA' in html and "'p'" in raw else 'full'
    )
    if schema == 'compact':
        new_rows = [to_compact_row(r) for r in edgar_rows]
    else:
        new_rows = [to_full_row(r) for r in edgar_rows]

    # Prepend EDGAR rows so they're visible without scrolling, then keep
    # original order for the rest. Cap total at the same length as before
    # if we'd exceed it (avoid unbounded growth on rerun).
    cap = max(len(articles), len(new_rows) + len(cleaned))
    nd['articles'] = (new_rows + cleaned)[:cap]

    new_raw = json.dumps(nd, ensure_ascii=False, separators=(',', ':'))
    new_html = html[:start] + new_raw + html[end:]
    return new_html, f'patched ({schema}, +{len(new_rows)} edgar rows)'


# ---------------------------------------------------------------- driver
def process_site(site: str, max_per_ticker: int, apply: bool) -> dict:
    dash = ROOT / site / 'Dashboard' / DASHBOARD_NAME[site]
    if not dash.exists():
        return {'site': site, 'status': 'error: dashboard not found', 'edgar': 0}
    print(f'\n[{site}] fetching EDGAR feeds...', flush=True)
    rows = fetch_all_for_site(site, max_per_ticker)
    print(f'[{site}] fetched {len(rows)} EDGAR rows', flush=True)
    html = dash.read_text()
    new_html, status = splice(html, rows)
    print(f'[{site}] splice: {status}', flush=True)
    if apply and new_html != html and not status.startswith('error') and status != 'no_news_data':
        dash.write_text(new_html)
    return {'site': site, 'status': status, 'edgar': len(rows)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='write changes (default: dry-run)')
    ap.add_argument('--max', type=int, default=DEFAULT_MAX_PER_TICKER,
                    help='max filings per ticker (default 10)')
    ap.add_argument('--site', help='process only this site')
    args = ap.parse_args()

    sites = [args.site] if args.site else SITES
    results = []
    for site in sites:
        if site not in DASHBOARD_NAME:
            print(f'skipping unknown site: {site}', file=sys.stderr)
            continue
        results.append(process_site(site, args.max, args.apply))

    print('\n=== Summary ===')
    for r in results:
        print(f"  {r['site']:30} {r['edgar']:4d} rows  {r['status']}")
    if not args.apply:
        print('\nDry-run only. Re-run with --apply to write changes.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
