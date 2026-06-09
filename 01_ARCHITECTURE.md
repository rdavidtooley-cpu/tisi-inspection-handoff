# 01 — Architecture

## What this thing is

A daily-refreshing, password-protected web dashboard covering the global TIC/NDT (Testing/Inspection/Certification & Non-Destructive Testing) industry. Public-company-focused, with peripheral coverage of Flow Control and Mechanical/On-Site Services as adjacent industrial peers.

## The whole system on one page

```
┌────────────────────────────────────────────────────────────────┐
│  HOST MACHINE  (macOS, single laptop or workstation)           │
│                                                                │
│   LaunchAgent (cron)                                           │
│        │ fires daily at 5–7am ET                               │
│        ▼                                                       │
│   morning_pipeline.sh                                          │
│        │                                                       │
│        ├── osha_fetcher.py        ─→ Industry_Data/osha.json   │
│        ├── ir_fetcher.py          ─→ Industry_Data/ir.json     │
│        ├── gov_data_fetcher.py    ─→ Industry_Data/gov.json    │
│        ├── news_fetcher.py        ─→ Dashboard/news.json       │
│        ├── koyfin_transcripts.py  ─→ Companies/.../transcripts/│
│        ├── summarize_transcripts.py ─→ summaries.json          │
│        ├── edgar_fetcher.py       ─→ filings.json              │
│        ├── fetch_ma_rss.py        ─→ ma_deals_wire.json        │
│        ├── fetch_ma_edgar.py      ─→ ma_deals_edgar.json       │
│        └── refresh_inspection_dashboard.py                     │
│                │                                               │
│                │ fetches yfinance prices for 22 tickers        │
│                │ computes Inspection-11 and Flow&MOS-11 indices│
│                │ injects all JSON into 6 HTML templates        │
│                ▼                                               │
│         Dashboard/*.html  (6 generated dashboards)             │
│                │                                               │
│                ▼                                               │
│         git commit + push to GitHub                            │
│                │                                               │
└────────────────┼───────────────────────────────────────────────┘
                 │
                 ▼
   ┌─────────────────────────────────────────────────────────┐
   │  CLOUDFLARE PAGES                                        │
   │   ▶ auto-builds on git push                              │
   │   ▶ serves static HTML                                   │
   │   ▶ Pages Functions (/api/*) for subscribe + quotes      │
   │   ▶ KV namespace SUBSCRIBERS                             │
   └─────────────────────────────────────────────────────────┘
                 │
                 ▼
        End user (browser, password gate)
```

## Two ingestion modes

**Daily (automated):**
- Market data (prices, fundamentals) via yfinance
- News headlines via Google News RSS
- M&A wire deals via Google News RSS
- OSHA, gov data — varies by source

**Periodic (event-driven):**
- Earnings transcripts via Koyfin (when companies report)
- SEC filings via EDGAR (8-K, 10-K, 10-Q)
- Insider trading via SEC Form 4 (via `_shared/insider_tracker.py`)

## Six dashboards

| Page | Purpose | Template | Live file |
|---|---|---|---|
| 1 | Command Center (home) | index_template (in script) | `index.html` |
| 2 | Equities (price action) | `equities_template.html` (in script) | `TIC_NDT_Equities_Dashboard.html` |
| 3 | Company Summary (per-ticker deep dive) | `company_summary_template.html` (in script) | `TIC_NDT_Company_Summary.html` |
| 4 | Peer Analysis (cross-company benchmarks) | `peer_analysis_template.html` (in script) | `TIC_NDT_Peer_Analysis_Dashboard.html` |
| 5 | Industry Dashboard (OSHA + macro) | `industry_template.html` (in script) | `TIC_NDT_Industry_Dashboard.html` |
| 6 | News (RSS feed + AI summaries) | `news_template.html` (in script) | `TIC_NDT_News_Dashboard.html` |
| 7 | Earnings (transcripts + summaries) | `earnings_template.html` | `TIC_NDT_Earnings_Dashboard.html` |
| 8 | M&A (deals + multiples) | inline | `TIC_NDT_MA_Dashboard.html` |

Note: most templates are string literals inside `refresh_inspection_dashboard.py` (search for `TEMPLATE = """`). Only `earnings_template.html` is a separate file.

## Data layout on disk

```
project root/
├── _scripts/                   (Python pipeline, ~22 files)
├── _shared/                    (cross-cutting helpers, ~21 files)
├── Companies/                  (per-ticker folders with transcripts)
│   └── <Category>/<Ticker>/
│       ├── transcripts/        (raw .txt from Koyfin)
│       └── summaries.json      (Claude-summarized 5-section format)
├── Industry_Data/              (sector-wide JSON: OSHA, IR, gov)
├── Financials/                 (Excel models, per-ticker)
├── Newsletter/                 (drafts of email digest)
├── Reports/                    (one-off generated PDFs)
├── Dashboard/
│   ├── index.html              ← generated
│   ├── *_Dashboard.html        ← generated, 6 files
│   ├── earnings_template.html  ← edit this, not the generated file
│   ├── auth.js
│   ├── csv_export.js
│   ├── functions/api/*         (Pages Functions)
│   ├── transcripts/            (per-quarter HTML pages from summaries)
│   ├── market_data.json        (current snapshot)
│   ├── price_history.json      (5+ year history)
│   ├── ma_deals*.json
│   └── wrangler.toml
└── morning_pipeline.sh
```

## Tech stack

| Layer | Tech |
|---|---|
| Pipeline | Python 3 (stdlib + yfinance + requests) |
| Transcript fetch | Koyfin (no public API — Chrome cookie session) |
| Summarization | Anthropic Claude CLI |
| SEC data | EDGAR REST API |
| News | Google News RSS (free, zero tokens) |
| Frontend | Vanilla HTML/CSS/JS — no framework, no build step |
| Charts | Chart.js (CDN) |
| Hosting | Cloudflare Pages (free tier) |
| Functions | Cloudflare Pages Functions (Workers runtime) |
| Storage | Cloudflare KV (one namespace, SUBSCRIBERS) |
| Auth | SHA-256 password gate, localStorage session |
| Email | Resend API |
| Automation | macOS LaunchAgent |

## Why no framework / no build step

- One person operates this. React/Vue/Next add complexity without value.
- Pipeline output is HTML files. Cloudflare serves static. Simplest deploy possible.
- The receiving company's IT team can audit one file at a time.
- Total stack fits in one developer's head.

## Pipeline runtime

| Stage | Typical duration |
|---|---|
| OSHA + IR + gov fetchers | 1–3 min each |
| News collector | 2–5 min |
| Market data + chart prep (refresh_inspection_dashboard.py) | 8–12 min |
| Transcript downloads (only on earnings days) | 10–30 min |
| Transcript summarization (only when new transcripts exist) | 20–40 min |
| M&A pipeline (curated + 8-K + wire) | 2–5 min |
| HTML generation + git push | <1 min |

Total cold start: ~25 min. Steady-state daily: ~10 min.
