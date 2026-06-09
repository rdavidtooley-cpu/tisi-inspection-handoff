#!/usr/bin/env python3
"""
Industry News Fetcher — Inspection Intel

Aggregates TIC/NDT industry news from multiple sources into a single CSV.
Sources: Metrology News (RSS), ASNT Newsroom (HTML), NDT.net (HTML).

Usage:
  python3 news_fetcher.py              # Fetch latest articles
  python3 news_fetcher.py --dry-run    # Show what would be fetched
  python3 news_fetcher.py --backfill   # Try to get more historical articles
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

NEWS_CSV = NEWS_DIR / "industry_news.csv"

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
METROLOGY_RSS = "https://metrology.news/feed/"
ASNT_NEWSROOM = "https://www.asnt.org/about/newsroom"
NDT_NET_HOME = "https://www.ndt.net/"
INSPECTIONEERING_NEWS = "https://inspectioneering.com/news"
QUALITY_MAG_NDT = "https://www.qualitymag.com/topics/2643-ndt"
ONESTOPNDT_NEWS = "https://www.onestopndt.com/ndt-news"

# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------
REQUEST_DELAY = 2.0   # Be polite to non-API sites
MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# CSV fields
# ---------------------------------------------------------------------------
NEWS_FIELDS = ["date", "source", "title", "url", "summary"]

USER_AGENT = "InspectionIntel RobertTooley __ADMIN_EMAIL__"


# ===================================================================
# Logging
# ===================================================================
def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = LOG_DIR / f"news_fetcher_{date_str}.log"

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)

    logger = logging.getLogger("news_fetcher")
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
# Source: Metrology & Quality News (RSS)
# ===================================================================
def fetch_metrology_news(logger):
    """Parse Metrology News RSS feed. Returns list of article dicts."""
    logger.info("Fetching Metrology & Quality News (RSS)")
    xml_text = fetch_url(METROLOGY_RSS, logger)
    if not xml_text:
        return []

    articles = []
    try:
        root = ET.fromstring(xml_text)
        for item in root.iter("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            pubdate_el = item.find("pubDate")
            desc_el = item.find("description")

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            link = link_el.text.strip() if link_el is not None and link_el.text else ""
            pub_date = ""
            if pubdate_el is not None and pubdate_el.text:
                pub_date = parse_rss_date(pubdate_el.text.strip())

            summary = ""
            if desc_el is not None and desc_el.text:
                # Strip HTML tags from description
                raw = unescape(desc_el.text)
                summary = re.sub(r"<[^>]+>", "", raw).strip()
                summary = " ".join(summary.split())[:200]

            if title and link:
                articles.append({
                    "date": pub_date,
                    "source": "Metrology News",
                    "title": title,
                    "url": link,
                    "summary": summary,
                })
    except ET.ParseError as e:
        logger.error(f"RSS parse error: {e}")

    logger.info(f"  Metrology News: {len(articles)} articles found")
    return articles


def parse_rss_date(date_str):
    """Parse RSS date like 'Wed, 26 Feb 2026 08:00:00 +0000' -> '2026-02-26'."""
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Fallback: try to extract date portion
    match = re.search(r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})", date_str)
    if match:
        try:
            dt = datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", "%d %b %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return date_str


# ===================================================================
# Source: ASNT Newsroom (HTML scrape)
# ===================================================================
def fetch_asnt_news(logger):
    """Scrape ASNT newsroom page for article listings."""
    logger.info("Fetching ASNT Newsroom (HTML)")
    time.sleep(REQUEST_DELAY)
    html = fetch_url(ASNT_NEWSROOM, logger)
    if not html:
        return []

    articles = []

    # ASNT uses full URLs for newsroom article links
    # Match both asnt.org and foundation.asnt.org newsroom links
    links = re.findall(
        r'<a[^>]*href="(https?://(?:www\.|foundation\.)?asnt\.org/about/newsroom/[^"?]+)"[^>]*>(.*?)</a>',
        html, re.DOTALL
    )

    seen_urls = set()
    for url, link_text in links:
        title = re.sub(r"<[^>]+>", "", link_text).strip()
        if not title or len(title) < 10:
            continue

        if url in seen_urls:
            continue
        seen_urls.add(url)

        # Skip generic navigation and archive links
        lower = title.lower()
        if lower in ("newsroom", "read more", "learn more", "view all"):
            continue
        if "newsroom" in lower and len(title) < 25:
            continue

        articles.append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "source": "ASNT",
            "title": title,
            "url": url,
            "summary": "",
        })

    logger.info(f"  ASNT: {len(articles)} articles found")
    return articles


# ===================================================================
# Source: NDT.net (HTML scrape)
# ===================================================================
def fetch_ndt_net_news(logger):
    """Scrape NDT.net for recent news and articles."""
    logger.info("Fetching NDT.net (HTML)")
    time.sleep(REQUEST_DELAY)
    html = fetch_url(NDT_NET_HOME, logger)
    if not html:
        return []

    articles = []
    seen_urls = set()

    # NDT.net lists articles with links to /article/ or /news/ paths
    # Also has forum posts and announcements
    patterns = [
        r'<a[^>]*href="(https?://www\.ndt\.net/article/[^"]+)"[^>]*>(.*?)</a>',
        r'<a[^>]*href="(https?://www\.ndt\.net/search/docs\.php3\?[^"]+)"[^>]*>(.*?)</a>',
        r'<a[^>]*href="(/article/[^"]+)"[^>]*>(.*?)</a>',
    ]

    for pattern in patterns:
        links = re.findall(pattern, html, re.DOTALL)
        for href, link_text in links:
            title = re.sub(r"<[^>]+>", "", link_text).strip()
            if not title or len(title) < 15:
                continue

            url = href if href.startswith("http") else f"https://www.ndt.net{href}"
            if url in seen_urls:
                continue
            seen_urls.add(url)

            articles.append({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "source": "NDT.net",
                "title": title,
                "url": url,
                "summary": "",
            })

    # Also grab forum/news announcements
    forum_links = re.findall(
        r'<a[^>]*href="(https?://www\.ndt\.net/forum/thread\.php\?[^"]+)"[^>]*>(.*?)</a>',
        html, re.DOTALL
    )
    for href, link_text in forum_links:
        title = re.sub(r"<[^>]+>", "", link_text).strip()
        if not title or len(title) < 15 or href in seen_urls:
            continue
        seen_urls.add(href)
        articles.append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "source": "NDT.net",
            "title": title,
            "url": href,
            "summary": "",
        })

    logger.info(f"  NDT.net: {len(articles)} articles found")
    return articles


# ===================================================================
# Source: Inspectioneering (HTML scrape)
# ===================================================================
def fetch_inspectioneering_news(logger):
    """Scrape Inspectioneering news page for article listings."""
    logger.info("Fetching Inspectioneering (HTML)")
    time.sleep(REQUEST_DELAY)
    html = fetch_url(INSPECTIONEERING_NEWS, logger)
    if not html:
        return []

    articles = []
    seen_urls = set()

    # Match article links from inspectioneering.com/news/
    links = re.findall(
        r'<a[^>]*href="(https?://inspectioneering\.com/news/[^"?]+)"[^>]*>(.*?)</a>',
        html, re.DOTALL
    )
    for url, link_text in links:
        title = re.sub(r"<[^>]+>", "", link_text).strip()
        if not title or len(title) < 15 or url in seen_urls:
            continue
        seen_urls.add(url)
        articles.append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "source": "Inspectioneering",
            "title": title,
            "url": url,
            "summary": "",
        })

    logger.info(f"  Inspectioneering: {len(articles)} articles found")
    return articles


# ===================================================================
# Source: Quality Magazine NDT Section (HTML scrape)
# ===================================================================
def fetch_quality_mag_news(logger):
    """Scrape Quality Magazine NDT topic page."""
    logger.info("Fetching Quality Magazine NDT (HTML)")
    time.sleep(REQUEST_DELAY)
    html = fetch_url(QUALITY_MAG_NDT, logger)
    if not html:
        return []

    articles = []
    seen_urls = set()

    links = re.findall(
        r'<a[^>]*href="(https?://www\.qualitymag\.com/articles/[^"?]+)"[^>]*>(.*?)</a>',
        html, re.DOTALL
    )
    for url, link_text in links:
        title = re.sub(r"<[^>]+>", "", link_text).strip()
        if not title or len(title) < 15 or url in seen_urls:
            continue
        seen_urls.add(url)
        articles.append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "source": "Quality Magazine",
            "title": title,
            "url": url,
            "summary": "",
        })

    logger.info(f"  Quality Magazine: {len(articles)} articles found")
    return articles


# ===================================================================
# Source: OneStopNDT News (HTML scrape)
# ===================================================================
def fetch_onestopndt_news(logger):
    """Scrape OneStopNDT news page."""
    logger.info("Fetching OneStopNDT (HTML)")
    time.sleep(REQUEST_DELAY)
    html = fetch_url(ONESTOPNDT_NEWS, logger)
    if not html:
        return []

    articles = []
    seen_urls = set()

    links = re.findall(
        r'<a[^>]*href="(https?://www\.onestopndt\.com/[^"?]*ndt[^"?]*)"[^>]*>(.*?)</a>',
        html, re.DOTALL | re.IGNORECASE
    )
    for url, link_text in links:
        title = re.sub(r"<[^>]+>", "", link_text).strip()
        if not title or len(title) < 15 or url in seen_urls:
            continue
        # Skip navigation/generic links
        lower = title.lower()
        if lower in ("ndt news", "read more", "learn more", "view all"):
            continue
        seen_urls.add(url)
        articles.append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "source": "OneStopNDT",
            "title": title,
            "url": url,
            "summary": "",
        })

    logger.info(f"  OneStopNDT: {len(articles)} articles found")
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
        description="Industry News Fetcher — Inspection Intel"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be fetched")
    parser.add_argument("--backfill", action="store_true",
                        help="Attempt deeper historical fetch")
    args = parser.parse_args()

    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("Industry News Fetcher — Inspection Intel")
    if args.dry_run:
        logger.info("Mode: DRY RUN")
    logger.info("=" * 60)

    NEWS_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing URLs for dedup
    existing_urls = load_existing_urls(NEWS_CSV)
    logger.info(f"Existing articles on disk: {len(existing_urls)}")

    # Fetch from all sources
    all_articles = []

    for fetch_fn in [fetch_metrology_news, fetch_asnt_news, fetch_ndt_net_news,
                      fetch_inspectioneering_news, fetch_quality_mag_news, fetch_onestopndt_news]:
        try:
            articles = fetch_fn(logger)
            all_articles.extend(articles)
        except Exception as e:
            logger.error(f"Error in {fetch_fn.__name__}: {e}", exc_info=True)

    # Dedup against existing
    new_articles = [a for a in all_articles if a["url"] not in existing_urls]
    logger.info(f"Total articles found: {len(all_articles)}, new: {len(new_articles)}")

    # Write
    if not args.dry_run and new_articles:
        append_to_csv(NEWS_CSV, NEWS_FIELDS, new_articles)
        logger.info(f"Appended {len(new_articles)} articles to {NEWS_CSV.name}")
    elif args.dry_run:
        for a in new_articles[:10]:
            logger.info(f"  [DRY RUN] {a['source']}: {a['title'][:80]}")
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
