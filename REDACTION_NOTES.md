# Redaction Notes

Every Robert/origin-account-specific value has been replaced by a `__PLACEHOLDER__` token. Walk through this table during Build Step 3 and replace each token with the receiver's real value.

## Placeholder reference

| Placeholder | What it represents | Where to find the value | Files affected |
|---|---|---|---|
| `__PAGES_PROJECT_NAME__` | Cloudflare Pages project name (lowercase, hyphens) | User picks, e.g. `tisi-intel` | wrangler.toml.template, all Dashboard HTMLs |
| `__PROJECT_DOMAIN__` | Custom domain for the site (optional) | User's domain in Cloudflare DNS | Dashboard HTMLs, auth.js, email templates |
| `__CLOUDFLARE_ACCOUNT_ID__` | 32-char hex account ID | Cloudflare dashboard → right sidebar | wrangler.toml, GitHub Actions yml |
| `__KV_NAMESPACE_ID__` | KV namespace ID for subscribers | Created via `npx wrangler kv:namespace create SUBSCRIBERS` | wrangler.toml.template |
| `__GITHUB_ORG__` / `__GITHUB_REPO__` | GitHub org and repo names | User-chosen | GitHub Actions yml, deploy docs |
| `__SET_YOUR_PASSWORD__` | Plaintext password (for reference only — never stored) | User-chosen, strong | Used to generate the hash below |
| `__SET_YOUR_PASSWORD_HASH__` | SHA-256 of the password (hex, lowercase, 64 chars) | `echo -n 'password' \| shasum -a 256` | Dashboard/auth.js |
| `__ADMIN_EMAIL__` | Admin notification recipient | User's email | check_alerts.py, pipeline_notify.py, edgar_news_injector.py |
| `__FROM_EMAIL__` | Sending address for email digest | Must be on a Resend-verified domain | check_alerts.py, subscribe API |
| `__SET_KOYFIN_ACCESS_TOKEN__` | Koyfin session access token | Extracted via koyfin_refresh_token.py | _scripts/koyfin_token.json |
| `__SET_KOYFIN_REFRESH_TOKEN__` | Koyfin refresh token | Same | _scripts/koyfin_token.json |
| `__PROJECT_NAME__` | Human-readable project name | e.g. "TISI Inspection Intel" | _shared/edgar_news_injector.py (User-Agent) |
| `${PROJECT_ROOT}` | Absolute path to project root | Set as env var: `export PROJECT_ROOT=$(pwd)` | morning_pipeline.sh, several scripts |
| `${HOME}` | Standard shell variable | Already set by shell, no action | Various |

## Quick-replace script

After collecting all values from the user, write them into a file `_setup_values.sh`:

```bash
#!/bin/bash
export PAGES_PROJECT_NAME="tisi-intel"
export PROJECT_DOMAIN="intel.tisi.com"
export CLOUDFLARE_ACCOUNT_ID="abc123..."
export KV_NAMESPACE_ID="def456..."
export GITHUB_ORG="your-org"
export GITHUB_REPO="tisi-intel"
export PASSWORD_HASH="$(echo -n 'YourPassword!' | shasum -a 256 | awk '{print $1}')"
export ADMIN_EMAIL="admin@tisi.com"
export FROM_EMAIL="intel@tisi.com"
export PROJECT_NAME="TISI Inspection Intel"
```

Then run a sed sweep:

```bash
source _setup_values.sh
cd ~/code/tisi-intel

find . -type f \( -name "*.py" -o -name "*.sh" -o -name "*.html" -o -name "*.js" -o -name "*.toml" -o -name "*.template" -o -name "*.yml" \) -print0 | \
xargs -0 sed -i '' \
  -e "s|__PAGES_PROJECT_NAME__|$PAGES_PROJECT_NAME|g" \
  -e "s|__PROJECT_DOMAIN__|$PROJECT_DOMAIN|g" \
  -e "s|__CLOUDFLARE_ACCOUNT_ID__|$CLOUDFLARE_ACCOUNT_ID|g" \
  -e "s|__KV_NAMESPACE_ID__|$KV_NAMESPACE_ID|g" \
  -e "s|__GITHUB_ORG__|$GITHUB_ORG|g" \
  -e "s|__GITHUB_REPO__|$GITHUB_REPO|g" \
  -e "s|__SET_YOUR_PASSWORD_HASH__|$PASSWORD_HASH|g" \
  -e "s|__ADMIN_EMAIL__|$ADMIN_EMAIL|g" \
  -e "s|__FROM_EMAIL__|$FROM_EMAIL|g" \
  -e "s|__PROJECT_NAME__|$PROJECT_NAME|g"
```

Finally rename: `mv wrangler.toml.template wrangler.toml`.

## Special note: cross-sector project name leakage in `_shared/`

The `_shared/` helpers (`insider_tracker.py`, `short_interest.py`, `edgar_news_injector.py`, `fix_info_tooltips.py`, `enrich_ma_multiples.py`, `add_period_selector.py`, `analyst_actions_helper.py`, `_scripts/analyze_transcripts.py`) were originally built to operate across multiple sector sites (Casino_Gaming_Intel, Oil_Gas_Intel, Metal_Mining_Intel). They contain hardcoded sector folder names.

**Two options:**

1. **Single-sector deployment (recommended for TISI):** Rename your project root folder to `Inspection_Intel` so the existing `Inspection_Intel` references match. Other sector names (Casino, Oil_Gas, Metal_Mining) in those scripts will simply skip non-existent folders — no breakage.

2. **Custom folder name:** Open each affected file, find the `SECTOR_PROJECTS` dict (or similar), and replace the cross-sector entries with a single entry for your folder name. About 12 files affected. Grep to find them:

   ```bash
   grep -rln "Casino_Gaming_Intel\|Oil_Gas_Intel\|Metal_Mining_Intel" _shared _scripts
   ```

## What was NOT redacted (legitimate content)

These strings look sensitive but are real public information that should stay:

- `Stellex Capital Management` in dashboard transcripts — TISI's PE investor, mentioned in real Q3 2025 earnings calls
- Public company tickers (FLS, ROR.L, MTRX, etc.) — these are the universe being tracked
- CIK numbers in `_scripts/edgar_company_registry.json` — public SEC identifiers
- `Inspection_Intel` as a project-folder reference — see special note above
