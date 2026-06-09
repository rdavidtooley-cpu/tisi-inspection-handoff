#!/usr/bin/env python3
"""Free RSS M&A wire feed — replaces the Bigdata MCP dependency.

Usage: python3 fetch_ma_rss.py <SiteFolder>
  e.g. python3 fetch_ma_rss.py Inspection_Intel

Pulls M&A headlines from Google News RSS (aggregator of PR Newswire, Business
Wire, all trade press). Per-site sector keyword filter keeps results focused.
Reuses fetch_ma_wire.normalize_raw_results for entity extraction + schema
normalization, so output lands directly in {site}/Dashboard/ma_deals_wire.json.

Zero tokens, zero external deps, zero rate limits.
"""

import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from fetch_ma_wire import SITE_KEYWORDS, normalize_raw_results  # noqa: E402

MA_TERMS = (
    '(acquires OR acquisition OR merger OR buyout OR "to buy" OR takeover '
    'OR "to acquire" OR divests OR "sells to")'
)

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) MasterIntelligence/1.0"

# Strict sector tokens — at least one must appear in title OR entities to keep a deal.
# Filters out Google News false-positives (e.g. "mining" keyword matching pharma articles).
SITE_RELEVANCE_TOKENS = {
    "Inspection_Intel": [
        "ndt", "non-destructive", "nondestructive", "inspection", "testing",
        "certification", "tic ", "asset integrity", "quality assurance",
        "pipeline integrity", "calibration", "metrology",
    ],
    "Oil_Gas_Intel": [
        "oil", "gas", "upstream", "midstream", "downstream", "refining",
        "oilfield", "pipeline", "e&p", "shale", "drilling", "petroleum",
        "lng", "refinery", "energy",
    ],
    "Casino_Gaming_Intel": [
        "casino", "gaming", "sportsbook", "igaming", "gambling", "wager",
        "slot", "poker", "racetrack", "lottery",
    ],
    "Metal_Mining_Intel": [
        "mining", "mine ", "miner ", "mineral", "metal", "gold", "copper",
        "silver", "lithium", "nickel", "zinc", "iron ore", "platinum",
        "palladium", "uranium", "smelter", "refinery", "ore",
    ],
    "Media_Broadcasting_Intel": [
        "broadcast", "tv ", " tv", "television", "radio", "media",
        "cable", "news network", "publisher", "publishing", "streaming",
        "newspaper", "magazine", "studio",
    ],
    "Aerospace_Defense_Intel": [
        "aerospace", "defense", "defence", "military", "aviation", "aircraft",
        "satellite", "missile", "drone", "uav", "radar", "naval", "army",
        "fighter", "helicopter", "rocket", "space ", " space", "munitions",
    ],
    "Autos_Intel": [
        "auto", "automotive", "automaker", "vehicle", "car ", " cars",
        "truck", "dealership", "ev ", " ev", "electric vehicle", "tire",
        "auto parts", "powertrain", "motor", "chassis",
    ],
    "Chemicals_Intel": [
        "chemical", "specialty chemical", "petrochemical", "polymer",
        "coating", "paint", "adhesive", "resin", "fertilizer", "pesticide",
        "agrichemical", "silicone", "catalyst", "pigment",
    ],
    "Homebuilders_Intel": [
        "homebuilder", "home builder", "home building", "housing",
        "residential", "subdivision", "single-family", "multifamily",
        "home construction", "new homes", "building products",
    ],
    "Power_Utilities_Intel": [
        "utility", "utilities", "power ", " power", "electric", "grid",
        "renewable", "solar", "wind ", " wind", "transmission", "generation",
        "nuclear", "battery storage", "ipp ", "independent power",
    ],
    "REITs_Intel": [
        "reit", "real estate", "property", "mall", "apartment", "industrial",
        "warehouse", "office", "retail", "hospitality", "hotel ", " hotels",
        "self storage", "self-storage", "data center", "net lease", "landlord",
    ],
    "Rail_Logistics_Intel": [
        "rail", "railroad", "logistics", "trucking", "freight", "warehouse",
        "supply chain", "parcel", "last-mile", "last mile", "intermodal",
        "3pl", "third-party logistics", "drayage", "courier",
    ],
    "Semiconductors_Intel": [
        "semiconductor", "chip", "chipmaker", "chip maker", "foundry",
        "fab ", " fab", "wafer", "eda", "silicon", "processor", "lithography",
        "ic ", "integrated circuit", "memory chip", "gpu", "fpga",
    ],
    "Shipping_Intel": [
        "shipping", "ocean shipping", "tanker", "bulker", "dry bulk",
        "drybulk", "container ship", "maritime", "port ", " port", "vessel",
        "lng carrier", "lpg carrier", "product tanker", "vlcc", "suezmax",
    ],
}


def _build_query(site_folder: str) -> str:
    sector = SITE_KEYWORDS.get(site_folder)
    if not sector:
        raise ValueError(f"No keyword config for {site_folder}")
    return f"{MA_TERMS} AND ({sector})"


def _fetch_rss(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _strip_html(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _clean_google_title(s: str) -> str:
    """Google News appends ' - Publisher Name' to every headline. Strip it."""
    if not s:
        return s
    return re.sub(r"\s+-\s+[^-]{2,60}$", "", s).strip()


def _parse_pubdate(s: str) -> str | None:
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
        return dt.strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
        return m.group(1) if m else None


def fetch_google_news(query: str) -> list[dict]:
    url = (
        "https://news.google.com/rss/search?"
        + urllib.parse.urlencode({
            "q": query,
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
        })
    )
    xml_bytes = _fetch_rss(url)
    root = ET.fromstring(xml_bytes)

    items = []
    for item in root.iter("item"):
        title = _clean_google_title((item.findtext("title") or "").strip())
        desc = _strip_html(item.findtext("description") or "")
        link = (item.findtext("link") or "").strip()
        pub = _parse_pubdate(item.findtext("pubDate") or "")
        source_el = item.find("source")
        src_name = (source_el.text or "").strip() if source_el is not None else ""

        if not title:
            continue

        items.append({
            "title": title,
            "summary": desc,
            "url": link,
            "date": pub or "",
            "source_name": src_name,
        })
    return items


SOURCES = [
    ("Google News", fetch_google_news),
]


def collect_raw(site_folder: str) -> list[dict]:
    query = _build_query(site_folder)
    all_items = []
    for name, fetcher in SOURCES:
        try:
            items = fetcher(query)
            print(f"  {name}: {len(items)} raw items")
            all_items.extend(items)
        except Exception as e:
            print(f"  {name}: fetch failed ({e.__class__.__name__}: {e})")
    # Dedup by URL
    seen, deduped = set(), []
    for it in all_items:
        key = it.get("url") or it.get("title")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)
    return deduped


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 fetch_ma_rss.py <SiteFolder>")
        sys.exit(1)

    site_folder = sys.argv[1]
    site_dir = BASE / site_folder
    out_path = site_dir / "Dashboard" / "ma_deals_wire.json"

    if not site_dir.exists():
        print(f"Site folder not found: {site_dir}")
        sys.exit(1)

    print(f"[{site_folder}] Fetching RSS M&A feed")
    print(f"  Query: {_build_query(site_folder)[:120]}...")

    try:
        raw = collect_raw(site_folder)
    except Exception as e:
        print(f"  Collection failed: {e}. Writing empty wire file.")
        with open(out_path, "w") as f:
            json.dump([], f)
        return

    deals = normalize_raw_results(raw, site_folder)

    # Sector-relevance post-filter: drop deals where no sector token appears
    # in title, acquirer name, or target name (catches Google News false-positives).
    tokens = SITE_RELEVANCE_TOKENS.get(site_folder, [])
    if tokens:
        # Build a lookup from raw items so we can check original titles too
        url_to_title = {it.get("url", ""): it.get("title", "").lower() for it in raw}
        filtered = []
        dropped = 0
        for d in deals:
            haystack = " ".join([
                (d.get("acquirer") or "").lower(),
                (d.get("target") or "").lower(),
                url_to_title.get(d.get("source_url", ""), ""),
                (d.get("rationale") or "").lower(),
            ])
            if any(tok in haystack for tok in tokens):
                filtered.append(d)
            else:
                dropped += 1
        if dropped:
            print(f"  Sector filter: dropped {dropped} irrelevant deals")
        deals = filtered

    with open(out_path, "w") as f:
        json.dump(deals, f, indent=2)

    print(f"  → {len(raw)} raw items → {len(deals)} deals → {out_path.relative_to(BASE)}")
    if deals:
        print(f"  Latest: {deals[0].get('date')} — {deals[0].get('acquirer')} → {deals[0].get('target')}")


if __name__ == "__main__":
    main()
