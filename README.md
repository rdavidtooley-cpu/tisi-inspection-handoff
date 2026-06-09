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
