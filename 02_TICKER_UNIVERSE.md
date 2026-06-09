# 02 — Ticker Universe

22 tickers across 5 categories. Defined in `_scripts/refresh_inspection_dashboard.py` in three constants: `TICKER_UNIVERSE`, `CATEGORY_ORDER`, `CATEGORY_COLORS`.

## The 22 tickers

### NDT Services (5) — color: blue (#4fc3f7)
US-listed pure-play TIC/NDT providers.

| Ticker | Company | Notes |
|---|---|---|
| MG | Mistras Group | NDT services |
| TISI | Team, Inc. | Inspection + heat-treating + mechanical services |
| TIC | Team Industrial Services (parent ref) | confirm against current listing |
| OII | Oceaneering International | subsea inspection + ROV services |
| XPRO | Expro Group | well intervention + integrity services |

### Global NDT (4) — color: gold (#ffb300)
International peers, multi-currency. **FX handling required.**

| Ticker | Company | Currency |
|---|---|---|
| BVI.PA | Bureau Veritas | EUR |
| ITRK.L | Intertek | GBp (pence — auto-divided by 100) |
| COTN.SW | Comet Holding (NDT exposure) | CHF |
| SGSN.SW | SGS SA | CHF |

### NDT Adjacent (2) — color: purple (#ab47bc)
Public companies with NDT-related lines of business.

| Ticker | Company |
|---|---|
| TRNS | Transcat (calibration + lab services) |
| THR | Thermon Group (process heating, adjacent industrial) |

### Flow Control (6) — color: green (#81c784)
Valves, actuators, flow products — adjacent industrial services.

| Ticker | Company | Currency |
|---|---|---|
| FLS | Flowserve | USD |
| ROR.L | Rotork | GBp |
| IMI.L | IMI plc | GBp |
| SPX.L | Spirax Group | GBp |
| WEIR.L | Weir Group | GBp |
| WHD | Cactus Inc. | USD |

### Mech. & On-Site Services (5) — color: orange (#ff9800)
Pipeline/industrial services, public proxies for private peers (TDW, Stats Group, Ion Pro, Colt, WeldFit, HydroChem/PSC, ISS).

| Ticker | Company |
|---|---|
| MTRX | Matrix Service Co |
| PRIM | Primoris Services |
| MTZ | MasTec |
| CLH | Clean Harbors |
| FET | Forum Energy Technologies |

## Two named indices

Defined in `refresh_inspection_dashboard.py` constants `INSPECTION_11_TICKERS` and `FLOW_MOS_TICKERS`.

| Index | Constituents | Color | Purpose |
|---|---|---|---|
| **Inspection-11** | NDT Services + Global NDT + NDT Adjacent (11 tickers) | blue (#4fc3f7) | TIC/NDT pure-play index |
| **Flow & MOS-11** | Flow Control + Mech. & On-Site Services (11 tickers) | green (#81c784) | Adjacent industrial services index |

Both are:
- Market-cap weighted
- Base 1000
- Compared against S&P 500, Russell 2000, and XLI overlays
- Shown on the home page (header KPI cards + side-by-side charts with MTD/QTD/YTD/LTM/5Y/10Y range selectors)
- Computed by single function `compute_basket_index(price_history, market_data, label, basket_tickers, logger)` — called twice

**Per-ticker base price gotcha:** tickers added after the price_history base_date use their own first-observed price as base. Otherwise newer additions silently fall out and the index returns None.

## Display ticker overrides

Some tickers display differently than their yfinance symbol. Defined in `DISPLAY_TICKER` dict in `refresh_inspection_dashboard.py`:

| yfinance symbol | Display as |
|---|---|
| BVI.PA | BVI |
| ITRK.L | ITRK |
| COTN.SW | COTN |
| SGSN.SW | SGSN |
| ROR.L | ROR |
| IMI.L | IMI |
| SPX.L | SPX |
| WEIR.L | WEIR |

## Koyfin ticker overrides

Some LSE tickers need explicit `prefer_us=False` to find the right transcript. Defined in `koyfin_transcripts.py` → `TICKER_OVERRIDES`:

```python
TICKER_OVERRIDES = {
    "ROR.L": {"prefer_us": False},
    "IMI.L": {"prefer_us": False},
    "SPX.L": {"prefer_us": False},
    "WEIR.L": {"prefer_us": False},
}
```

## CIK registry (SEC EDGAR)

`_scripts/edgar_company_registry.json` maps ticker → SEC CIK for US-listed names. Foreign filers (BVI.PA, ITRK.L, COTN.SW, SGSN.SW, ROR.L, IMI.L, SPX.L, WEIR.L) are flagged `"active": false` and skipped by the EDGAR fetcher.

## FX handling

`refresh_inspection_dashboard.py` auto-detects currency from yfinance metadata and converts to USD for market-cap aggregation. **GBp (pence)** is auto-divided by 100 — there's a known yfinance quirk where ITRK.L and other LSE-listed names return prices in pence not pounds.

## Changing the universe

To add a ticker:

1. Add to `TICKER_UNIVERSE` dict in `refresh_inspection_dashboard.py` (key = ticker, value = `{"category": "...", "name": "..."}`)
2. If US-listed: add CIK entry to `_scripts/edgar_company_registry.json`
3. If foreign: add inactive entry to the registry with `"active": false`
4. If LSE-listed and needs Koyfin tweak: add to `TICKER_OVERRIDES` in `koyfin_transcripts.py`
5. If part of a named index: add to `INSPECTION_11_TICKERS` or `FLOW_MOS_TICKERS`
6. Create folder: `Companies/<Category>/<Ticker>/` with `transcripts/` subdir
7. Re-run pipeline

To remove a ticker: reverse the above. Index composition changes also need to be reflected in label strings, count strings, and tooltips on the dashboards.

## TISI-specific note

TISI (Team, Inc.) is part of the NDT Services category in the current universe. If TISI is the **host company building this site**, decide:

- **Keep TISI in:** treat self as one of many comps, makes for internal benchmarking
- **Take TISI out:** cleaner for an external-facing site, removes "we ranked ourselves Nth"

Removal is one line in `TICKER_UNIVERSE` plus a re-run.
