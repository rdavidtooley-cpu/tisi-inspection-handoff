#!/bin/bash
# ─────────────────────────────────────────────────────────────────────
# Transcript Auto-Summarizer Wrapper
# ─────────────────────────────────────────────────────────────────────
# Called by macOS Launch Agent when new files appear in Transcripts dirs.
# Runs the Python summarizer, then refreshes the dashboard and pushes.
#
# Logs: ~/Inspection_Intel/_scripts/logs/summarizer.log
# ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/summarizer.log"

mkdir -p "$LOG_DIR"

# Timestamp
echo "" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"
echo "$(date '+%Y-%m-%d %H:%M:%S') — Triggered" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# Wait a moment for file writes to finish
sleep 3

# Unset CLAUDECODE to avoid nesting guard
unset CLAUDECODE

# Run summarizer (only processes new/missing transcripts)
python3 "$SCRIPT_DIR/summarize_transcripts.py" >> "$LOG_FILE" 2>&1
SUMMARY_EXIT=$?

if [ $SUMMARY_EXIT -eq 0 ]; then
    echo "$(date '+%H:%M:%S') Summarizer finished successfully" >> "$LOG_FILE"
else
    echo "$(date '+%H:%M:%S') Summarizer exited with code $SUMMARY_EXIT" >> "$LOG_FILE"
    exit $SUMMARY_EXIT
fi

# Check if transcript_summaries.json was actually modified in the last 60 seconds
SUMMARIES_FILE="$PROJECT_DIR/Companies/transcript_summaries.json"
if [ -f "$SUMMARIES_FILE" ]; then
    MODIFIED=$(stat -f %m "$SUMMARIES_FILE")
    NOW=$(date +%s)
    DIFF=$((NOW - MODIFIED))

    if [ $DIFF -le 60 ]; then
        echo "$(date '+%H:%M:%S') New summaries detected — refreshing dashboard..." >> "$LOG_FILE"

        # Run refresh
        python3 "$SCRIPT_DIR/refresh_inspection_dashboard.py" >> "$LOG_FILE" 2>&1

        # Push to deploy
        cd "$PROJECT_DIR/Dashboard"
        git add -A >> "$LOG_FILE" 2>&1
        git commit -m "Auto-update: new transcript summaries

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>" >> "$LOG_FILE" 2>&1

        GIT_SSH_COMMAND="ssh -i $HOME/.ssh/id_ed25519 -o StrictHostKeyChecking=no" \
            git push origin main >> "$LOG_FILE" 2>&1

        echo "$(date '+%H:%M:%S') Dashboard refreshed and pushed." >> "$LOG_FILE"
    else
        echo "$(date '+%H:%M:%S') No new summaries — skipping refresh." >> "$LOG_FILE"
    fi
fi

echo "$(date '+%H:%M:%S') Done." >> "$LOG_FILE"
