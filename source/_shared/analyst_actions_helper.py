#!/usr/bin/env python3
"""
Fetch recent analyst upgrades/downgrades for a set of tickers via yfinance.

Extracted from `Oil_Gas_Intel/_scripts/collect_news_multi.py::fetch_analyst_actions`
(2026-05-08) so the same logic can be reused by Casino/Mining/Inspection refresh
scripts that currently emit empty Analyst Actions tabs.

Usage:
    from analyst_actions_helper import fetch_analyst_actions
    rows = fetch_analyst_actions(
        {'AAPL': {'company': 'Apple Inc', 'subsector': 'Tech'}, ...},
        lookback_days=30,
    )

Output rows match the schema each News Dashboard's Analyst Actions tab expects:
    {date, ticker, company, subsector, firm, action, from_grade, to_grade}
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta


def fetch_analyst_actions(
    tickers_info: dict,
    lookback_days: int = 30,
    skip: set[str] | None = None,
) -> list[dict]:
    """Fetch recent analyst rating changes for the given tickers.

    Args:
        tickers_info: mapping `ticker -> {company, subsector}` (or with `name`
            in place of `company`, and/or `category` in place of `subsector`;
            both naming conventions are accepted).
        lookback_days: only return actions from the last N days.
        skip: set of tickers to skip (e.g. inactive foreign listings without
            yfinance coverage).

    Returns:
        List of dicts: {date, ticker, company, subsector, firm, action,
        from_grade, to_grade}. Sorted descending by date. Empty list if
        yfinance is unavailable or no data was returned.
    """
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return []

    skip = skip or set()
    cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
    actions: list[dict] = []
    tickers = list(tickers_info.keys())
    total = len(tickers)

    for i, ticker in enumerate(tickers):
        if ticker in skip:
            continue
        info = tickers_info.get(ticker, {}) or {}
        company = info.get('company') or info.get('name') or ticker
        subsector = info.get('subsector') or info.get('category') or ''
        try:
            t = yf.Ticker(ticker)
            ud = t.upgrades_downgrades
            if ud is None or (hasattr(ud, 'empty') and ud.empty):
                continue
            for date_idx, row in ud.iterrows():
                grade_date = str(date_idx)[:19]
                if grade_date[:10] < cutoff:
                    continue
                firm = row.get('Firm', '') if hasattr(row, 'get') else (
                    str(row.iloc[0]) if len(row) > 0 else ''
                )
                to_grade = row.get('ToGrade', '') if hasattr(row, 'get') else (
                    str(row.iloc[1]) if len(row) > 1 else ''
                )
                from_grade = row.get('FromGrade', '') if hasattr(row, 'get') else (
                    str(row.iloc[2]) if len(row) > 2 else ''
                )
                action_val = row.get('Action', '') if hasattr(row, 'get') else (
                    str(row.iloc[3]) if len(row) > 3 else ''
                )
                actions.append({
                    'date': grade_date,
                    'ticker': ticker,
                    'company': company,
                    'subsector': subsector,
                    'firm': str(firm),
                    'action': str(action_val),
                    'from_grade': str(from_grade),
                    'to_grade': str(to_grade),
                })
        except Exception:
            pass
        if (i + 1) % 25 == 0:
            time.sleep(0.3)  # gentle pacing for yfinance

    actions.sort(key=lambda x: x['date'], reverse=True)
    return actions


if __name__ == '__main__':
    # Quick CLI test: pass JSON tickers_info on stdin and print row count.
    import json
    import sys
    info = json.load(sys.stdin)
    rows = fetch_analyst_actions(info)
    print(f'fetched {len(rows)} rows')
    if rows:
        print('first:', rows[0])
