#!/usr/bin/env python3
"""
Automated Transcript Summarizer
================================
Scans Companies for earnings call transcripts, compares against
transcript_summaries.json, and uses Claude Code CLI to generate summaries
for any new/missing transcripts. No API key needed — uses your existing
Claude subscription via the Claude Code CLI.

Usage:
    # Summarize only new (unsummarized) transcripts
    python3 _scripts/summarize_transcripts.py

    # Watch mode — continuously monitor for new transcripts
    python3 _scripts/summarize_transcripts.py --watch

    # Force re-summarize all transcripts
    python3 _scripts/summarize_transcripts.py --force

    # Summarize a specific ticker only
    python3 _scripts/summarize_transcripts.py --ticker TISI

    # Dry run — show what would be summarized
    python3 _scripts/summarize_transcripts.py --dry-run

    # Also run the dashboard refresh after summarizing
    python3 _scripts/summarize_transcripts.py --refresh

Run from Terminal (not from inside Claude Code).
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

# ── Paths ───────────────────────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).resolve().parent.parent
RESEARCH_DIR = PROJECT_DIR / 'Companies'
SUMMARIES_FILE = RESEARCH_DIR / 'transcript_summaries.json'
SCRIPTS_DIR = Path(__file__).resolve().parent
REFRESH_SCRIPT = SCRIPTS_DIR / 'refresh_inspection_dashboard.py'

# ── Find Claude Code CLI ────────────────────────────────────────────────────
def find_claude_cli():
    """Find the Claude Code CLI binary, checking versioned install paths."""
    # Check PATH first
    for name in ['claude']:
        result = subprocess.run(['which', name], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()

    # Check user-local Node.js install (npm global)
    import glob as _glob
    for node_dir in sorted(_glob.glob(str(Path.home() / '.local' / 'node-*' / 'bin' / 'claude')), reverse=True):
        if Path(node_dir).exists():
            return node_dir

    # Check the macOS Application Support install location
    base = Path.home() / 'Library' / 'Application Support' / 'Claude' / 'claude-code'
    if base.exists():
        # Get the latest version directory
        versions = sorted(base.iterdir(), reverse=True)
        for v in versions:
            cli = v / 'claude'
            if cli.exists():
                return str(cli)

    return None


CLAUDE_CLI = find_claude_cli()

# ── Config ──────────────────────────────────────────────────────────────────
WATCH_INTERVAL = 30  # seconds between scans in watch mode
DELAY_BETWEEN_SUMMARIES = 5  # seconds between CLI calls (paced to avoid usage limits)

SUMMARY_PROMPT = """You are a senior financial reporter at Bloomberg writing an executive briefing for a CEO. Summarize this earnings call transcript in five parts: bullet-point highlights, narrative summary, Q&A takeaways, quarter-over-quarter comparison, and key risks.

Format your response EXACTLY like this (use **bold** markers for section headers):

**KEY HIGHLIGHTS**
- [Most important takeaway — lead with the headline number: revenue, earnings beat/miss, or guidance change]
- [Second most important: margin expansion/contraction, EBITDA, or free cash flow highlight]
- [Notable strategic move: M&A, restructuring, new contract win, or market expansion]
- [Forward guidance: raised/lowered/maintained, with specific targets if given]
- [Any additional critical item: management change, balance sheet move, risk factor, or catalyst]

**SUMMARY**
[3-5 paragraph narrative summary covering: (1) Top-line performance — revenue, growth rates by segment/geography, and what drove the results. (2) Profitability — gross margin, operating margin, EBITDA, EPS, and free cash flow with specific numbers. (3) Strategic and operational updates — backlog, customer wins, M&A activity, technology investments, end-market trends. (4) Management outlook and guidance — what management expects going forward, specific targets, and key risks or catalysts they flagged. Write in third person (e.g., "The company reported..." or "Management raised guidance..."). Be specific with dollar amounts, percentages, and basis points throughout.]

**Q&A TAKEAWAYS**
- [Key analyst question #1 and management's response — focus on what was NEW or surprising vs. prepared remarks]
- [Key analyst question #2 and management's response — include specific numbers or commitments made]
- [Key analyst question #3 and management's response — note any pushback, hedging, or color not in prepared remarks]
[If no Q&A section exists in the transcript, write: "No Q&A session included in this transcript."]

**QoQ COMPARISON**
- [How did revenue/growth this quarter compare to last quarter? Accelerating, decelerating, or stable?]
- [Any notable changes in margin trajectory, guidance, or strategic direction vs. prior quarter?]
- [Management tone shift: more bullish, cautious, or consistent vs. last quarter's commentary?]
[Base this ONLY on what management explicitly references about prior quarter trends within this transcript. Do not fabricate comparisons.]

**KEY RISKS**
- [Risk #1: Most material risk flagged by management or evident from results — be specific]
- [Risk #2: Secondary risk — competitive, regulatory, macro, balance sheet, or execution risk]
[If management flagged no specific risks, note the most obvious risk implied by the results or industry context.]

IMPORTANT:
- Lead every bullet with a specific number ($, %, bps) — never vague language
- The narrative SUMMARY should be 300-500 words, written as a professional financial brief
- Include direct context: "vs. prior year", "vs. consensus", "sequential improvement"
- Q&A TAKEAWAYS should capture what analysts pressed on and any new info not in prepared remarks
- QoQ COMPARISON should only reference data from this transcript — do not invent prior quarter numbers
- KEY RISKS should be 1-2 bullets, concise and actionable — not generic boilerplate
- Do NOT include any preamble, greeting, or closing — just the five sections"""


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S',
    )
    return logging.getLogger('summarizer')


def load_existing_summaries():
    """Load existing summaries from JSON file."""
    if SUMMARIES_FILE.exists():
        with open(SUMMARIES_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_summaries(summaries):
    """Save summaries to JSON file."""
    with open(SUMMARIES_FILE, 'w') as f:
        json.dump(summaries, f, indent=2, ensure_ascii=False)


def find_all_transcripts():
    """Find all transcript .txt files and return list of (key, path) tuples."""
    results = []
    txt_files = sorted(RESEARCH_DIR.glob('**/Transcripts/*_Earnings_Call.txt'))

    for fpath in txt_files:
        fname = fpath.stem  # e.g. MG_Q3_2025_Earnings_Call
        parts = fname.split('_')
        if len(parts) < 4:
            continue

        ticker = parts[0]
        quarter = parts[1]
        year = parts[2]
        key = f'{ticker}_{quarter}_{year}'
        results.append((key, fpath))

    return results


def summarize_transcript(transcript_path, logger):
    """Call Claude Code CLI to summarize a single transcript."""
    with open(transcript_path, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()

    # Truncate if too long (keep under ~100K chars for CLI)
    if len(text) > 100_000:
        text = text[:100_000] + '\n\n[Transcript truncated]'

    full_prompt = f'{SUMMARY_PROMPT}\n\n---\n\nTRANSCRIPT:\n\n{text}'

    # Build clean environment — strip nesting guard vars but keep auth
    env = os.environ.copy()
    # These vars trigger the "cannot launch inside another session" guard
    for key in ['CLAUDECODE', 'CLAUDE_CODE_ENTRYPOINT', 'CLAUDE_CODE_ENABLE_ASK_USER_QUESTION_TOOL',
                'CLAUDE_CODE_EMIT_TOOL_USE_SUMMARIES', 'CLAUDE_CODE_DISABLE_CRON',
                'CLAUDE_AGENT_SDK_VERSION']:
        env.pop(key, None)

    result = subprocess.run(
        [CLAUDE_CLI, '-p', full_prompt, '--output-format', 'text'],
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )

    if result.returncode != 0:
        raise RuntimeError(f'Claude CLI error (exit {result.returncode}): {result.stderr.strip()}')

    summary = result.stdout.strip()
    if not summary:
        raise RuntimeError('Claude CLI returned empty response')

    return summary


def run_refresh(logger):
    """Run the dashboard refresh script."""
    logger.info('Running dashboard refresh...')
    result = subprocess.run(
        [sys.executable, str(REFRESH_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode == 0:
        logger.info('Dashboard refresh complete.')
    else:
        logger.error(f'Refresh failed: {result.stderr[-500:] if result.stderr else "unknown error"}')


def summarize_new(existing, all_transcripts, force, logger):
    """Summarize transcripts that don't have summaries yet. Returns count of new summaries."""
    if force:
        # Skip transcripts already in the new CEO brief format
        to_summarize = []
        skipped = 0
        for k, p in all_transcripts:
            if k in existing and '**KEY RISKS**' in existing[k].get('summary', ''):
                skipped += 1
            else:
                to_summarize.append((k, p))
        if skipped:
            logger.info(f'Skipping {skipped} transcripts already in new format')
    else:
        to_summarize = [(k, p) for k, p in all_transcripts if k not in existing]

    if not to_summarize:
        return 0

    logger.info(f'{len(to_summarize)} transcripts need summarization')
    success_count = 0

    for i, (key, path) in enumerate(to_summarize):
        logger.info(f'[{i + 1}/{len(to_summarize)}] Summarizing {key}...')

        try:
            summary = summarize_transcript(path, logger)
            existing[key] = {'summary': summary}
            success_count += 1
            logger.info(f'  Done ({len(summary)} chars)')

            # Save after each successful summary
            save_summaries(existing)

            # Delay between calls
            if i < len(to_summarize) - 1:
                time.sleep(DELAY_BETWEEN_SUMMARIES)

        except subprocess.TimeoutExpired:
            logger.error(f'  Timeout for {key} — skipping')
        except Exception as e:
            logger.error(f'  Error for {key}: {e}')

    return success_count


def main():
    parser = argparse.ArgumentParser(description='Summarize earnings call transcripts using Claude Code CLI')
    parser.add_argument('--force', action='store_true', help='Re-summarize all transcripts')
    parser.add_argument('--ticker', type=str, help='Only summarize transcripts for a specific ticker')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be summarized')
    parser.add_argument('--watch', action='store_true', help='Continuously watch for new transcripts')
    parser.add_argument('--refresh', action='store_true', help='Run dashboard refresh after summarizing')
    args = parser.parse_args()

    logger = setup_logging()

    # Verify Claude CLI exists
    if not CLAUDE_CLI:
        logger.error('Claude Code CLI not found. Install Claude Code or add it to your PATH.')
        logger.error('Expected location: ~/Library/Application Support/Claude/claude-code/*/claude')
        sys.exit(1)
    logger.info(f'Using Claude CLI: {CLAUDE_CLI}')

    if args.watch:
        logger.info(f'Watch mode — scanning every {WATCH_INTERVAL}s for new transcripts (Ctrl+C to stop)')
        try:
            while True:
                existing = load_existing_summaries()
                all_transcripts = find_all_transcripts()

                if args.ticker:
                    all_transcripts = [(k, p) for k, p in all_transcripts if k.startswith(args.ticker + '_')]

                new_count = summarize_new(existing, all_transcripts, False, logger)

                if new_count > 0 and args.refresh:
                    run_refresh(logger)

                time.sleep(WATCH_INTERVAL)
        except KeyboardInterrupt:
            logger.info('Watch mode stopped.')
            return
    else:
        # One-shot mode
        existing = load_existing_summaries()
        logger.info(f'Loaded {len(existing)} existing summaries')

        all_transcripts = find_all_transcripts()
        logger.info(f'Found {len(all_transcripts)} transcript files')

        if args.ticker:
            all_transcripts = [(k, p) for k, p in all_transcripts if k.startswith(args.ticker + '_')]
            logger.info(f'Filtered to {len(all_transcripts)} transcripts for ticker {args.ticker}')

        # Determine which need summarization
        if args.force:
            # Skip transcripts already in the new CEO brief format
            to_summarize = []
            skipped = 0
            for k, p in all_transcripts:
                if k in existing and '**KEY RISKS**' in existing[k].get('summary', ''):
                    skipped += 1
                else:
                    to_summarize.append((k, p))
            if skipped:
                logger.info(f'Skipping {skipped} transcripts already in new format')
        else:
            to_summarize = [(k, p) for k, p in all_transcripts if k not in existing]

        if not to_summarize:
            logger.info('All transcripts already have summaries. Nothing to do.')
            return

        logger.info(f'{len(to_summarize)} transcripts need summarization:')
        for key, path in to_summarize:
            logger.info(f'  - {key}')

        if args.dry_run:
            logger.info('DRY RUN — no calls made.')
            return

        new_count = summarize_new(existing, all_transcripts, args.force, logger)
        logger.info(f'Done! {new_count} new summaries. {len(existing)} total.')

        if new_count > 0 and args.refresh:
            run_refresh(logger)


if __name__ == '__main__':
    main()
