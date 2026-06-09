#!/usr/bin/env python3
"""
Finnhub Data Fetcher — Inspection Intel

Fetches enhanced financial intelligence from Finnhub API:
  - Earnings calendar (upcoming & recent)
  - Insider transactions
  - Analyst upgrades/downgrades
  - Recommendation trends
  - Earnings call transcripts list

Output: Industry_Data/Finnhub/finnhub_data.json

Usage:
  python3 finnhub_fetcher.py
  python3 finnhub_fetcher.py --dry-run
"""

import json
import logging
import ssl
import sys
import time
import argparse
import certifi
from pathlib import Path
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SSL_CTX = ssl.create_default_context(cafile=certifi.where())

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_DIR / "Industry_Data" / "Finnhub"
LOG_DIR = SCRIPT_DIR / "logs"

API_KEY = "d6ljku1r01qrq6i318b0d6ljku1r01qrq6i318bg"
BASE_URL = "https://finnhub.io/api/v1"
REQUEST_DELAY = 0.35  # Finnhub free: 60 calls/min => ~1/sec, stay safe

# Ticker mapping: yfinance ticker -> Finnhub symbol
# Finnhub uses exchange-prefixed symbols for international stocks
FINNHUB_TICKERS = {
    'MG':       'MG',
    'TISI':     'TISI',
    'TIC':      'TIC',
    'OII':      'OII',
    'XPRO':     'XPRO',
    'TRNS':     'TRNS',
    'THR':      'THR',
    # International — Finnhub format is different from yfinance
    'SGSN.SW':  'SGSN.SW',    # Swiss
    'BVI.PA':   'BVI.PA',     # Paris
    'ITRK.L':   'ITRK.L',    # London
    'COTN.SW':  'COTN.SW',    # Swiss
}

COMPANY_NAMES = {
    'MG': 'Mistras Group', 'TISI': 'Team Inc', 'TIC': 'Acuren Group',
    'OII': 'Oceaneering Intl', 'XPRO': 'Expro Group', 'TRNS': 'Transcat',
    'THR': 'Thermon Group', 'SGSN.SW': 'SGS SA', 'BVI.PA': 'Bureau Veritas',
    'ITRK.L': 'Intertek Group', 'COTN.SW': 'Comet Group',
}


def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("finnhub_fetcher")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(LOG_DIR / "finnhub_fetcher.log")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def api_get(endpoint, params=None, logger=None):
    """Make a Finnhub API GET request."""
    url = f"{BASE_URL}{endpoint}?token={API_KEY}"
    if params:
        for k, v in params.items():
            url += f"&{k}={v}"
    time.sleep(REQUEST_DELAY)
    try:
        req = Request(url, headers={"User-Agent": "InspectionIntel/1.0"})
        resp = urlopen(req, context=SSL_CTX, timeout=15)
        data = json.loads(resp.read().decode("utf-8"))
        return data
    except HTTPError as e:
        if logger:
            logger.warning(f"  HTTP {e.code}: {endpoint}")
        return None
    except (URLError, TimeoutError) as e:
        if logger:
            logger.warning(f"  Network error: {endpoint} — {e}")
        return None
    except json.JSONDecodeError:
        if logger:
            logger.warning(f"  JSON decode error: {endpoint}")
        return None


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------

def fetch_earnings_calendar(logger):
    """Fetch upcoming and recent earnings for tracked companies."""
    logger.info("\n--- Earnings Calendar ---")
    today = datetime.now()
    from_date = (today - timedelta(days=90)).strftime("%Y-%m-%d")
    to_date = (today + timedelta(days=90)).strftime("%Y-%m-%d")

    all_earnings = []
    for yf_ticker, fh_ticker in FINNHUB_TICKERS.items():
        logger.info(f"  Earnings: {COMPANY_NAMES.get(yf_ticker, yf_ticker)} ({fh_ticker})")
        data = api_get("/calendar/earnings", {
            "symbol": fh_ticker,
            "from": from_date,
            "to": to_date,
        }, logger)
        if data and "earningsCalendar" in data:
            for e in data["earningsCalendar"]:
                e["yf_ticker"] = yf_ticker
                e["company"] = COMPANY_NAMES.get(yf_ticker, yf_ticker)
                all_earnings.append(e)
            logger.info(f"    {len(data['earningsCalendar'])} earnings events")
        else:
            logger.info(f"    No earnings data")
    return all_earnings


def fetch_insider_transactions(logger):
    """Fetch insider buying/selling activity."""
    logger.info("\n--- Insider Transactions ---")
    all_transactions = []
    for yf_ticker, fh_ticker in FINNHUB_TICKERS.items():
        logger.info(f"  Insider txns: {COMPANY_NAMES.get(yf_ticker, yf_ticker)} ({fh_ticker})")
        data = api_get("/stock/insider-transactions", {
            "symbol": fh_ticker,
        }, logger)
        if data and "data" in data:
            for txn in data["data"][:20]:  # Last 20 transactions
                txn["yf_ticker"] = yf_ticker
                txn["company"] = COMPANY_NAMES.get(yf_ticker, yf_ticker)
                all_transactions.append(txn)
            logger.info(f"    {len(data['data'])} transactions (kept top 20)")
        else:
            logger.info(f"    No insider data")
    return all_transactions


def fetch_upgrades_downgrades(logger):
    """Fetch analyst rating changes."""
    logger.info("\n--- Analyst Upgrades/Downgrades ---")
    all_changes = []
    for yf_ticker, fh_ticker in FINNHUB_TICKERS.items():
        logger.info(f"  Upgrades: {COMPANY_NAMES.get(yf_ticker, yf_ticker)} ({fh_ticker})")
        data = api_get("/stock/upgrade-downgrade", {
            "symbol": fh_ticker,
        }, logger)
        if data and isinstance(data, list):
            # Keep last 12 months
            cutoff = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            recent = [r for r in data if r.get("gradeDate", "") >= cutoff]
            for r in recent:
                r["yf_ticker"] = yf_ticker
                r["company"] = COMPANY_NAMES.get(yf_ticker, yf_ticker)
                all_changes.append(r)
            logger.info(f"    {len(recent)} rating changes (last 12 months)")
        else:
            logger.info(f"    No upgrade/downgrade data")
    return all_changes


def fetch_recommendation_trends(logger):
    """Fetch analyst recommendation trends over time."""
    logger.info("\n--- Recommendation Trends ---")
    all_trends = {}
    for yf_ticker, fh_ticker in FINNHUB_TICKERS.items():
        logger.info(f"  Rec trends: {COMPANY_NAMES.get(yf_ticker, yf_ticker)} ({fh_ticker})")
        data = api_get("/stock/recommendation", {
            "symbol": fh_ticker,
        }, logger)
        if data and isinstance(data, list) and len(data) > 0:
            all_trends[yf_ticker] = data[:8]  # Last 8 periods
            logger.info(f"    {len(data)} periods (kept last 8)")
        else:
            logger.info(f"    No recommendation data")
    return all_trends


def fetch_transcripts_list(logger):
    """Fetch list of available earnings call transcripts."""
    logger.info("\n--- Earnings Transcripts ---")
    all_transcripts = {}
    for yf_ticker, fh_ticker in FINNHUB_TICKERS.items():
        logger.info(f"  Transcripts: {COMPANY_NAMES.get(yf_ticker, yf_ticker)} ({fh_ticker})")
        data = api_get("/stock/transcripts/list", {
            "symbol": fh_ticker,
        }, logger)
        if data and "transcripts" in data and data["transcripts"]:
            all_transcripts[yf_ticker] = data["transcripts"][:4]  # Last 4 quarters
            logger.info(f"    {len(data['transcripts'])} transcripts available")
        else:
            logger.info(f"    No transcripts")
    return all_transcripts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Finnhub Data Fetcher")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("Finnhub Data Fetcher — Inspection Intel")
    logger.info("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Fetch all data
    earnings = fetch_earnings_calendar(logger)
    insider_txns = fetch_insider_transactions(logger)
    upgrades = fetch_upgrades_downgrades(logger)
    rec_trends = fetch_recommendation_trends(logger)
    transcripts = fetch_transcripts_list(logger)

    # Bundle
    bundle = {
        "earnings_calendar": earnings,
        "insider_transactions": insider_txns,
        "upgrades_downgrades": upgrades,
        "recommendation_trends": rec_trends,
        "transcripts": transcripts,
        "generated_at": datetime.now().isoformat(),
    }

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info(f"  Earnings events:      {len(earnings)}")
    logger.info(f"  Insider transactions: {len(insider_txns)}")
    logger.info(f"  Upgrades/downgrades:  {len(upgrades)}")
    logger.info(f"  Rec trend tickers:    {len(rec_trends)}")
    logger.info(f"  Transcript tickers:   {len(transcripts)}")
    logger.info("=" * 60)

    if not args.dry_run:
        out_path = OUTPUT_DIR / "finnhub_data.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2, default=str)
        logger.info(f"Saved: {out_path}")
    else:
        logger.info("DRY RUN — no files written")


if __name__ == "__main__":
    main()
