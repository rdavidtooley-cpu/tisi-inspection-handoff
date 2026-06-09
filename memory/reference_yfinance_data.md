---
name: yfinance Data Source Reference
description: What yfinance provides and does not provide, known gotchas and deprecated attributes
type: reference
originSessionId: 6bf54a73-9f01-46f0-8fd3-9a9851f8f3ff
---
## Earnings Surprise Data
- `stock.earnings_dates` — returns ~25 rows (6 years) with columns: EPS Estimate, Reported EPS, Surprise(%)
- First row is typically the next upcoming earnings date (Reported EPS and Surprise will be NaN)
- Requires `lxml` package (`pip3 install lxml`) — will error without it
- Revenue actual vs estimate is NOT available through this endpoint
- `stock.quarterly_earnings` — deprecated, returns None. Do not use.
- `stock.earnings` — deprecated, shows deprecation warning pointing to income_stmt

## NaN Handling
- Some older quarters have EPS Estimate but NaN for Surprise(%). Always filter with `math.isnan()` after converting to float.
- Future earnings dates have NaN for Reported EPS — skip these rows.

## macOS DNS Safety (CRITICAL)
- `threads=False` on all `yf.download()` calls — macOS DNS thread pool chokes on parallel lookups
- `time.sleep(0.3)` between individual `yf.Ticker(t)` attribute calls
- See lessons.md #3 for full background

## `threads=` kwarg scope — only `yf.download()`, NOT `Ticker.history()`
- `yf.Ticker(t).history(period="1y")` does NOT accept `threads=` — raises `TypeError: history() got an unexpected keyword argument 'threads'` in current yfinance
- `Ticker.history()` is already single-ticker/sequential, so DNS safety doesn't apply
- If an every-ticker loop starts silently failing and your JSON shrinks to only the fallback fields in the except branch, check for `.history(..., threads=...)`
- Grep guard: `\.history\([^)]*threads` must return zero matches across any refresh script
- See lessons.md #22 for full background

## Shared Scripts Using yfinance
- `_shared/earnings_tracker.py` — earnings beat/miss history across all 4 Intel projects
- Each project's `refresh_dashboard.py` — market data collection
