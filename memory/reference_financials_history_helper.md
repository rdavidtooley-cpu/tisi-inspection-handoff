---
name: _shared/financials_history.py calling convention
description: fetch_historical_financials accepts dict keyed by ticker OR list of ticker strings — never list of dicts
type: reference
originSessionId: 43a58aad-d141-4c7f-8800-49108fe7643b
---
## Rule
`_shared/financials_history.py::fetch_historical_financials(tickers, logger)` accepts two shapes:
1. A **dict keyed by ticker** (the canonical `market_data` shape) — this is what Casino and Metal Mining pass.
2. A **list of ticker strings** (e.g. `['XOM', 'CVX', ...]`).

It does NOT accept a list of per-ticker dicts. If you have a list of records, extract ticker strings first: `[r['ticker'] for r in records if r.get('ticker')]`.

## Why
Discovered 2026-04-17. Oil & Gas `refresh_dashboard.py` was passing `cleaned` (a list of per-ticker dicts) to the helper. The helper's fallback `symbols = list(tickers)` branch then treated each dict as a ticker symbol, producing:
- `yf.Ticker failed: 'dict' object has no attribute 'upper'`
- `cannot use 'dict' as a dict key (unhashable type: 'dict')`

The injection was wrapped in try/except, so the pipeline silently reported "all steps succeeded" while the Financials tab period selector had no data — a hidden regression.

## How to apply
- When cloning a refresh script from another Intel project, check the call site for `fetch_historical_financials` or `_fetch_historical_financials`.
- Verify the first arg is either the dict-shaped `market_data` or a ticker-string list.
- Grep for bad-shape callers: `grep -rn "_fetch_historical_financials\|fetch_historical_financials" ~/Master\ Intelligence/ --include="*.py"` and inspect each arg.
- Reference good callers: Metal Mining at `Metal_Mining_Intel/_scripts/refresh_metal_mining_dashboard.py` (passes dict), Casino Gaming (passes dict).
