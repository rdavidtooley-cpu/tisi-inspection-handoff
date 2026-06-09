---
name: Python stdout buffering hides progress in pipeline logs
description: Long Python steps in shell pipelines look hung because stdout is block-buffered when redirected; use python3 -u or PYTHONUNBUFFERED=1
type: reference
originSessionId: a7f21582-94bf-4fe1-bc5e-8011f2fddae9
---
When a shell pipeline runs `python3 script.py >> logfile 2>&1`, Python's stdout is block-buffered (not line-buffered) because the destination is a regular file, not a TTY. `print()` calls accumulate in a 4-8KB buffer and only flush at process exit or buffer-full. The log file appears frozen even when the script is working correctly.

**Symptom:** Long-running Python step in a pipeline (PDF parsing, transcript summarization, big data extraction) looks "stuck." Log file last line shows the step starting, no further output for 30+ minutes. Process is alive at 99% CPU.

**First diagnostic before assuming a hang:**
1. `ps -p <pid> -o %cpu,etime,command` — is CPU > 0 and process still running?
2. Was Python launched with `-u` or under `PYTHONUNBUFFERED=1`?

If CPU is pegged and Python is buffered, the script is working fine — wait for it.

**Fix going forward:** In all pipeline shell scripts, launch Python with `-u` (e.g. `$PYTHON -u ikn_pdf_parser.py >> "$LOG_FILE"`) or export `PYTHONUNBUFFERED=1` at the top of the script. Cheap insurance against false-hang diagnoses across IKN, transcript summarizer, EDGAR fetcher, and any other long Python steps in morning pipelines.

**Original incident:** 2026-04-28 spent ~30 min investigating "stuck" IKN parser that was actually parsing 1,027 PDFs normally — its 8 AM run completed cleanly at 10:39 AM and auto-pushed to Cloudflare while I was diagnosing.
