#!/usr/bin/env python3
"""
Short Interest Monitor — Shared across all Intel projects.

Reads the existing market_data.json from a project's Dashboard directory
(which already contains short interest fields from the refresh scripts),
extracts and ranks the short interest data, and outputs short_interest.json.

Usage:
    python3 short_interest.py --project metal_mining
    python3 short_interest.py --project casino
    python3 short_interest.py --project inspection
    python3 short_interest.py --project oil_gas
"""

import argparse
import json
import os
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# Path configuration — __file__-relative, never hardcoded
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)  # project root

PROJECT_MAP = {
    "metal_mining": os.path.join(PROJECT_ROOT, "Metal_Mining_Intel", "Dashboard"),
    "casino":       os.path.join(PROJECT_ROOT, "Casino_Gaming_Intel", "Dashboard"),
    "inspection":   os.path.join(PROJECT_ROOT, "Inspection_Intel", "Dashboard"),
    "oil_gas":      os.path.join(PROJECT_ROOT, "Oil_Gas_Intel", "Dashboard"),
}


def load_market_data(project_name):
    """Load market_data.json and normalize to list of dicts with ticker key."""
    dashboard_dir = PROJECT_MAP[project_name]
    md_path = os.path.join(dashboard_dir, "market_data.json")
    if not os.path.exists(md_path):
        print(f"ERROR: market_data.json not found at {md_path}")
        sys.exit(1)

    with open(md_path) as f:
        data = json.load(f)

    # Normalize: Oil & Gas is a list, others are dicts keyed by ticker
    records = []
    if isinstance(data, list):
        for d in data:
            d["_ticker"] = d.get("ticker", d.get("symbol", ""))
            records.append(d)
    elif isinstance(data, dict):
        for ticker, d in data.items():
            d["_ticker"] = ticker
            records.append(d)

    return records, dashboard_dir


def extract_short_data(records):
    """Extract short interest fields from market data records."""
    entries = []
    for r in records:
        ticker = r["_ticker"]
        company = r.get("company", r.get("name", ticker))
        category = r.get("category", r.get("sector", ""))
        price = r.get("price", r.get("price_usd"))
        market_cap_b = r.get("market_cap_b")

        shares_short = r.get("shares_short")
        short_ratio = r.get("short_ratio")
        short_pct_float = r.get("short_pct_float")

        # Convert short_pct_float to percentage if it's a decimal (e.g., 0.0257 -> 2.57)
        short_pct_display = None
        if short_pct_float is not None:
            if short_pct_float < 1:
                short_pct_display = round(short_pct_float * 100, 2)
            else:
                short_pct_display = round(short_pct_float, 2)

        entries.append({
            "ticker": ticker,
            "company": company,
            "category": category,
            "price": price,
            "market_cap_b": market_cap_b,
            "shares_short": shares_short,
            "short_ratio": round(short_ratio, 2) if short_ratio else None,
            "short_pct_float": short_pct_display,
            "short_pct_float_raw": short_pct_float,
        })

    return entries


def build_output(entries):
    """Build the final short_interest.json structure."""
    # Filter to entries that have at least some short data
    has_data = [e for e in entries if e["short_pct_float"] is not None or e["short_ratio"] is not None]
    no_data = [e["ticker"] for e in entries if e["short_pct_float"] is None and e["short_ratio"] is None]

    # Most shorted by % of float
    most_shorted = sorted(
        [e for e in has_data if e["short_pct_float"] is not None],
        key=lambda x: x["short_pct_float"],
        reverse=True
    )

    # Least shorted by % of float
    least_shorted = sorted(
        [e for e in has_data if e["short_pct_float"] is not None],
        key=lambda x: x["short_pct_float"],
    )

    # High short ratio (days to cover > 5)
    high_short_ratio = sorted(
        [e for e in has_data if e["short_ratio"] is not None and e["short_ratio"] > 5],
        key=lambda x: x["short_ratio"],
        reverse=True
    )

    # Clean up internal fields before output
    def clean(entry):
        e = dict(entry)
        e.pop("short_pct_float_raw", None)
        return e

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tickers_total": len(entries),
        "tickers_with_short_data": len(has_data),
        "tickers_missing_data": no_data,
        "most_shorted": [clean(e) for e in most_shorted[:20]],
        "least_shorted": [clean(e) for e in least_shorted[:20]],
        "high_short_ratio": [clean(e) for e in high_short_ratio],
        "summary": {
            "avg_short_pct_float": round(
                sum(e["short_pct_float"] for e in has_data if e["short_pct_float"]) /
                max(len([e for e in has_data if e["short_pct_float"]]), 1),
                2
            ),
            "median_short_ratio": round(
                sorted([e["short_ratio"] for e in has_data if e["short_ratio"]])[
                    len([e for e in has_data if e["short_ratio"]]) // 2
                ] if [e for e in has_data if e["short_ratio"]] else 0,
                2
            ),
            "companies_above_10pct": len([e for e in has_data if e["short_pct_float"] and e["short_pct_float"] > 10]),
            "companies_above_5pct": len([e for e in has_data if e["short_pct_float"] and e["short_pct_float"] > 5]),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Short Interest Monitor")
    parser.add_argument("--project", choices=["metal_mining", "casino", "inspection", "oil_gas"],
                        required=True, help="Project to analyze")
    parser.add_argument("--output", help="Custom output path (default: project Dashboard dir)")
    args = parser.parse_args()

    records, dashboard_dir = load_market_data(args.project)
    output_dir = args.output or dashboard_dir
    output_path = os.path.join(output_dir, "short_interest.json")

    print(f"Short Interest Monitor — analyzing {len(records)} tickers from {args.project}")
    print(f"Source: {os.path.join(dashboard_dir, 'market_data.json')}")
    print(f"Output: {output_path}")
    print()

    entries = extract_short_data(records)
    result = build_output(entries)

    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, default=str)

    # Summary
    print(f"Done. {result['tickers_with_short_data']}/{result['tickers_total']} tickers have short data.")
    print(f"  Avg short % of float: {result['summary']['avg_short_pct_float']}%")
    print(f"  Companies >10% shorted: {result['summary']['companies_above_10pct']}")
    print(f"  Companies >5% shorted: {result['summary']['companies_above_5pct']}")
    print(f"  High short ratio (>5 days): {len(result['high_short_ratio'])}")
    if result["most_shorted"]:
        top = result["most_shorted"][0]
        print(f"  Most shorted: {top['company']} ({top['ticker']}) at {top['short_pct_float']}%")
    if result.get("tickers_missing_data"):
        print(f"  Missing data: {', '.join(result['tickers_missing_data'])}")
    print(f"  Saved to: {output_path}")


if __name__ == "__main__":
    main()
