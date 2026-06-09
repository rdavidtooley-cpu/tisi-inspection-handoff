# 04 — Dashboard Pages

## Six pages, one consistent layout

| # | Page | Live file | Source of template |
|---|---|---|---|
| 1 | Command Center | `index.html` | string literal in `refresh_inspection_dashboard.py` |
| 2 | Equities Dashboard | `TIC_NDT_Equities_Dashboard.html` | string literal in script |
| 3 | Company Summary | `TIC_NDT_Company_Summary.html` | string literal in script |
| 4 | Peer Analysis | `TIC_NDT_Peer_Analysis_Dashboard.html` | string literal in script |
| 5 | Industry Dashboard | `TIC_NDT_Industry_Dashboard.html` | string literal in script |
| 6 | News Dashboard | `TIC_NDT_News_Dashboard.html` | string literal in script |
| 7 | Earnings Dashboard | `TIC_NDT_Earnings_Dashboard.html` | **`earnings_template.html`** (separate file) |
| 8 | M&A Dashboard | `TIC_NDT_MA_Dashboard.html` | string literal in script |

8 pages live, 7 templates — Command Center + 5 dashboards have their templates inline in `refresh_inspection_dashboard.py`. Search the file for `TEMPLATE = """` to find each block.

## ⚠️ Template vs live file rule

**Live HTML files are build artifacts. The pipeline regenerates them every morning.**

If you hand-edit a `*_Dashboard.html` file directly, the next pipeline run silently overwrites it. Always edit the template:

- For the standalone `earnings_template.html`: edit that file directly
- For inline templates: edit the string literal inside `refresh_inspection_dashboard.py`

After editing either, you can either:
1. Re-run `python3 _scripts/refresh_inspection_dashboard.py` (full pipeline)
2. Run just the template-render portion (no re-fetch)

## Standard page layout

Every page must follow this exact HTML structure:

```html
<body>
  <div class="ticker-bar" id="ticker-bar">...</div>   <!-- sticky top:0, z-index:1001 -->
  <div class="nav-bar">...</div>                       <!-- sticky top:32px, z-index:1000 -->
  <div class="container">                              <!-- max-width:1500px, centered -->
    <div class="page-header">...</div>                <!-- INSIDE container -->
    <!-- content cards go here -->
  </div>
</body>
```

**Critical:** `page-header` must be INSIDE `container`. If it's outside, it spans full viewport width edge-to-edge and looks broken.

### Required `page-header` CSS

```css
.page-header {
  background: linear-gradient(135deg, #1a1d29 0%, #16213e 100%);
  border-bottom: 2px solid var(--accent);
  padding: 28px 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
  border-radius: var(--radius);    /* REQUIRED — rounded corners */
  margin-bottom: var(--gap);       /* REQUIRED — spacing below header */
}
```

### Required nav-bar tail

Every page's nav-bar must end with this exact structure:

```html
    <div style="flex:1"></div>
    <a href="#" onclick="cgiLogout();return false" style="color:#9aa0a6;font-size:12px;">Logout</a>
</div>
```

(If using user-account auth, also include an Admin link before Logout.)

**Never use shell `sed` to edit this** — it corrupts the `<a>` tag structure.

## CSS theme system

Dark Bloomberg-inspired theme. Defined as CSS custom properties:

```css
:root {
  --bg:        #0d1117;
  --card-bg:   #161b22;
  --border:    #30363d;
  --text:      #e6edf3;
  --text-dim:  #9aa0a6;
  --accent:    #4fc3f7;
  --positive:  #4caf50;
  --negative:  #f44336;
  --radius:    8px;
  --gap:       16px;
}
```

Category colors are used consistently across all dashboards:

- NDT Services: blue `#4fc3f7`
- Global NDT: gold `#ffb300`
- NDT Adjacent: purple `#ab47bc`
- Flow Control: green `#81c784`
- Mech. & On-Site Services: orange `#ff9800`

## Ticker bar — live refresh rule

Every dashboard page with a ticker container must end with a self-contained IIFE that calls `/api/quotes` every 60s. Without it, prices freeze at the morning snapshot.

Container IDs across the codebase: `ticker-track` (with `.tk-sym`/`.tk-price` classes), `ticker-inner` (with `.t-sym`/`.t-price`/`.t-chg`), `tickerTrack`.

Company Summary pages need null-guards on `q.display`, `q.price`, `q.changePct` — unguarded `.toFixed()` on null produces "undefined" text.

Use `_shared/fix_tickers.py` (idempotent, marker `__ticker_live_v1`) to install this pattern on any page.

## Chart range controls

Every chart over a time series must include the standard range bar:

- Preset buttons: MTD · QTD · YTD · LTM · 5Y · 10Y
- Two `<input type="date">` for custom start/end
- Default load: YTD
- Chart function signature `(startDate, endDate)`; destroy and rebuild on range change

Uses `calcDateRange(preset)` and `setRange(preset, btn)` / `renderFromInputs()` helper pattern. CSS class: `.range-controls` placed above the canvas inside the card.

## Static fallback data

When a section's pipeline data is empty (e.g. `market_share: []`), define a `*_STATIC` JS object with hardcoded baseline values and use it as fallback:

```javascript
var SECTION_STATIC = { items: [...] };
function renderTab() {
  var d = INDUSTRY_DATA.section || {};
  var items = (d.items && d.items.length) ? d.items : SECTION_STATIC.items;
  // render items
}
```

This ensures sections always show something useful even when the pipeline hasn't populated them yet.

## Tooltips

Every dashboard section needs a descriptive `?` info icon next to its title. Tooltip implementation rules:

- Use `position: fixed` with JavaScript positioning relative to the icon
- **Never** use `position: absolute` inside an overflow container — the tooltip gets clipped
- The icon must be adjacent to the element it explains (not floating in a corner)
- Use `_shared/fix_info_tooltips.py` to patch existing pages

## Number formatting

- Numbers ≥ 1,000 use comma formatting: `12,345` not `12345`
- Currency: `$1,234` not `$1234`
- Show "Company Name (TICKER)" — not bare tickers — in any single-column context
- Two-column tables: Ticker column = ticker only, Company column = name only

## Worked examples

The shipped `Dashboard/*.html` files in `source/` are real production outputs. They demonstrate every layout rule above. Use them as visual reference even though they'll be regenerated on first pipeline run.
