---
name: Inspection Intel Platform
description: TIC/NDT sector intelligence dashboard — 22 tickers across 5 categories, daily-refreshed, deployed on Cloudflare Pages
type: project
---

## What this project is

A daily-refreshing, password-protected web dashboard covering the global TIC/NDT (Testing/Inspection/Certification and Non-Destructive Testing) industry, with adjacent coverage of Flow Control and Mechanical/On-Site Services public peers.

Single-host pipeline (macOS LaunchAgent or Linux cron), Python-based fetchers, static HTML output, Cloudflare Pages hosting.

## Ticker universe — 22 tickers across 5 categories

- **NDT Services (5):** MG, TISI, TIC, OII, XPRO
- **Global NDT (4):** BVI.PA, ITRK.L, COTN.SW, SGSN.SW
- **NDT Adjacent (2):** TRNS, THR
- **Flow Control (6):** FLS, ROR.L, IMI.L, SPX.L, WEIR.L, WHD
- **Mech. & On-Site Services (5):** MTRX, PRIM, MTZ, CLH, FET

Defined in `_scripts/refresh_inspection_dashboard.py` → `TICKER_UNIVERSE`, `CATEGORY_ORDER`, `CATEGORY_COLORS`, `DISPLAY_TICKER`.

## Two named indices

- **Inspection-11** (TIC/NDT pure-play): NDT Services + Global NDT + NDT Adjacent. Constants → `INSPECTION_11_TICKERS`. Color #4fc3f7 (blue).
- **Flow & MOS-11** (industrial services adjacency): Flow Control + Mech. & On-Site Services. Constants → `FLOW_MOS_TICKERS`. Color #81c784 (green).

Both market-cap weighted, base 1000, compared against S&P 500 / Russell 2000 / XLI overlays. Both live on the home page (header KPI cards + side-by-side charts with MTD/QTD/YTD/LTM/5Y/10Y range selectors).

Compute function: `compute_basket_index(price_history, market_data, label, basket_tickers, logger)` — single function called twice.

**Per-ticker base price gotcha:** tickers added after `price_history`'s base_date use their own first-observed price as base. Otherwise newer additions silently fall out and the index returns None.

## Category colors

- NDT Services — blue (#4fc3f7)
- Global NDT — gold (#ffb300)
- NDT Adjacent — purple (#ab47bc)
- Flow Control — green (#81c784)
- Mech. & On-Site Services — orange (#ff9800)

## FX handling

CHF / GBP / EUR / AUD currencies auto-handled. **GBp (pence)** is auto-divided by 100 — known yfinance quirk where LSE-listed names return prices in pence not pounds.

## CIK registry (SEC EDGAR)

`_scripts/edgar_company_registry.json` maps ticker → SEC CIK for US-listed names. Foreign filers flagged `"active": false` and skipped by the EDGAR fetcher.

## Key scripts (in `_scripts/`)

1. `refresh_inspection_dashboard.py` — main engine, ~2,750 lines, generates all dashboards from templates
2. `osha_fetcher.py` — OSHA inspection/enforcement data
3. `ir_fetcher.py` — investor relations
4. `gov_data_fetcher.py` — government data
5. `news_fetcher.py` / `company_news_fetcher.py` — news aggregation
6. `koyfin_transcripts.py` — earnings transcript downloader
7. `summarize_transcripts.py` — Claude CLI summaries (5-section format)
8. `transcript_intelligence.py` / `analyze_transcripts.py` — transcript content extraction
9. `edgar_fetcher.py` / `edgar_exhibit_fetcher.py` — SEC filings
10. `finnhub_fetcher.py` — Finnhub API
11. `check_alerts.py` — email alerts
12. `koyfin_login_reminder.py` / `koyfin_refresh_token.py` — manual token mgmt
13. `morning_pipeline.sh` — pipeline orchestrator

## Transcript summary 5-section format

`summarize_transcripts.py` produces summaries with these section keys (the dashboard parser depends on them — do not rename):

1. **KEY HIGHLIGHTS** — bullet-point financial metrics (revenue, EPS, margins, guidance)
2. **SUMMARY** — 300–500 word narrative
3. **Q&A TAKEAWAYS** — key analyst questions and management responses
4. **QoQ COMPARISON** — sequential trend analysis
5. **KEY RISKS** — material risks flagged or implied

## 8 dashboard pages

| Page | Live file | Template source |
|---|---|---|
| Command Center | `index.html` | string literal in refresh script |
| Equities | `TIC_NDT_Equities_Dashboard.html` | string literal |
| Company Summary | `TIC_NDT_Company_Summary.html` | string literal |
| Peer Analysis | `TIC_NDT_Peer_Analysis_Dashboard.html` | string literal |
| Industry | `TIC_NDT_Industry_Dashboard.html` | string literal |
| News | `TIC_NDT_News_Dashboard.html` | string literal |
| Earnings | `TIC_NDT_Earnings_Dashboard.html` | `earnings_template.html` (separate file) |
| M&A | `TIC_NDT_MA_Dashboard.html` | string literal |

## Template overwrite rule

Live HTML files are build artifacts. The pipeline regenerates them every morning. Always edit the template — either the string literal inside `refresh_inspection_dashboard.py` or `earnings_template.html` for the earnings page. Hand edits to `*_Dashboard.html` files are silently overwritten.

## Standard page layout

```html
<body>
  <div class="ticker-bar" id="ticker-bar">...</div>
  <div class="nav-bar">...</div>
  <div class="container">
    <div class="page-header">...</div>
    <!-- content cards -->
  </div>
</body>
```

`page-header` must be INSIDE `container`. CSS must include `border-radius: var(--radius)` and `margin-bottom: var(--gap)`.

## Cloudflare deployment

- Pages project: `__PAGES_PROJECT_NAME__`
- KV namespace: `SUBSCRIBERS` for email subscribe/unsubscribe
- Pages Functions: `/api/quotes`, `/api/subscribe`, `/api/unsubscribe`, `/api/subscribers`

## Email digest (optional)

- Sender: `__FROM_EMAIL__` (Resend-verified domain)
- Admin: `__ADMIN_EMAIL__`
- Daily weekday digest via GitHub Actions or LaunchAgent

## Auth

Standalone single-password gate by default. SHA-256 hash in `auth.js`, 24hr session in localStorage. Session key configurable (e.g. `tisi_auth`). See `06_AUTH_OPTIONS.md` in the handoff package for the alternative per-user account model.

## Daily pipeline schedule

Single LaunchAgent at ~5:30 AM local time runs `morning_pipeline.sh`. The orchestrator chains all fetchers, then calls `refresh_inspection_dashboard.py`, then commits and pushes to git (which triggers Cloudflare Pages deploy).

## Critical rules

- `threads=False` on every `yf.download()` call (macOS DNS gotcha)
- Clear `__pycache__/` after editing any pipeline Python
- `python3 -u` or `PYTHONUNBUFFERED=1` for scripts piped to logs
- `trap notify_failure EXIT` in every shell orchestrator
- Numbers ≥ 1,000 use comma formatting
- Always include Adjusted EBITDA alongside reported EBITDA
- Q4 financials are always derived (FY − Q1 − Q2 − Q3)
- Two-column tables: Ticker column = ticker only, Company column = name only
- Every dashboard section needs a descriptive tooltip
