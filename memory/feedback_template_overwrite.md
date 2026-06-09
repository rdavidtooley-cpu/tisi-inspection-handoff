---
name: Always patch the template, not just the live HTML
description: Every Intel sector dashboard has *_template.html files that the morning refresh copies over the live HTML. Hand edits to the live file silently revert the next morning unless the template is patched too.
type: feedback
originSessionId: 8c8c4e3a-a921-47d1-a25a-6df1a7e8d1f5
---
**Rule:** Before editing any `*_Dashboard.html` or `index.html` under `*_Intel/Dashboard/`, check for a matching `*_template.html` in the same directory. If one exists, **edit BOTH** in the same patch.

**Why:** The morning pipeline (`_scripts/refresh_*.py`) does `shutil.copy2(template.html, live.html)` every run before injecting fresh market data. Any change made only to the live file gets clobbered overnight. This bit me on 2026-04-27 when an earlier-session Inspection Earnings transcript fix had vanished by the next morning, and the same uncorrected bug was duplicated across Casino and Metal Mining because the template was never patched there either.

**How to apply:**
1. Before editing any live dashboard file, run `ls *_template.html` in the directory.
2. If a template exists, apply identical edits to both files.
3. To find ALL live files generated from templates on a given site, grep its refresh script: `grep -n "_template.html" _scripts/refresh_*.py`
4. Common pairs across all 14 Intel sites:
   - `earnings_template.html` → `<X>_Earnings_Dashboard.html`
   - `equities_template.html` → `<X>_Equities_Dashboard.html`
   - `industry_template.html` → `<X>_Industry_Dashboard.html`
   - `news_template.html` → `<X>_News_Dashboard.html`
   - `ma_template.html` → `<X>_MA_Dashboard.html`
   - `peer_analysis_template.html` → `<X>_Peer_Analysis(_Dashboard).html`
   - `company_summary_template.html` → `<X>_Company_Summary.html`
   - `index_template.html` → `index.html`
5. After deploy, the next morning's pipeline should be a no-op (not a regression). If a fix "mysteriously reverts," the template is the first place to check.

**Cross-project scope:** Applies to all 14 sector sites — Aerospace_Defense, Autos, Casino_Gaming, Chemicals, Homebuilders, Inspection, Media_Broadcasting, Metal_Mining, Oil_Gas, Power_Utilities, Rail_Logistics, REITs, Semiconductors, Shipping. Same `_scripts/refresh_*.py` architecture across every one.

**Enforcement (added 2026-04-27):** `_shared/check_template_drift.py` and the wrapper `_shared/deploy_with_drift_check.sh` mechanically enforce this rule — diff each template against its live counterpart, normalize away injected data blobs, fail the deploy if structural drift exists. Default deploy command is now:
```
./_shared/deploy_with_drift_check.sh <Site_Intel>
```
If drift is flagged, run `python3 _shared/check_template_drift.py <Site_Intel> --diff` to inspect, fix, retry. Use `--force` only after reviewing. The tool auto-discovers all `*_Intel/Dashboard/` directories so it works on new sector sites automatically. The `--fail-on-drift` flag returns exit 1, suitable for any pre-deploy hook or CI check.
