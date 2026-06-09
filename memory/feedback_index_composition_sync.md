---
name: Index composition must sync with universe composition
description: When tickers are added/removed on any Intel site, all named indices must be updated in the same task — composition, weights, label, tooltip, narrative, count strings
type: feedback
originSessionId: 2f429244-4337-49c2-bfb0-8c730cfd0c4d
---
Whenever the company composition changes on any Intel site (Oil & Gas, Inspection, Casino, Metal Mining, Media, or any sector site with a named composite index like OG-10), ALL named indices must be reviewed and updated in the same task.

**Why:** On 2026-04-27 Robert flagged that Inspection Intel's home page still showed an "NDT-10 Index" five days after the universe was expanded from 10 → 22 tickers across 5 categories. The compute function was mathematically already tracking all 22 (because it weighted from `price_history[dates[-1]].get('market_caps')`), so the displayed number was misleading — a value labelled "NDT-10" that silently included Flow Control + MOS tickers. Plus the tooltip still said "three categories" when there were five. Whoever does the universe expansion must own the index pass too — leaving it as a follow-up means the named index lies until someone notices.

**How to apply:** Audit checklist on every universe change:
1. `TICKER_UNIVERSE` and `CATEGORY_ORDER` updated.
2. Index compute function's basket subsets updated (or split into multiple baskets — see below).
3. Injection payload keys (`<basket>_current`, `<basket>_daily_pct`, `<basket>_index`, etc.) consistent across refresh script and HTML consumers.
4. Home-page header card, KPI card, chart canvas, range-selector IDs renamed to match.
5. Every tooltip mentioning a count ("all 11 tracked", "three categories") or a category list updated.
6. Briefing narrative text updated.
7. Dead code from prior index versions deleted (don't leave stale `INJECTED_NDT10` blocks or dead `renderNdt10()` functions behind).

**When to split rather than rebrand:** If the new tickers don't fit the existing index thematically (e.g. adding industrial-services adjacencies to a TIC/NDT pure-play index), split into multiple baskets (Inspection-11 + Flow & MOS-11) rather than broadening the original. If you find yourself renaming "X-10" to "X-22", you've already drifted past step 7 — better either composition-neutral names ("Sector Index") or a fixed basket with parallel adjacency baskets.

**Compute gotcha:** Tickers added after `price_history`'s `base_date` won't appear in `base_prices`, so a naive "ret = price / base_prices[ticker]" loop drops them silently and the new basket's index_series stays empty (function returns None with no warning). Fix: walk forward to find each ticker's earliest non-zero price and use that as its individualized base. This was the root cause of Flow & MOS-11 returning None on first run.

**Cross-project:** Applies to every Intel site with a named composite. Verify before declaring any universe-expansion task done.
