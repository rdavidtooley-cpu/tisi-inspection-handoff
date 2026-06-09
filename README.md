# TISI Inspection Intel — Handoff Package

This package contains everything another Claude (on another machine, for another company) needs to recreate the **Inspection Intel** platform — a TIC/NDT (Testing, Inspection, Certification / Non-Destructive Testing) sector intelligence dashboard. It tracks 22 public companies across 5 industry categories, refreshes daily, and serves a password-protected web dashboard.

The originating site is in production at a dedicated Cloudflare Pages project. This handoff strips all account-specific values (passwords, tokens, account IDs, emails, custom domains) and replaces them with placeholders the receiver fills in.

---

## If you are the receiving Claude, read this first

### Step 1 — Drop the memory files into your auto-memory system

Copy the contents of `memory/` into your project's memory directory:

```
~/.claude/projects/<your-project-slug>/memory/
```

The MEMORY.md inside is the index; the rest are individual memory files referenced from it. They give you the architectural mental model, the universal engineering lessons learned, and the operational gotchas — without these you will repeat mistakes that have already been solved.

### Step 2 — Drop CLAUDE.md into your new project root

`CLAUDE.md` is the project-level briefing file. Place it at the root of the new repo. It tells future Claude sessions what this project is, the critical rules, and what not to break.

### Step 3 — Read in this order

1. `01_ARCHITECTURE.md` — what you're building, how it fits together
2. `02_TICKER_UNIVERSE.md` — the 22 companies and 5 categories
3. `BUILD_ORDER.md` — the 10-step sequence to stand up the new site
4. `REDACTION_NOTES.md` — every placeholder string and what to replace it with
5. `06_AUTH_OPTIONS.md` — decide auth model BEFORE you deploy

### Step 4 — Before you write any code, confirm the user provides

The user must supply these eight items. Do not start the build until you have them:

1. **Cloudflare account ID** (32-char hex from Cloudflare dashboard → right sidebar)
2. **Cloudflare API token** with `Account → Pages → Edit` permission
3. **GitHub repo** (org/name) created and SSH key set up on the local machine
4. **Site password** the user wants for the password gate (will be SHA-256 hashed)
5. **FROM email** for the daily digest (must be on a domain verified in Resend)
6. **Admin email** for failure notifications and the subscriber inbox
7. **Resend API key** (`https://resend.com/api-keys`)
8. **Koyfin session token** (manual extraction — see `_scripts/koyfin_login_reminder.py`)

Plus optional: a custom domain (`<sub>.<your-domain>`) and a chosen Pages project name (e.g. `tisi-intel`).

---

### Step 4.5 — IMPORTANT: read this if Robert is the user

Robert (the original Inspection Intel operator) has explicitly opted out of two of the credentials above:

- **No Anthropic API key.** He doesn't want to use the Claude API for transcript summarization.
- **Koyfin session is uncertain.** He may use something simpler than Koyfin for transcripts.

**Don't redesign your build to summarize transcripts yourself.** Robert's existing Mac mini (`Roberts-Mac-mini.local`) already runs the full Inspection Intel morning pipeline — it downloads transcripts via Koyfin, summarizes via Claude CLI (5-section format), and **publishes the results to a public feed repo daily** at:

> **https://github.com/rdavidtooley-cpu/inspection-summaries-feed**

That feed is **public** (no auth needed) and updated every morning at ~5:10 AM Central. It contains:

- `transcript_summaries.json` — every summary keyed by `<TICKER>_Q<n>_<YYYY>`
- `transcripts/*.html` — rendered per-transcript HTML files

#### How to consume the feed from the TISI Node.js build

**Pattern A — Fetch the JSON at runtime (recommended):**

```javascript
// Once per day (e.g. at site startup or on a 6 AM CT timer)
const url = 'https://raw.githubusercontent.com/rdavidtooley-cpu/inspection-summaries-feed/main/transcript_summaries.json';
const res = await fetch(url);
const summaries = await res.json();
// summaries["MG_Q3_2026"] = { ticker, quarter, year, title, sections: [...], company, date, source_url }
```

**Pattern B — Clone + pull on a schedule:**

```bash
# On the Windows server
cd C:\sites\
git clone https://github.com/rdavidtooley-cpu/inspection-summaries-feed.git
# Then daily:
cd inspection-summaries-feed && git pull
```

Read `transcript_summaries.json` and `transcripts/*.html` from disk.

#### What this means for your build

- **Skip the Koyfin + Anthropic transcript pipeline entirely.** You're a consumer of the feed, not a producer.
- **Skip credentials #8 (Koyfin session token).** Not needed.
- **You do NOT need an Anthropic API key.**
- **Your dashboard's "Earnings Transcripts" view** reads from the feed JSON instead of running summarization locally.
- **Stale-data check:** if the feed's last-modified date on GitHub is older than 24h, alert Robert — his morning pipeline probably failed.

#### What the feed does NOT cover

Only transcript summaries — not prices, news, M&A, or any other Inspection data. For everything else, you still run your own pipeline (Yahoo Finance, SEC EDGAR, FRED — all free, no key needed).

If Robert ever turns off the feed or his Mac mini goes dark, fall back to either (a) running Claude CLI on the Windows server if installed, or (b) displaying a "summaries temporarily unavailable" notice. Plan for graceful degradation, not for the feed being permanent infrastructure.

---

## What's in the box

```
README.md                this file — start here
CLAUDE.md                drop into new project root
BUILD_ORDER.md           10-step build sequence
REDACTION_NOTES.md       placeholder → real value mapping

01_ARCHITECTURE.md       system overview, data flow
02_TICKER_UNIVERSE.md    22 tickers, 5 categories, two named indices
03_PIPELINE_SCRIPTS.md   what each Python script does
04_DASHBOARD_PAGES.md    6 dashboards, template system, layout rules
05_DEPLOYMENT.md         Cloudflare Pages + GitHub Actions
06_AUTH_OPTIONS.md       standalone single-password vs full user system
07_EMAIL_DIGEST.md       Resend setup + subscribe APIs
08_LAUNCHAGENT_SETUP.md  macOS daily refresh automation
09_KNOWN_GOTCHAS.md      universal lessons from the original build

memory/                  drop-in for ~/.claude/projects/.../memory/
source/                  full working code — scripts, templates, Pages functions
```

The `source/` tree is a working snapshot of the production codebase with every Robert-specific value already replaced by a `__PLACEHOLDER__` token. `REDACTION_NOTES.md` lists every placeholder and what value to drop in.

---

## What this site does (one paragraph)

Daily at ~5am ET, a macOS LaunchAgent runs `morning_pipeline.sh`. That script pulls fresh market data (yfinance), earnings transcripts (Koyfin), SEC filings (EDGAR), OSHA inspection data, M&A announcements (Google News RSS + 8-K filings), and news headlines. It writes JSON data files, then a master Python script (`refresh_inspection_dashboard.py`) injects that data into 6 HTML templates to produce 6 static dashboards. The output is git-committed and auto-deployed to Cloudflare Pages. Users hit the site, see a password gate, and get a real-time view of 22 companies across the TIC/NDT industry.

The whole thing runs on free-tier Cloudflare Pages, costs ~$0/month to host, and is single-machine + single-cron-job to operate.
