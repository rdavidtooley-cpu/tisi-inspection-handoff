# Memory Index — Inspection Intel (TISI deployment)

Drop the contents of this folder into `~/.claude/projects/<your-project-slug>/memory/` so future Claude sessions can recall the architecture, lessons, and gotchas without re-reading the full handoff docs.

## Project

- [project_inspection_intel.md](project_inspection_intel.md) — full project state: 22 tickers, 5 categories, 8 dashboards, indices, scripts, rules

## Feedback (engineering lessons — universal)

- [feedback_template_overwrite.md](feedback_template_overwrite.md) — Always patch *_template.html alongside the live *_Dashboard.html; morning refresh silently reverts hand edits
- [feedback_info_icons.md](feedback_info_icons.md) — Info icons must be adjacent to their element; tooltips use position:fixed + JS positioning, never absolute inside overflow containers
- [feedback_mutation_observer.md](feedback_mutation_observer.md) — MutationObservers that write to observed DOM must disconnect during writes — self-trigger loops freeze the browser
- [feedback_summarizer_subprocess_timeout.md](feedback_summarizer_subprocess_timeout.md) — Bulk transcript loads must run summarize_transcripts.py directly; embedded refresh subprocess caps at 600s and silently fails
- [feedback_ticker_name_columns.md](feedback_ticker_name_columns.md) — Two-column tables: Ticker = ticker only, Company = name only. "Name (TICKER)" only in single-column contexts
- [feedback_pipeline_failure_notification.md](feedback_pipeline_failure_notification.md) — Pipelines must `trap notify_failure EXIT` and email on non-zero exit; success-path emails miss silent fails
- [feedback_crlf_phantom_dirs.md](feedback_crlf_phantom_dirs.md) — .sh scripts with CRLF endings spawn phantom <CR> directories; check with `file script.sh`, fix with `tr -d '\r'`
- [feedback_adjusted_ebitda.md](feedback_adjusted_ebitda.md) — Always include Adjusted EBITDA alongside reported EBITDA in financial displays and extractions
- [feedback_financial_models.md](feedback_financial_models.md) — Q4 financials are derived (FY − Q1 − Q2 − Q3), never directly reported; enter FY from 10-K, formula for Q4
- [feedback_auth_visibility.md](feedback_auth_visibility.md) — auth.js must never set document.visibility:hidden during validate — causes Chrome renderer freeze
- [feedback_index_composition_sync.md](feedback_index_composition_sync.md) — Universe ticker changes must propagate to named indices in the same task
- [feedback_always_deploy.md](feedback_always_deploy.md) — Any Pages dashboard edit must be deployed in the same task; never leave changes local
- [feedback_unique_kv_per_site.md](feedback_unique_kv_per_site.md) — Every sector site needs its own KV namespace IDs in wrangler.toml; copy-paste scaffolding silently shares KVs
- [feedback_cloudflare_secrets.md](feedback_cloudflare_secrets.md) — Pages secrets drift from local .env; rotate per-project and never silently swallow third-party API failures

## Reference (operational patterns)

- [reference_yfinance_data.md](reference_yfinance_data.md) — yfinance provides earnings_dates, market data; deprecated attributes, NaN gotchas, macOS DNS safety
- [reference_fred_curl.md](reference_fred_curl.md) — FRED silently blocks custom curl User-Agents; use default UA (no -A flag)
- [reference_user_agent_rules.md](reference_user_agent_rules.md) — UA rules: Cloudflare APIs (Resend) require explicit UA; FRED requires default UA — opposite rules per endpoint
- [reference_financials_history_helper.md](reference_financials_history_helper.md) — _shared/financials_history.py expects dict keyed by ticker OR list of ticker strings — never list of dicts
- [reference_google_news_rss.md](reference_google_news_rss.md) — Google News RSS as free zero-token news aggregator; gotchas for publisher-suffix stripping and sector relevance filtering
- [reference_python_unbuffered.md](reference_python_unbuffered.md) — Python stdout is block-buffered when piped to a log file; use `python3 -u` or `PYTHONUNBUFFERED=1`
