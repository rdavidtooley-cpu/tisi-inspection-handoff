#!/usr/bin/env python3
"""
Earnings Beat/Miss Tracker
Fetches historical earnings surprise data for tickers across all Intel projects.
Outputs earnings_history.json with beat/miss streaks, beat rates, and avg surprise.

Usage:
    python earnings_tracker.py --project oil_gas
    python earnings_tracker.py --project casino
    python earnings_tracker.py --project inspection
    python earnings_tracker.py --project metal_mining
    python earnings_tracker.py --tickers NEM XOM MGM
    python earnings_tracker.py --project casino --cache
"""

import argparse
import json
import math
import os
import sys
import time
import warnings
from datetime import datetime

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths — always relative to this script's location
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# Map --project flag values to their ticker source files
PROJECT_MAP = {
    "oil_gas": {
        "dir": os.path.join(PROJECT_ROOT, "Oil_Gas_Intel"),
        "ticker_source": "market_data",  # uses Dashboard/market_data.json
    },
    "casino": {
        "dir": os.path.join(PROJECT_ROOT, "Casino_Gaming_Intel"),
        "ticker_source": "edgar_registry",
    },
    "inspection": {
        "dir": os.path.join(PROJECT_ROOT, "Inspection_Intel"),
        "ticker_source": "edgar_registry",
    },
    "metal_mining": {
        "dir": os.path.join(PROJECT_ROOT, "Metal_Mining_Intel"),
        "ticker_source": "edgar_registry",
    },
}


def load_tickers_from_edgar_registry(project_dir):
    """Load tickers from edgar_company_registry.json."""
    path = os.path.join(project_dir, "_scripts", "edgar_company_registry.json")
    if not os.path.exists(path):
        print(f"  ERROR: Registry not found at {path}")
        return []
    with open(path) as f:
        data = json.load(f)
    companies = data.get("companies", [])
    return [c["ticker"] for c in companies if c.get("active", True)]


def load_tickers_from_market_data(project_dir):
    """Load tickers from Dashboard/market_data.json (Oil & Gas format)."""
    path = os.path.join(project_dir, "Dashboard", "market_data.json")
    if not os.path.exists(path):
        print(f"  ERROR: market_data.json not found at {path}")
        return []
    with open(path) as f:
        data = json.load(f)
    return [item["ticker"] for item in data if "ticker" in item]


def load_tickers_for_project(project_key):
    """Load tickers for a given project."""
    config = PROJECT_MAP.get(project_key)
    if not config:
        print(f"  ERROR: Unknown project '{project_key}'. Valid: {', '.join(PROJECT_MAP.keys())}")
        sys.exit(1)

    project_dir = config["dir"]
    if not os.path.isdir(project_dir):
        print(f"  ERROR: Project directory not found: {project_dir}")
        sys.exit(1)

    if config["ticker_source"] == "edgar_registry":
        return load_tickers_from_edgar_registry(project_dir)
    elif config["ticker_source"] == "market_data":
        return load_tickers_from_market_data(project_dir)
    return []


def fetch_earnings_for_ticker(ticker_sym):
    """
    Fetch earnings history for a single ticker using yfinance.
    Returns a dict with history list, streak, beat_rate, avg_surprise.
    Returns None if no earnings data available.
    """
    import yfinance as yf

    try:
        stock = yf.Ticker(ticker_sym)
        ed = stock.earnings_dates
    except Exception as e:
        print(f"  {ticker_sym}: ERROR fetching earnings_dates — {e}")
        return None

    if ed is None or len(ed) == 0:
        print(f"  {ticker_sym}: No earnings data available")
        return None

    history = []
    for idx, row in ed.iterrows():
        eps_estimate = row.get("EPS Estimate")
        eps_actual = row.get("Reported EPS")
        surprise_pct = row.get("Surprise(%)")

        # Skip future dates (no reported EPS yet)
        if eps_actual is None or (hasattr(eps_actual, "__float__") and str(eps_actual) == "nan"):
            continue

        # Convert pandas types to native Python, filter NaN
        try:
            eps_actual = float(eps_actual)
            if math.isnan(eps_actual):
                continue
        except (ValueError, TypeError):
            continue

        eps_est = None
        if eps_estimate is not None:
            try:
                val = float(eps_estimate)
                if not math.isnan(val):
                    eps_est = val
            except (ValueError, TypeError):
                pass

        surp = None
        if surprise_pct is not None:
            try:
                val = float(surprise_pct)
                if not math.isnan(val):
                    surp = round(val, 2)
            except (ValueError, TypeError):
                pass

        # Determine beat/miss
        beat = None
        if eps_est is not None:
            beat = eps_actual > eps_est
        elif surp is not None:
            beat = surp > 0

        # Format the date
        date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]

        entry = {
            "date": date_str,
            "eps_actual": round(eps_actual, 4),
            "eps_estimate": round(eps_est, 4) if eps_est is not None else None,
            "surprise_pct": surp,
            "beat": beat,
        }
        history.append(entry)

    if not history:
        print(f"  {ticker_sym}: No reported earnings found")
        return None

    # Calculate summary stats
    beats_known = [h for h in history if h["beat"] is not None]
    beat_count = sum(1 for h in beats_known if h["beat"])
    beat_rate = round(100.0 * beat_count / len(beats_known), 1) if beats_known else None

    surprises = [h["surprise_pct"] for h in history if h["surprise_pct"] is not None]
    avg_surprise = round(sum(surprises) / len(surprises), 2) if surprises else None

    # Calculate current streak (consecutive beats or misses from most recent)
    streak = 0
    if beats_known:
        streak_val = beats_known[0]["beat"]  # most recent result
        for h in beats_known:
            if h["beat"] == streak_val:
                streak += 1
            else:
                break
        if not streak_val:
            streak = -streak  # negative for miss streaks

    result = {
        "history": history,
        "streak": streak,
        "beat_rate": beat_rate,
        "avg_surprise": avg_surprise,
        "quarters_tracked": len(history),
    }

    status = "beats" if streak > 0 else "misses"
    print(f"  {ticker_sym}: {len(history)} quarters, beat rate {beat_rate}%, streak {abs(streak)} {status}, avg surprise {avg_surprise}%")
    return result


def main():
    parser = argparse.ArgumentParser(description="Earnings Beat/Miss Tracker")
    parser.add_argument("--project", type=str, help="Project: oil_gas, casino, inspection, metal_mining")
    parser.add_argument("--tickers", nargs="+", type=str, help="Specific tickers to fetch")
    parser.add_argument("--cache", action="store_true", help="Reuse previously fetched data if available")
    parser.add_argument("--output", type=str, help="Output file path (default: project's _scripts/earnings_history.json)")
    args = parser.parse_args()

    if not args.project and not args.tickers:
        print("ERROR: Provide --project or --tickers")
        parser.print_help()
        sys.exit(1)

    # Determine tickers
    if args.tickers:
        tickers = args.tickers
        project_key = args.project or "manual"
    else:
        project_key = args.project
        tickers = load_tickers_for_project(project_key)

    if not tickers:
        print("ERROR: No tickers found")
        sys.exit(1)

    # Determine output path
    if args.output:
        output_path = args.output
    elif args.project and args.project in PROJECT_MAP:
        project_dir = PROJECT_MAP[args.project]["dir"]
        output_path = os.path.join(project_dir, "_scripts", "earnings_history.json")
    else:
        output_path = os.path.join(SCRIPT_DIR, "earnings_history.json")

    print(f"Earnings Tracker — {project_key}")
    print(f"  Tickers: {len(tickers)}")
    print(f"  Output: {output_path}")
    print()

    # Load cache if --cache flag set
    existing = {}
    if args.cache and os.path.exists(output_path):
        with open(output_path) as f:
            existing = json.load(f)
        print(f"  Loaded cache: {len(existing)} tickers already fetched")

    results = dict(existing)
    fetched = 0
    skipped = 0
    errors = 0

    for i, ticker in enumerate(tickers):
        if args.cache and ticker in existing:
            skipped += 1
            continue

        data = fetch_earnings_for_ticker(ticker)
        if data:
            results[ticker] = data
            fetched += 1
        else:
            errors += 1

        # Rate limit: 0.3s between fetches (DNS thread safety on macOS)
        if i < len(tickers) - 1:
            time.sleep(0.3)

    # Write output
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    # Add metadata
    meta_path = output_path.replace(".json", "_meta.json")
    meta = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "project": project_key,
        "tickers_requested": len(tickers),
        "tickers_fetched": fetched,
        "tickers_cached": skipped,
        "tickers_failed": errors,
        "tickers_total": len(results),
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print()
    print(f"Done. Fetched: {fetched}, Cached: {skipped}, Failed: {errors}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
