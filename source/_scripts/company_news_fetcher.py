#!/usr/bin/env python3
"""
Company News Fetcher — Inspection Intel

Fetches company-specific press releases and filing alerts for tracked NDT companies.
Sources: SEC EDGAR RSS (new filing alerts), Company IR pages (press releases).

Output: Industry_Data/News/company_news.csv

Usage:
  python3 company_news_fetcher.py              # Fetch latest company news
  python3 company_news_fetcher.py --dry-run    # Show what would be fetched
"""

import csv
import json
import logging
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
from xml.etree import ElementTree as ET
from html import unescape

SSL_CTX = ssl.create_default_context(cafile=certifi.where())

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parent
NEWS_DIR = PROJECT_DIR / "Industry_Data" / "News"
LOG_DIR = SCRIPT_DIR / "logs"
REGISTRY_FILE = SCRIPT_DIR / "edgar_company_registry.json"

COMPANY_NEWS_CSV = NEWS_DIR / "company_news.csv"

# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------
REQUEST_DELAY = 2.0
MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# CSV fields (extends industry news with company/ticker fields)
# ---------------------------------------------------------------------------
NEWS_FIELDS = ["date", "source", "title", "url", "summary", "company", "ticker"]

USER_AGENT = "InspectionIntel RobertTooley __ADMIN_EMAIL__"

# ---------------------------------------------------------------------------
# Company IR page URLs for press releases
# ---------------------------------------------------------------------------
COMPANY_IR_PAGES = {
    'MG':       'https://ir.mistrasgroup.com/press-releases',
    'TISI':     'https://ir.teaminc.com/press-releases',
    'TIC':      'https://investors.acurengroup.com/press-releases',
    'OII':      'https://www.oceaneering.com/investor-relations/press-releases/',
    'XPRO':     'https://www.expro.com/investors/press-releases',
    'TRNS':     'https://investor.transcat.com/press-releases',
    'THR':      'https://ir.thermon.com/press-releases',
    'SGSN.SW':  'https://www.sgs.com/en/media-center/press-releases',
    'BVI.PA':   'https://group.bureauveritas.com/newsroom/press-releases',
    'ITRK.L':   'https://www.intertek.com/investors/regulatory-news/',
    'COTN.SW':  'https://www.comet-group.com/en/investors/news-events',
}


# ===================================================================
# Logging
# ===================================================================
def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = LOG_DIR / f"company_news_fetcher_{date_str}.log"

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)

    logger = logging.getLogger("company_news_fetcher")
    logger.setLevel(logging.INFO)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


# ===================================================================
# HTTP
# ===================================================================
def fetch_url(url, logger):
    """Rate-limited GET. Returns string or None."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    for attempt in range(MAX_RETRIES):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=30, context=SSL_CTX) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except HTTPError as e:
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
# Load registry
# ===================================================================
def load_registry(logger):
    """Load company registry."""
    if not REGISTRY_FILE.exists():
        logger.error(f"Registry not found: {REGISTRY_FILE}")
        return []
    with open(REGISTRY_FILE, "r") as f:
        data = json.load(f)
    return data.get("companies", [])


# ===================================================================
# Source: SEC EDGAR RSS (new filing alerts)
# ===================================================================
def fetch_edgar_rss(company, logger):
    """Fetch SEC EDGAR RSS feed for new filings of a company."""
    cik = company.get("cik")
    if not cik:
        return []

    ticker = company.get("ticker", "")
    name = company.get("name", "")
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=&dateb=&owner=include&count=40&search_text=&action=getcompany&output=atom"

    logger.info(f"  Fetching EDGAR RSS for {name} ({ticker})")
    time.sleep(REQUEST_DELAY)
    xml_text = fetch_url(url, logger)
    if not xml_text:
        return []

    articles = []
    try:
        # EDGAR Atom feed
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        root = ET.fromstring(xml_text)
        for entry in root.findall('atom:entry', ns):
            title_el = entry.find('atom:title', ns)
            link_el = entry.find('atom:link', ns)
            updated_el = entry.find('atom:updated', ns)
            summary_el = entry.find('atom:summary', ns)

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            link = link_el.get('href', '') if link_el is not None else ""
            date_str = ""
            if updated_el is not None and updated_el.text:
                try:
                    dt = datetime.fromisoformat(updated_el.text.replace('Z', '+00:00'))
                    date_str = dt.strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    date_str = updated_el.text[:10]

            summary = ""
            if summary_el is not None and summary_el.text:
                raw = unescape(summary_el.text)
                summary = re.sub(r"<[^>]+>", "", raw).strip()
                summary = " ".join(summary.split())[:200]

            if title and link:
                articles.append({
                    "date": date_str,
                    "source": "SEC EDGAR",
                    "title": title,
                    "url": link,
                    "summary": summary,
                    "company": name,
                    "ticker": ticker,
                })
    except ET.ParseError as e:
        logger.error(f"EDGAR RSS parse error for {ticker}: {e}")

    logger.info(f"    {ticker}: {len(articles)} EDGAR entries found")
    return articles


# ===================================================================
# Source: Company IR Pages (press releases)
# ===================================================================
def fetch_company_ir(ticker, name, ir_url, logger):
    """Scrape company IR page for press release links."""
    logger.info(f"  Fetching IR page for {name} ({ticker})")
    time.sleep(REQUEST_DELAY)
    html = fetch_url(ir_url, logger)
    if not html:
        return []

    articles = []
    seen_urls = set()

    # Generic pattern: look for links with press-release or news keywords in the URL
    patterns = [
        r'<a[^>]*href="([^"]*(?:press-release|news|newsroom|announcement)[^"]*)"[^>]*>(.*?)</a>',
        r'<a[^>]*href="(https?://[^"]*)"[^>]*class="[^"]*(?:press|news|release)[^"]*"[^>]*>(.*?)</a>',
    ]

    for pattern in patterns:
        links = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
        for href, link_text in links:
            title = re.sub(r"<[^>]+>", "", link_text).strip()
            if not title or len(title) < 15:
                continue

            url = href if href.startswith("http") else f"{ir_url.rstrip('/')}/{href.lstrip('/')}"
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Skip navigation/generic links
            lower = title.lower()
            if lower in ("press releases", "read more", "view all", "see more", "more news"):
                continue

            articles.append({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "source": "Company IR",
                "title": title,
                "url": url,
                "summary": "",
                "company": name,
                "ticker": ticker,
            })

    logger.info(f"    {ticker}: {len(articles)} IR articles found")
    return articles


# ===================================================================
# Source: Yahoo Finance RSS (company news stories)
# ===================================================================
YAHOO_TICKERS = ['MG', 'TISI', 'TIC', 'OII', 'XPRO', 'TRNS', 'THR',
                  'SGSN.SW', 'BVI.PA', 'ITRK.L', 'COTN.SW']
YAHOO_INTL_NAMES = {
    'SGSN.SW': 'SGS SA', 'BVI.PA': 'Bureau Veritas',
    'ITRK.L': 'Intertek Group', 'COTN.SW': 'Comet Group',
}

def fetch_yahoo_finance_news(ticker, name, logger):
    """Fetch Yahoo Finance RSS feed for company news headlines."""
    url = f"https://finance.yahoo.com/rss/headline?s={ticker}"
    logger.info(f"  Fetching Yahoo Finance news for {name} ({ticker})")
    time.sleep(REQUEST_DELAY)
    xml_text = fetch_url(url, logger)
    if not xml_text:
        return []

    articles = []
    try:
        root = ET.fromstring(xml_text)
        channel = root.find('channel')
        if channel is None:
            return []

        for item in channel.findall('item'):
            title_el = item.find('title')
            link_el = item.find('link')
            pubdate_el = item.find('pubDate')
            desc_el = item.find('description')

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            link = link_el.text.strip() if link_el is not None and link_el.text else ""

            date_str = ""
            if pubdate_el is not None and pubdate_el.text:
                try:
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(pubdate_el.text)
                    date_str = dt.strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    date_str = ""

            summary = ""
            if desc_el is not None and desc_el.text:
                raw = unescape(desc_el.text)
                summary = re.sub(r"<[^>]+>", "", raw).strip()
                summary = " ".join(summary.split())[:200]

            if title and link:
                articles.append({
                    "date": date_str,
                    "source": "Yahoo Finance",
                    "title": title,
                    "url": link,
                    "summary": summary,
                    "company": name,
                    "ticker": ticker,
                })
    except ET.ParseError as e:
        logger.error(f"Yahoo Finance RSS parse error for {ticker}: {e}")

    logger.info(f"    {ticker}: {len(articles)} Yahoo Finance articles found")
    return articles


# ===================================================================
# Source: Investegate RSS (UK RNS regulatory announcements)
# ===================================================================
INVESTEGATE_COMPANIES = {
    'ITRK': ('Intertek Group', 'ITRK.L'),
}


def fetch_investegate_rss(epic, name, ticker, logger):
    """Fetch Investegate RSS feed for UK-listed company RNS announcements."""
    url = f"https://www.investegate.co.uk/Rss.aspx?company={epic}"
    logger.info(f"  Fetching Investegate RNS for {name} ({epic})")
    time.sleep(REQUEST_DELAY)
    xml_text = fetch_url(url, logger)
    if not xml_text:
        return []

    articles = []
    try:
        # Investegate RSS may contain invalid XML chars; clean before parsing
        xml_clean = re.sub(r'[^\x09\x0A\x0D\x20-\x7E\x80-\uFFFF]', '', xml_text)
        # Also fix common XML issues like unescaped ampersands
        xml_clean = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#)', '&amp;', xml_clean)
        root = ET.fromstring(xml_clean)
        channel = root.find('channel')
        if channel is None:
            return []
        for item in channel.findall('item'):
            title_el = item.find('title')
            link_el = item.find('link')
            pubdate_el = item.find('pubDate')
            desc_el = item.find('description')

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            link = link_el.text.strip() if link_el is not None and link_el.text else ""

            date_str = ""
            if pubdate_el is not None and pubdate_el.text:
                try:
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(pubdate_el.text)
                    date_str = dt.strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    date_str = ""

            summary = ""
            if desc_el is not None and desc_el.text:
                raw = unescape(desc_el.text)
                summary = re.sub(r"<[^>]+>", "", raw).strip()
                summary = " ".join(summary.split())[:200]

            if title and link:
                articles.append({
                    "date": date_str,
                    "source": "Investegate",
                    "title": title,
                    "url": link,
                    "summary": summary,
                    "company": name,
                    "ticker": ticker,
                })
    except ET.ParseError as e:
        logger.error(f"Investegate RSS parse error for {epic}: {e}")

    logger.info(f"    {epic}: {len(articles)} Investegate articles found")
    return articles


# ===================================================================
# CSV I/O
# ===================================================================
def load_existing_urls(csv_path):
    """Load set of existing article URLs from CSV."""
    urls = set()
    if not csv_path.exists():
        return urls
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if "url" in row and row["url"]:
                urls.add(row["url"])
    return urls


def append_to_csv(csv_path, fieldnames, rows):
    """Append rows to CSV, creating with headers if new."""
    file_exists = csv_path.exists() and csv_path.stat().st_size > 0
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


# ===================================================================
# Main
# ===================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Company News Fetcher — Inspection Intel"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be fetched")
    args = parser.parse_args()

    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("Company News Fetcher — Inspection Intel")
    if args.dry_run:
        logger.info("Mode: DRY RUN")
    logger.info("=" * 60)

    NEWS_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing URLs for dedup
    existing_urls = load_existing_urls(COMPANY_NEWS_CSV)
    logger.info(f"Existing company news articles on disk: {len(existing_urls)}")

    # Load registry
    companies = load_registry(logger)
    logger.info(f"Companies in registry: {len(companies)}")

    all_articles = []

    # 1. SEC EDGAR RSS for active SEC filers
    logger.info("\n--- SEC EDGAR Filing Alerts ---")
    for company in companies:
        if not company.get("active") or not company.get("cik"):
            continue
        try:
            articles = fetch_edgar_rss(company, logger)
            all_articles.extend(articles)
        except Exception as e:
            logger.error(f"Error fetching EDGAR for {company.get('ticker')}: {e}")

    # 2. Yahoo Finance RSS for company news stories
    logger.info("\n--- Yahoo Finance Company News ---")
    for ticker in YAHOO_TICKERS:
        name = YAHOO_INTL_NAMES.get(ticker, ticker)
        for c in companies:
            if c.get("ticker") == ticker:
                name = c.get("name", ticker)
                break
        try:
            articles = fetch_yahoo_finance_news(ticker, name, logger)
            all_articles.extend(articles)
        except Exception as e:
            logger.error(f"Error fetching Yahoo Finance for {ticker}: {e}")

    # 3. Investegate RSS for UK-listed companies (RNS announcements)
    logger.info("\n--- Investegate UK RNS Announcements ---")
    for epic, (name, ticker) in INVESTEGATE_COMPANIES.items():
        try:
            articles = fetch_investegate_rss(epic, name, ticker, logger)
            all_articles.extend(articles)
        except Exception as e:
            logger.error(f"Error fetching Investegate for {epic}: {e}")

    # 4. Company IR pages for press releases
    logger.info("\n--- Company IR Press Releases ---")
    for ticker, ir_url in COMPANY_IR_PAGES.items():
        # Find company name from registry
        name = ticker
        for c in companies:
            if c.get("ticker") == ticker:
                name = c.get("name", ticker)
                break
        try:
            articles = fetch_company_ir(ticker, name, ir_url, logger)
            all_articles.extend(articles)
        except Exception as e:
            logger.error(f"Error fetching IR for {ticker}: {e}")

    # Dedup against existing
    new_articles = [a for a in all_articles if a["url"] not in existing_urls]
    logger.info(f"\nTotal articles found: {len(all_articles)}, new: {len(new_articles)}")

    # Write
    if not args.dry_run and new_articles:
        append_to_csv(COMPANY_NEWS_CSV, NEWS_FIELDS, new_articles)
        logger.info(f"Appended {len(new_articles)} articles to {COMPANY_NEWS_CSV.name}")
    elif args.dry_run:
        for a in new_articles[:10]:
            logger.info(f"  [DRY RUN] {a['source']}: {a['company']} — {a['title'][:60]}")
        if len(new_articles) > 10:
            logger.info(f"  ... and {len(new_articles) - 10} more")

    # Summary
    by_source = {}
    for a in new_articles:
        by_source[a["source"]] = by_source.get(a["source"], 0) + 1

    logger.info("=" * 60)
    logger.info("SUMMARY")
    for src, count in sorted(by_source.items()):
        logger.info(f"  {src}: {count} new articles")
    logger.info(f"  Total new: {len(new_articles)}")
    if args.dry_run:
        logger.info("  (DRY RUN — nothing written)")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
