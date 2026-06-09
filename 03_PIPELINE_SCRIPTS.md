# 03 — Pipeline Scripts

Two folders contain Python code:

- `_scripts/` — pipeline scripts (data fetchers + dashboard generator) specific to this project
- `_shared/` — helpers originally designed to operate across multiple sector sites

## `_scripts/` — the pipeline

| File | Role | Runs daily? |
|---|---|---|
| `refresh_inspection_dashboard.py` | THE engine. Fetches yfinance, computes indices, injects JSON into HTML templates. ~2,750 lines. | Yes |
| `osha_fetcher.py` | Pulls OSHA inspection + enforcement data | Yes |
| `ir_fetcher.py` | Investor relations data scraping | Yes |
| `gov_data_fetcher.py` | Government data (BLS, FRED, etc.) | Yes |
| `news_fetcher.py` | RSS news aggregator (sector-level) | Yes |
| `company_news_fetcher.py` | Per-ticker news | Yes |
| `finnhub_fetcher.py` | Finnhub API for company profiles | Periodic |
| `edgar_fetcher.py` | SEC filings index | Daily |
| `edgar_exhibit_fetcher.py` | SEC filing exhibits (deep pull) | On-demand |
| `koyfin_transcripts.py` | Downloads earnings transcripts from Koyfin | When earnings drop |
| `summarize_transcripts.py` | Claude CLI → 5-section transcript summaries | After download |
| `transcript_intelligence.py` | Extract financials/themes from transcripts | After summarize |
| `analyze_transcripts.py` | Cross-quarter narrative analysis | On-demand |
| `koyfin_login_reminder.py` | Prints instructions to refresh Koyfin token | Manual |
| `koyfin_refresh_token.py` | Extracts Koyfin token from Chrome cookie DB | Manual |
| `check_alerts.py` | Sends email alerts when thresholds breach | Yes |
| `run_summarizer.sh` | Helper wrapper for summarize_transcripts.py | On-demand |
| `morning_pipeline.sh` | (duplicate of root-level — same orchestrator) | — |

### The engine: `refresh_inspection_dashboard.py`

Single ~2,750-line file. Does everything dashboard-generation related:

1. Loads ticker universe + category metadata
2. Pulls fresh prices via yfinance (`threads=False` — see CLAUDE.md)
3. Loads `price_history.json` (5+ year cache), appends today's bar
4. Computes the two named indices via `compute_basket_index()` — one function called twice
5. Pulls fundamental data (market cap, P/E, dividend yield) from yfinance
6. Loads M&A deals (curated + 8-K + RSS wire) from JSON
7. Loads news, summaries, OSHA, IR, gov data
8. Builds 6 large data blobs (one per dashboard)
9. Replaces `__PLACEHOLDER__` tokens in 6 HTML template strings
10. Writes 6 `*_Dashboard.html` files
11. Writes `market_data.json`, `industry_indicators.json`, etc.
12. Auto-commits to git, pushes (if configured)

**Most templates are string literals inside this file.** Search for `TEMPLATE = """`. Only `earnings_template.html` is a separate file.

### Earnings transcripts: 5-section format

`summarize_transcripts.py` produces summaries with these sections (do not change the keys — the dashboard parser depends on them):

1. **KEY HIGHLIGHTS** — bullet-point financial metrics (revenue, EPS, margins, guidance)
2. **SUMMARY** — 300–500 word narrative brief
3. **Q&A TAKEAWAYS** — key analyst questions + management responses
4. **QoQ COMPARISON** — sequential trend analysis
5. **KEY RISKS** — material risks flagged or implied

The summarizer calls the Claude CLI (`claude` binary in PATH). It expects an API key or session already configured at the OS level.

## `_shared/` — cross-cutting helpers

These were built to run across multiple sector projects. For a single-sector deployment, see the cross-sector note in `REDACTION_NOTES.md`.

| File | Role |
|---|---|
| `financials_history.py` | 3-statement model loader; expects dict-keyed-by-ticker or list-of-strings, never list-of-dicts |
| `ma_core.py` | M&A deal data class + dedupe |
| `fetch_ma_rss.py` | Google News RSS → M&A wire deals (free, zero tokens) |
| `fetch_ma_edgar.py` | SEC 8-K → M&A deals |
| `enrich_ma_multiples.py` | Adds EV/EBITDA, EV/Revenue to M&A deals |
| `apply_ma_curated_multiples.py` | Hand-curated multiple overrides |
| `build_ma_pages.py` | Generates `Dashboard/transcripts/<DEAL>.html` per deal |
| `pipeline_notify.py` | Emails on pipeline success/failure via Resend |
| `fix_tickers.py` | Idempotent patcher — installs live ticker-bar IIFE on dashboards |
| `fix_ticker_change.py` | Fixes change_pct field mismatch on ticker bars |
| `fix_pipeline_change_pct.py` | Pipeline-source fix for ticker change_pct |
| `fix_info_tooltips.py` | Idempotent tooltip CSS/JS patcher |
| `add_period_selector.py` | Adds MTD/QTD/YTD/LTM/5Y/10Y range controls to chart cards |
| `inject_csv_export.py` | Wires CSV export button into tables |
| `analyst_actions_helper.py` | Analyst rating change aggregator |
| `insider_tracker.py` | SEC Form 4 insider trades |
| `short_interest.py` | Short interest data aggregator |
| `earnings_tracker.py` | Earnings calendar generator |
| `edgar_news_injector.py` | Injects SEC filing alerts into news dashboard |
| `audit_model.py` | Auditor for 3-statement Excel models |
| `check_template_drift.py` | Detects template/live HTML drift |

## `morning_pipeline.sh`

The orchestrator. ~140 lines of bash. Walks through fetchers in order, logs each step, traps EXIT for failure notification.

Key patterns to preserve:

```bash
set -euo pipefail                             # fail fast
trap notify_failure EXIT                       # always run notification
export PYTHONUNBUFFERED=1                      # unbuffered stdout
```

If you change which scripts run, update both the body and the success/failure notification.

## Pipeline-level rules (worth repeating from CLAUDE.md)

- `threads=False` on every `yf.download()` — macOS DNS chokes on parallel lookups
- Clear `__pycache__/` after editing any pipeline Python — stale bytecode bites
- `python3 -u` (or `PYTHONUNBUFFERED=1`) for scripts piped to logs
- Scrub JSON files for git-conflict markers after any merge/rebase
- Don't use the embedded transcript-summarize subprocess for bulk loads — it caps at 600s and silently fails. Always run `summarize_transcripts.py` directly.
- Pipeline failure notification (`trap notify_failure EXIT`) is non-negotiable — success-path-only emails miss silent fails.

## CRLF gotcha

If you edit any `.sh` script on Windows (or paste into an editor that uses CRLF), the script will spawn phantom `<CR>` directories when constructing paths from variables. Check with `file morning_pipeline.sh` and fix with `tr -d '\r' < script.sh > script.sh.tmp && mv script.sh.tmp script.sh`.
