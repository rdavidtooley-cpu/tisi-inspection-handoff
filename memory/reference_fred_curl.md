---
name: FRED curl fetches must use default User-Agent
description: fred.stlouisfed.org silently blocks custom -A strings; use curl default UA
type: reference
originSessionId: 43a58aad-d141-4c7f-8800-49108fe7643b
---
## Rule
When fetching FRED CSV endpoints (`https://fred.stlouisfed.org/graph/fredgraph.csv?id=...`) via curl, do NOT set a custom `-A` User-Agent. FRED silently blackholes non-standard UAs — requests hang until timeout with `curl exited 28`. Curl's default UA (e.g. `curl/8.x`) returns 200 OK immediately.

## Why
Discovered 2026-04-17 while debugging Oil & Gas morning pipeline FRED failures that had persisted silently for weeks. `-A 'OilGasIntel/1.0'` caused indefinite hangs; removing `-A` fixed all three tested endpoints (GASREGW, INDPRO, T10YIE) instantly. `-A "Mozilla/5.0"` also blocked — so it's not a whitelist of browsers, it specifically targets non-default UAs or particular patterns.

## How to apply
- Any Intel pipeline (Oil & Gas, Casino Gaming, Metal Mining, Inspection, Media Broadcasting) calling FRED: strip `-A` from the curl invocation.
- Keep `--max-time 45`, `--retry 2`, `--retry-delay 3`, `--http1.1` for resilience — those are fine.
- Works under LaunchAgent env where `env={'PATH': '/usr/bin:/bin'}` is set.
- Grep command to find offenders across all projects: `grep -rn "fred.stlouisfed.org" ~/Master\ Intelligence/ | grep "\-A "`.

## Reference implementation
`Oil_Gas_Intel/Dashboard/refresh_dashboard.py` around the `for series_id, label in FRED_SERIES.items()` loop.
