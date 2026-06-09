---
name: Pipeline scripts must email on failure
description: LaunchAgent/cron pipeline shell scripts must trap EXIT and email on non-zero exit; success-path emails alone leave silent fails invisible
type: feedback
originSessionId: a7f21582-94bf-4fe1-bc5e-8011f2fddae9
---
Any LaunchAgent or cron-driven pipeline script (Oil & Gas, Inspection, Casino, Metal Mining, IKN, etc.) that can `exit N>0` MUST have a failure-notification trap. Success-only email at the end of the script is unreachable on failure.

**Why:** `ikn-archive/ikn_weekly_update.sh` failed silently on April 14 at Step 1 (Gmail auth). Script used `set -euo pipefail` + `if cmd; then ... else exit 1; fi`. Step 6 (success email) was never reached. User discovered the gap 14 days later by asking "is IKN updating?" — by then 4 IKN issues had stacked up unprocessed.

**How to apply:** Define a `notify_failure()` function that:
1. Captures `$?` as first action
2. Returns 0 if exit was clean
3. Calls `trap - EXIT` to prevent re-entry
4. Tails ~30-40 lines of the log file
5. POSTs to Resend with subject `[FAILED] {pipeline_name} (exit N)` and the tailed log in a `<pre>` block
6. Ends with `|| true` so notification failures don't loop

Register with `trap notify_failure EXIT`. Reference implementation lives in `ikn-archive/ikn_weekly_update.sh` (Resend via Python heredoc, RESEND_API_KEY pulled from project `.env`).

Audit and retrofit all existing pipeline scripts: `Oil_Gas_Intel/_scripts/nightly_refresh.sh`, `Casino_Gaming_Intel/_scripts/`, `Inspection_Intel/_scripts/`, `Metal_Mining_Intel/_scripts/nightly_refresh*.sh` — anywhere a LaunchAgent runs a multi-step pipeline.
