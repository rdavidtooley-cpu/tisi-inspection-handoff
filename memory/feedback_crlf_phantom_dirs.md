---
name: CRLF in shell scripts spawns phantom <CR> directories
description: Shell scripts with Windows CRLF line endings silently create directories with trailing carriage returns when constructing filesystem paths from variables
type: feedback
originSessionId: c0f2442d-531d-440e-878a-a431b33db628
---
Any `.sh` script that constructs filesystem paths from variables (e.g. `mkdir -p $LOG_DIR/sub`, `cd $TARGET`) MUST be LF-terminated. CRLF line endings cause the trailing `\r` to be appended to the path, producing phantom directories like `_scripts<CR>/logs` that look identical to `_scripts/` in most `ls` output but are actually different filesystem entries.

**Why:** April 2026 — during Inspection_Intel folder cleanup, a "trailing space" `_scripts ` directory at the project root kept reappearing after every deletion. Investigation revealed it was `_scripts\r` (carriage return) being recreated by `_scripts/run_summarizer.sh` which had been saved with CRLF. The script's `mkdir` calls were silently spawning the phantom directory on every pipeline run.

**How to apply:**
- Detection: `file path/to/script.sh` — look for "CRLF line terminators" in the output. To find any phantom-CR dirs in a tree: `find . -maxdepth 3 -type d -name $'*\r*'`. To see the actual byte name of a suspicious directory: `ls -lab` (the `b` flag escapes non-printables).
- Fix: `tr -d '\r' < script.sh > /tmp/fixed && mv /tmp/fixed script.sh && chmod +x script.sh`.
- Add this check to the diagnostic playbook for any "why does this folder keep coming back" investigation. Especially relevant for Master Intelligence projects (Oil_Gas_Intel, Inspection_Intel, Casino_Gaming_Intel, Metal_Mining_Intel) where pipelines mix shell + Python and shell scripts may have been edited on Windows or via copy-paste.
