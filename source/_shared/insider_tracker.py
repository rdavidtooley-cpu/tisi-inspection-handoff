#!/usr/bin/env python3
"""
Insider Trading Tracker — Shared across all Intel projects.

Fetches insider transaction data from yfinance for a given project's ticker universe,
ranks companies by recent insider buying activity (last 90 days), and outputs
insider_data.json to the project's Dashboard directory.

Usage:
    python3 insider_tracker.py --project metal_mining
    python3 insider_tracker.py --project casino
    python3 insider_tracker.py --project inspection
    python3 insider_tracker.py --project oil_gas
    python3 insider_tracker.py --tickers NEM GOLD FCX   # ad-hoc test
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta

import yfinance as yf
import pandas as pd

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


def load_tickers(project_name):
    """Load ticker list from a project's market_data.json."""
    dashboard_dir = PROJECT_MAP[project_name]
    md_path = os.path.join(dashboard_dir, "market_data.json")
    if not os.path.exists(md_path):
        print(f"ERROR: market_data.json not found at {md_path}")
        sys.exit(1)

    with open(md_path) as f:
        data = json.load(f)

    # Oil & Gas uses a list of dicts; others use a dict keyed by ticker
    if isinstance(data, list):
        tickers = [d.get("ticker", d.get("symbol", "")) for d in data]
    elif isinstance(data, dict):
        tickers = list(data.keys())
    else:
        print(f"ERROR: Unexpected market_data.json format in {project_name}")
        sys.exit(1)

    return [t for t in tickers if t], dashboard_dir


def load_company_names(project_name):
    """Load ticker -> company name mapping from market_data.json."""
    dashboard_dir = PROJECT_MAP[project_name]
    md_path = os.path.join(dashboard_dir, "market_data.json")
    with open(md_path) as f:
        data = json.load(f)

    names = {}
    if isinstance(data, list):
        for d in data:
            t = d.get("ticker", d.get("symbol", ""))
            names[t] = d.get("company", d.get("name", t))
    elif isinstance(data, dict):
        for t, d in data.items():
            names[t] = d.get("company", d.get("name", t))
    return names


def fetch_insider_data(ticker):
    """Fetch insider transactions for a single ticker. Returns list of dicts."""
    try:
        stock = yf.Ticker(ticker)
        txns = stock.insider_transactions
        if txns is None or txns.empty:
            return []

        records = []
        for _, row in txns.iterrows():
            # Parse transaction type from the Text field
            text = str(row.get("Text", "")).lower()
            if "sale" in text or "sell" in text:
                txn_type = "Sell"
            elif "purchase" in text or "buy" in text or "acquisition" in text:
                txn_type = "Buy"
            elif "option" in text or "exercise" in text:
                txn_type = "Option Exercise"
            elif "gift" in text:
                txn_type = "Gift"
            else:
                txn_type = str(row.get("Transaction", "Unknown"))

            # Parse date
            raw_date = row.get("Start Date")
            if pd.notna(raw_date):
                if isinstance(raw_date, str):
                    date_str = raw_date
                else:
                    date_str = str(raw_date)[:10]
            else:
                date_str = None

            records.append({
                "insider": str(row.get("Insider", "Unknown")),
                "position": str(row.get("Position", "Unknown")),
                "date": date_str,
                "transaction_type": txn_type,
                "shares": int(row.get("Shares", 0)) if pd.notna(row.get("Shares")) else 0,
                "value": float(row.get("Value", 0)) if pd.notna(row.get("Value")) else 0,
                "description": str(row.get("Text", "")),
                "ownership": str(row.get("Ownership", "")),
            })
        return records

    except Exception as e:
        print(f"  WARNING: Failed to fetch insider data for {ticker}: {e}")
        return []


def build_output(all_data, company_names):
    """Build the final insider_data.json structure."""
    cutoff = datetime.now() - timedelta(days=90)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    # Flatten all transactions with ticker attached
    all_txns = []
    for ticker, txns in all_data.items():
        for t in txns:
            t_copy = dict(t)
            t_copy["ticker"] = ticker
            t_copy["company"] = company_names.get(ticker, ticker)
            all_txns.append(t_copy)

    # Recent buys and sells (last 90 days, sorted by value descending)
    recent_buys = sorted(
        [t for t in all_txns if t["transaction_type"] == "Buy" and t.get("date") and t["date"] >= cutoff_str],
        key=lambda x: x["value"],
        reverse=True
    )[:20]

    recent_sells = sorted(
        [t for t in all_txns if t["transaction_type"] == "Sell" and t.get("date") and t["date"] >= cutoff_str],
        key=lambda x: x["value"],
        reverse=True
    )[:20]

    # Buy signal ranking: total $ bought in last 90 days, by ticker
    buy_totals = {}
    sell_totals = {}
    for t in all_txns:
        if not t.get("date") or t["date"] < cutoff_str:
            continue
        ticker = t["ticker"]
        if t["transaction_type"] == "Buy":
            buy_totals[ticker] = buy_totals.get(ticker, 0) + t["value"]
        elif t["transaction_type"] == "Sell":
            sell_totals[ticker] = sell_totals.get(ticker, 0) + t["value"]

    buy_signal_ranking = sorted(
        [
            {
                "ticker": ticker,
                "company": company_names.get(ticker, ticker),
                "total_bought_90d": round(val, 2),
                "total_sold_90d": round(sell_totals.get(ticker, 0), 2),
                "net_90d": round(val - sell_totals.get(ticker, 0), 2),
            }
            for ticker, val in buy_totals.items()
        ],
        key=lambda x: x["total_bought_90d"],
        reverse=True
    )

    # By-ticker breakdown
    by_ticker = {}
    for ticker, txns in all_data.items():
        recent = [t for t in txns if t.get("date") and t["date"] >= cutoff_str]
        buys_90 = sum(t["value"] for t in recent if t["transaction_type"] == "Buy")
        sells_90 = sum(t["value"] for t in recent if t["transaction_type"] == "Sell")
        by_ticker[ticker] = {
            "company": company_names.get(ticker, ticker),
            "transactions": txns,
            "total_transactions": len(txns),
            "recent_buys_90d": round(buys_90, 2),
            "recent_sells_90d": round(sells_90, 2),
            "net_90d": round(buys_90 - sells_90, 2),
        }

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "lookback_days": 90,
        "cutoff_date": cutoff_str,
        "tickers_scanned": len(all_data),
        "recent_buys": recent_buys,
        "recent_sells": recent_sells,
        "buy_signal_ranking": buy_signal_ranking,
        "by_ticker": by_ticker,
    }


def main():
    parser = argparse.ArgumentParser(description="Insider Trading Tracker")
    parser.add_argument("--project", choices=["metal_mining", "casino", "inspection", "oil_gas"],
                        help="Project to scan")
    parser.add_argument("--tickers", nargs="+", help="Ad-hoc list of tickers (overrides --project)")
    parser.add_argument("--output", help="Custom output path (default: project Dashboard dir)")
    args = parser.parse_args()

    if not args.project and not args.tickers:
        parser.error("Provide --project or --tickers")

    # Determine tickers and output directory
    if args.tickers:
        tickers = args.tickers
        output_dir = args.output or os.path.join(SCRIPT_DIR, "..")
        company_names = {t: t for t in tickers}
    else:
        tickers, output_dir = load_tickers(args.project)
        company_names = load_company_names(args.project)

    if args.output:
        output_dir = args.output

    output_path = os.path.join(output_dir, "insider_data.json")

    print(f"Insider Tracker — scanning {len(tickers)} tickers")
    print(f"Output: {output_path}")
    print()

    all_data = {}
    for i, ticker in enumerate(tickers, 1):
        print(f"  [{i}/{len(tickers)}] {ticker}...", end=" ", flush=True)
        txns = fetch_insider_data(ticker)
        all_data[ticker] = txns
        print(f"{len(txns)} transactions")
        if i < len(tickers):
            time.sleep(0.3)  # Rate limiting — prevents DNS thread exhaustion on macOS

    result = build_output(all_data, company_names)

    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, default=str)

    # Summary
    total_txns = sum(len(t) for t in all_data.values())
    print(f"\nDone. {total_txns} total transactions across {len(all_data)} tickers.")
    print(f"  Recent buys (90d): {len(result['recent_buys'])}")
    print(f"  Recent sells (90d): {len(result['recent_sells'])}")
    print(f"  Companies with insider buying: {len(result['buy_signal_ranking'])}")
    print(f"  Saved to: {output_path}")


if __name__ == "__main__":
    main()
