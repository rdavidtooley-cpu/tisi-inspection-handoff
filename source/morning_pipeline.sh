#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Inspection Intel — Morning Pipeline
# ═══════════════════════════════════════════════════════════════
#  Replaces Claude scheduled tasks with a single no-token run.
#  Runs sequentially: token refresh → transcripts → dashboard → deploy
#
#  Note: Peer comparison is already computed inside
#        refresh_inspection_dashboard.py (compute_peer_rankings),
#        so no separate step is needed.
#
#  Schedule: 5:00 AM daily via LaunchAgent
#  Logs:     Inspection_Intel/_scripts/logs/morning_pipeline_YYYY-MM-DD.log
# ═══════════════════════════════════════════════════════════════

set -uo pipefail

# ── Paths ─────────────────────────────────────────────────────
# This script lives at Inspection_Intel/morning_pipeline.sh.
# SCRIPT_DIR == PROJECT_DIR == Inspection_Intel/
# The Python scripts it calls live in $PROJECT_DIR/_scripts/.
# Shared scripts (M&A pipeline) live at $PROJECT_DIR/../_shared/.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
DASHBOARD_DIR="$PROJECT_DIR/Dashboard"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/morning_pipeline_$(date +%Y-%m-%d).log"
PYTHON="/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
GIT_SSH_KEY="$HOME/.ssh/id_ed25519"
NOTIFY="${PROJECT_ROOT}/_shared/pipeline_notify.py"

# ── Setup ─────────────────────────────────────────────────────
mkdir -p "$LOG_DIR"
# ── Clear Python bytecode cache (per CLAUDE.md) ──────────────
find "$(cd "$(dirname "$0")" && pwd)" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
exec > >(tee -a "$LOG_FILE") 2>&1

FAILURES=0

run_step() {
    local step_name="$1"
    local step_dir="$2"
    shift 2
    echo ""
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│  $step_name"
    echo "│  $(date '+%H:%M:%S')"
    echo "└─────────────────────────────────────────────────────────────┘"
    cd "$step_dir"
    if "$@"; then
        echo "  ✓ $step_name completed"
    else
        echo "  ✗ $step_name FAILED (exit $?)"
        FAILURES=$((FAILURES + 1))
    fi
}

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Inspection Intel — Morning Pipeline"
echo "  $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "═══════════════════════════════════════════════════════════════"

# ── Step 1: Refresh Koyfin Token ─────────────────────────────
run_step "Koyfin token refresh" "$SCRIPT_DIR/_scripts" \
    $PYTHON koyfin_refresh_token.py

# ── Step 2: Download Transcripts (last 30 days) ─────────────
run_step "Download transcripts (last 30 days)" "$SCRIPT_DIR/_scripts" \
    $PYTHON koyfin_transcripts.py --recent 30

# ── Step 3: Refresh Dashboard (includes peer rankings) ───────
run_step "Refresh dashboard + peer rankings" "$SCRIPT_DIR/_scripts" \
    $PYTHON refresh_inspection_dashboard.py

# ── Step 4: Daily Alerts ─────────────────────────────────────
run_step "Daily alerts (big movers, 8-Ks, earnings)" "$SCRIPT_DIR/_scripts" \
    $PYTHON check_alerts.py

# ── Step 5: M&A Data Refresh ─────────────────────────────────
echo ""
echo "┌─────────────────────────────────────────────────────────────┐"
echo "│  [M&A] Fetching 8-K filings..."
echo "│  $(date '+%H:%M:%S')"
echo "└─────────────────────────────────────────────────────────────┘"
cd "$PROJECT_DIR/.."
$PYTHON "$PROJECT_DIR/../_shared/fetch_ma_edgar.py" Inspection_Intel || FAILURES=$((FAILURES + 1))

echo ""
echo "┌─────────────────────────────────────────────────────────────┐"
echo "│  [M&A] RSS wire feed (Google News — free, daily)..."
echo "│  $(date '+%H:%M:%S')"
echo "└─────────────────────────────────────────────────────────────┘"
$PYTHON "$PROJECT_DIR/../_shared/fetch_ma_rss.py" Inspection_Intel || true

echo ""
echo "┌─────────────────────────────────────────────────────────────┐"
echo "│  [M&A] Merging deals..."
echo "└─────────────────────────────────────────────────────────────┘"
$PYTHON "$PROJECT_DIR/../_shared/ma_core.py" Inspection_Intel/Dashboard || FAILURES=$((FAILURES + 1))

echo ""
echo "┌─────────────────────────────────────────────────────────────┐"
echo "│  [M&A] Rebuilding M&A Dashboard..."
echo "└─────────────────────────────────────────────────────────────┘"
$PYTHON "$PROJECT_DIR/../_shared/build_ma_pages.py" || FAILURES=$((FAILURES + 1))

# ── Step 6: Git Commit & Deploy ──────────────────────────────
echo ""
echo "┌─────────────────────────────────────────────────────────────┐"
echo "│  Deploy to Cloudflare Pages"
echo "│  $(date '+%H:%M:%S')"
echo "└─────────────────────────────────────────────────────────────┘"
cd "$DASHBOARD_DIR"

if git diff --quiet && git diff --cached --quiet; then
    echo "  No changes to deploy."
else
    DATE_STAMP=$(date +%Y-%m-%d)
    git add -A
    git commit -m "Morning pipeline: $DATE_STAMP"
    GIT_SSH_COMMAND="ssh -i $GIT_SSH_KEY" git push origin main
    echo "  ✓ Deployed successfully"
fi

# ── Summary ───────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
if [ $FAILURES -eq 0 ]; then
    echo "  Morning pipeline complete: $(date '+%H:%M:%S') — all steps succeeded"
else
    echo "  Morning pipeline complete: $(date '+%H:%M:%S') — $FAILURES step(s) failed"
fi
echo "═══════════════════════════════════════════════════════════════"
echo ""
# ── Alert on Failure ──────────────────────────────────────────
if [ $FAILURES -gt 0 ]; then
    $PYTHON "$NOTIFY" "Inspection Intel" "$LOG_FILE"
fi
