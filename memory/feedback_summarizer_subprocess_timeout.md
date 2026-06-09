---
name: Run summarizer directly for bulk transcript backfills
description: Embedded refresh→summarizer subprocesses across Intel sites cap at 600s — bulk loads (>10 transcripts) silently fail; always run summarizer standalone before refresh
type: feedback
originSessionId: af1a57e5-5408-42d2-85b3-6688e1c9a2a8
---
When bulk-adding transcripts on any Intel site (Inspection, Oil & Gas, Casino, Metal Mining, etc.), do NOT rely on the embedded summarizer subprocess inside `refresh_*_dashboard.py`. That subprocess has a `timeout=600` cap (verified on Inspection Intel `refresh_inspection_dashboard.py:2447`, same pattern likely across other sites). Each Claude CLI summarization takes ~30s, so >20 transcripts will hit the cap. The `subprocess.TimeoutExpired` exception is caught and logged as a non-fatal warning while the outer pipeline reports "completed successfully" — silent failure.

**Why:** This bit on the 2026-04-22 Inspection Intel valve/MOS expansion. 37 new transcripts needed summaries; the refresh reported success but `transcript_summaries.json` count never grew (236 → 236). Caught only via direct verification of the JSON file. Required a 30-min standalone summarizer run + second refresh.

**How to apply:** Whenever bulk-loading transcripts (new tickers, ticker uplistings, history backfill, >10 files at once):

1. Download via `_scripts/koyfin_transcripts.py --category X --recent N`
2. Trim if needed (sort by year/quarter, keep last N)
3. **Run summarizer DIRECTLY in background** — NOT via the refresh script:
   ```
   python3 _scripts/summarize_transcripts.py 2>&1 | tail -100
   ```
   Use `run_in_background: true`; expect ~35s × N transcripts runtime.
4. Verify summary count grew:
   ```
   python3 -c "import json; print(len(json.load(open('Companies/transcript_summaries.json'))))"
   ```
5. THEN run refresh — it'll inject the new summaries into HTML pages and auto-deploy.

For routine daily pipeline work (1-3 new transcripts per morning), the embedded subprocess is fine — the 600s cap is sized for that.

If you want a permanent fix: lift the refresh's subprocess timeout to 3600s AND change the success-detection logic to verify `transcript_summaries.json` count actually increased before logging success.
