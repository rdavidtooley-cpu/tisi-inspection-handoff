# Inspection Intel — Project Briefing

TIC/NDT sector intelligence dashboard. Tracks 22 public companies across 5 categories, refreshed daily from yfinance, Koyfin, EDGAR, OSHA, and Google News RSS. Deployed on Cloudflare Pages with a password gate.

**Categories:** NDT Services · Global NDT · NDT Adjacent · Flow Control · Mech. & On-Site Services
**Indices:** Inspection-11 (TIC/NDT pure-play) · Flow & MOS-11 (industrial services adjacency)

---

## Architecture in one diagram

```
LaunchAgent (cron, 5am)
        │
        ▼
morning_pipeline.sh ─── calls 10+ Python fetchers in sequence
        │                  │ yfinance, Koyfin, EDGAR, OSHA, Resend
        ▼                  ▼
   *.json data files   refresh_inspection_dashboard.py
                                │
                                ▼ injects JSON into HTML templates
                          Dashboard/*.html (6 pages)
                                │
                                ▼ git commit + auto-deploy
                          Cloudflare Pages
                                │
                                ▼ password gate (auth.js)
                          end user
```

---

## Critical rules

- **Templates are source. Live HTMLs are build artifacts.** Always edit `*_template.html`. The morning pipeline regenerates `*_Dashboard.html` from the template every night and silently overwrites hand edits.
- **`threads=False` on every `yf.download()` call.** macOS DNS chokes on parallel lookups and the pipeline will hang.
- **Clear `__pycache__/` after editing any script the LaunchAgent runs.** Stale bytecode is a recurring source of "but I just fixed that" bugs.
- **`python3 -u` for any script piped to a logfile.** Python's stdout is block-buffered when piped; long pipeline steps look hung otherwise.
- **Numbers ≥ 1,000 use comma formatting on dashboards.** Always.
- **Show "Company Name (TICKER)" — not bare tickers** — in any single-column context. In two-column tables, Ticker column = ticker only, Company column = name only.
- **Every dashboard section needs a descriptive tooltip.** Info icons must be adjacent to the element; tooltips use `position: fixed` with JS positioning, never `position: absolute` inside an overflow container.
- **Always include Adjusted EBITDA alongside reported EBITDA** in any financial display or extraction.
- **Q4 financials are always derived** as `FY − Q1 − Q2 − Q3`. They are never directly reported. Enter FY from the 10-K and let Excel formula compute Q4.
- **After every code edit, deploy.** Cloudflare Pages dashboards must be redeployed in the same task. Never leave changes local.
- **After git merge/rebase, scan JSON files for conflict markers** (`<<<<<<<`, `=======`, `>>>>>>>`). They will silently break the dashboard renderer.
- **Pipeline shell scripts need `trap notify_failure EXIT`.** Success-path emails miss silent fails.
- **Bulk transcript loads** must call `summarize_transcripts.py` directly. Do not use the refresh script's embedded subprocess — it caps at 600s and silently fails.
- **MutationObservers that write to observed DOM must disconnect during writes.** Self-trigger loops freeze the browser.
- **`auth.js` must never set `document.visibility:hidden`** during validate. It causes Chrome renderer freeze on large dashboards.
- **Every sector site needs its own KV namespace IDs** in `wrangler.toml`. Don't copy-paste IDs across projects — they silently share KVs.

---

## Standard page layout (must follow exactly)

```html
<body>
  <div class="ticker-bar" id="ticker-bar">...</div>   <!-- sticky, top:0, full width -->
  <div class="nav-bar">...</div>                       <!-- sticky, top:32px, full width -->
  <div class="container">                              <!-- max-width:1500px, centered -->
    <div class="page-header">...</div>                <!-- INSIDE container -->
    <!-- content cards -->
  </div>
</body>
```

`page-header` MUST be inside `container`. Outside, it goes edge-to-edge and looks broken.

`page-header` CSS must include `border-radius: var(--radius)` and `margin-bottom: var(--gap)`.

---

## Ticker bar live refresh

Every dashboard page with a ticker container must end with a self-contained IIFE that calls `/api/quotes` every 60s. Without it, tickers freeze at the morning snapshot.

Container IDs in use: `ticker-track` (with `.tk-sym` / `.tk-price`), `ticker-inner` (with `.t-sym` / `.t-price` / `.t-chg`), `tickerTrack`.

Use `_shared/fix_tickers.py` (idempotent, marker `__ticker_live_v1`) to apply this pattern to any new page.

---

## Chart range controls

Every chart over a time series must include the standard range bar:
- Preset buttons: MTD · QTD · YTD · LTM · 5Y · 10Y
- Two `<input type="date">` for custom start/end
- Default load: YTD
- Chart function signature `(startDate, endDate)`; destroy and rebuild on range change

---

## Where things live

- `_scripts/` — Python pipeline (data fetchers + dashboard generator)
- `Dashboard/` — HTML templates + generated dashboards + auth + Pages Functions
- `_shared/` — helpers (M&A pipeline, financial history, fix scripts)
- `morning_pipeline.sh` — the daily orchestrator
- `wrangler.toml` — Cloudflare Pages config (KV bindings)

---

## Before calling something done

- Edits to templates AND live HTMLs are deployed
- Pipeline runs end-to-end without errors
- Live site (not local) shows the change
- JSON data files contain valid JSON (no conflict markers)
- If a LaunchAgent was edited, it was reloaded (`launchctl unload + load`)
