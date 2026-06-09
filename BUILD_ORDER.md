# Build Order — 10 Steps to a Live Site

Follow these in order. Each step has a verify-before-proceed check. Do not skip ahead.

---

## Step 1 — Prerequisites

Check the host machine has:

```bash
python3 --version        # ≥ 3.10
node --version            # ≥ 18
npx wrangler --version    # any recent
git --version
```

Install if missing. Confirm the user has:

- A Cloudflare account (free tier is fine)
- A GitHub account with SSH key (`ssh-add -l` should list one)
- Chrome (needed for the Koyfin token extraction step)

**Verify:** all four CLI commands return a version.

---

## Step 2 — Lay down the project

Pick a project root, e.g. `~/code/tisi-intel/`. Then:

```bash
mkdir -p ~/code/tisi-intel
cp -R Export/TISI_Inspection_Handoff/source/. ~/code/tisi-intel/
cd ~/code/tisi-intel
```

The folder now looks like:

```
~/code/tisi-intel/
├── _scripts/             (Python pipeline)
├── _shared/              (helpers)
├── Dashboard/            (HTML + auth + functions)
├── morning_pipeline.sh
└── wrangler.toml.template
```

**Verify:** `ls _scripts | wc -l` ≥ 20 entries.

---

## Step 3 — Fill placeholders

Open `REDACTION_NOTES.md` and walk through each placeholder. For each one:

1. Get the real value from the user
2. Find every file containing it: `grep -rln '__PLACEHOLDER_NAME__' ~/code/tisi-intel`
3. Replace with the real value

Use `sed -i ''` on macOS or `sed -i` on Linux:

```bash
find . -type f \( -name "*.py" -o -name "*.sh" -o -name "*.html" -o -name "*.js" -o -name "*.toml" \) \
  -exec sed -i '' 's|__PAGES_PROJECT_NAME__|tisi-intel|g' {} +
```

Rename `wrangler.toml.template` → `wrangler.toml` after editing.

**Verify:** `grep -rn '__SET_\|__PAGES_PROJECT_\|__ADMIN_EMAIL__\|__FROM_EMAIL__\|__PROJECT_DOMAIN__\|__CLOUDFLARE_ACCOUNT_ID__\|__KV_NAMESPACE_ID__\|__GITHUB_ORG__\|__GITHUB_REPO__' .` returns nothing.

---

## Step 4 — Choose and install auth

Read `06_AUTH_OPTIONS.md`. Pick one:

- **Option A** — Standalone single password (simpler, 5 min)
- **Option B** — Per-site user accounts (more setup, supports admin approval)

Replace `Dashboard/auth.js` accordingly. The receiving Claude implements the chosen variant from the templates in `06_AUTH_OPTIONS.md`.

**Verify:** open `Dashboard/index.html` locally in a browser; the password gate should appear and accept the new password.

---

## Step 5 — Obtain a Koyfin session token

Koyfin doesn't have a public API. Token extraction is a manual one-time setup. Run:

```bash
cd ~/code/tisi-intel/_scripts
python3 koyfin_login_reminder.py
```

This prints instructions for logging into Koyfin in Chrome, then running `koyfin_refresh_token.py` to extract the session from Chrome's encrypted cookie database into `koyfin_token.json`.

**Verify:** `cat _scripts/koyfin_token.json` shows real `access_token` and `refresh_token` (not placeholders).

---

## Step 6 — First local pipeline run

```bash
cd ~/code/tisi-intel
export PROJECT_ROOT="$(pwd)"
bash morning_pipeline.sh 2>&1 | tee logs/first_run.log
```

Expected runtime: 15–25 minutes on first run (downloads all transcripts, builds 5-year price history).

Watch for:

- 22/22 tickers fetched
- Transcripts downloaded for at least 15 tickers (LSE semi-annual names cap at 3)
- `Dashboard/market_data.json`, `price_history.json`, `ma_deals.json` updated
- All 6 `*_Dashboard.html` files regenerated

**Verify:** `python3 -c "import json; print(len(json.load(open('Dashboard/market_data.json'))))"` returns 22.

---

## Step 7 — Open dashboards locally

```bash
cd Dashboard
python3 -m http.server 8000
```

Open `http://localhost:8000/index.html`. Walk all 6 tabs:

- Command Center (index.html)
- Equities Dashboard
- Company Summary
- Peer Analysis
- Industry Dashboard
- News Dashboard
- Earnings Dashboard
- M&A Dashboard

Confirm: tickers populate, charts render, no JS console errors.

**Verify:** every tab loads with non-empty data and no red errors in DevTools console.

---

## Step 8 — Create GitHub repo + first push

User creates a private repo `<org>/<repo>` on GitHub. Then:

```bash
cd ~/code/tisi-intel/Dashboard
git init -b main
git remote add origin git@github.com:<org>/<repo>.git
git add .
git commit -m "Initial deploy"
git push -u origin main
```

Add `CLOUDFLARE_API_TOKEN` to the GitHub repo: Settings → Secrets and variables → Actions → New repository secret.

Add `.github/workflows/deploy.yml` from the template in `05_DEPLOYMENT.md`. Commit and push.

**Verify:** the GitHub Actions tab shows a green deploy workflow run.

---

## Step 9 — First Cloudflare Pages deploy

If the GitHub Action succeeded, you're done. To deploy manually instead:

```bash
cd ~/code/tisi-intel/Dashboard
export CLOUDFLARE_API_TOKEN="<user's token>"
export CLOUDFLARE_ACCOUNT_ID="<user's account id>"
npx wrangler pages deploy . --project-name <project-name> --commit-dirty=true
```

**Verify:** `curl -I https://<project-name>.pages.dev` returns HTTP 200.

Open the live URL in a browser, log in with the password, walk all 6 dashboards. They should match what worked locally in Step 7.

---

## Step 10 — Schedule the daily refresh (optional)

If the user wants automated daily refreshes:

```bash
# macOS LaunchAgent — see 08_LAUNCHAGENT_SETUP.md for full plist
cp _shared/launchagent_template.plist ~/Library/LaunchAgents/com.tisi.intel.daily.plist
# edit the plist to set the correct project path
launchctl load ~/Library/LaunchAgents/com.tisi.intel.daily.plist
```

For email digest: see `07_EMAIL_DIGEST.md` — adds `RESEND_API_KEY` to Cloudflare Pages env vars and wires up the `/api/subscribe` endpoint.

**Verify:** `launchctl list | grep tisi` returns the agent loaded with PID `-` (idle, will fire at scheduled time).

---

## Done

You have a live, password-protected, daily-refreshing TIC/NDT sector intelligence dashboard at `https://<project-name>.pages.dev`.

If anything fails: check `09_KNOWN_GOTCHAS.md` first — most issues encountered during the original build are documented there with the fix.
