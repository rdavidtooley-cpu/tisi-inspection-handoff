# 05 — Deployment

## Target: Cloudflare Pages + GitHub Actions

The original site costs ~$0/month on the Cloudflare free tier. Static HTML + KV-backed Pages Functions for `/api/*` endpoints.

## Prereqs

- Cloudflare account (free)
- Cloudflare API token with `Account → Pages → Edit` permission
- (Optional) Cloudflare DNS token with `Zone → DNS → Edit` if using a custom subdomain
- GitHub account with SSH key on host machine
- Empty private GitHub repo created in the user's org

## Step 1 — `wrangler.toml`

The handoff ships `source/wrangler.toml.template`. Rename to `wrangler.toml` and fill in:

```toml
name = "__PAGES_PROJECT_NAME__"
pages_build_output_dir = "."

[[kv_namespaces]]
binding = "SUBSCRIBERS"
id = "__KV_NAMESPACE_ID__"
```

To create the KV namespace:

```bash
cd Dashboard
export CLOUDFLARE_API_TOKEN=...
export CLOUDFLARE_ACCOUNT_ID=...
npx wrangler kv:namespace create SUBSCRIBERS
# copy the returned ID into wrangler.toml
```

**Critical:** each project needs its own KV namespace ID. If you reuse an ID from another project, subscribers leak across sites.

## Step 2 — GitHub Actions workflow

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Cloudflare Pages

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      deployments: write
    steps:
      - uses: actions/checkout@v4

      - name: Create Pages project if needed
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: __CLOUDFLARE_ACCOUNT_ID__
          command: pages project create __PAGES_PROJECT_NAME__ --production-branch=main
        continue-on-error: true

      - name: Deploy to Cloudflare Pages
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: __CLOUDFLARE_ACCOUNT_ID__
          command: pages deploy . --project-name=__PAGES_PROJECT_NAME__ --commit-dirty=true
```

Replace placeholders. Add the API token as a GitHub repo secret named `CLOUDFLARE_API_TOKEN`.

## Step 3 — Initial push

```bash
cd Dashboard
git init -b main
git remote add origin git@github.com:<org>/<repo>.git
git add .
git commit -m "Initial deploy"
git push -u origin main
```

The Actions tab on GitHub will show the deploy run within ~30 seconds.

## Step 4 — Verify

```bash
curl -I https://<pages-project>.pages.dev
# expect: HTTP/2 200
```

Open the URL in a browser. The password gate should appear.

## Manual deploy (when not using GitHub Actions)

From any machine with the API token:

```bash
cd Dashboard
export CLOUDFLARE_API_TOKEN="..."
export CLOUDFLARE_ACCOUNT_ID="..."
npx wrangler pages deploy . --project-name <project-name> --commit-dirty=true
```

This is what the daily LaunchAgent does after the pipeline finishes — it commits the new HTML files to git, pushes, and the Action handles the deploy. The manual path is for ad-hoc redeploys.

## Pages Functions (`/api/*`)

The handoff includes `Dashboard/functions/` with these endpoints:

- `/api/subscribe` — email subscription opt-in (writes to SUBSCRIBERS KV)
- `/api/unsubscribe` — opt-out (removes from KV)
- `/api/subscribers` — admin-only list (KV read)
- `/api/quotes` — current market data (reads market_data.json, returns JSON)

These are Cloudflare Workers runtime — TypeScript-flavored JS with Workers types. They run automatically when deployed alongside the static HTML.

Environment variables for the Functions (set in Cloudflare dashboard → Pages project → Settings → Environment variables):

- `RESEND_API_KEY` — for email digest
- `FROM_EMAIL` — must be on a Resend-verified domain
- `ADMIN_EMAIL` — for failure notifications

## Custom domain (optional)

If the user has a domain in Cloudflare:

```bash
npx wrangler pages domains add <subdomain.example.com> --project-name <project-name>
```

Then in the Cloudflare DNS dashboard, add a CNAME from `<subdomain>` to `<project-name>.pages.dev` (proxied). Wait ~3 minutes for SSL provisioning.

If your origin platform has a custom-domain patcher (the original repo has one for Robert's setup), adapt or skip — the manual flow above is sufficient for a single site.

## `_headers` file

`Dashboard/_headers` adds HTTP headers globally. The shipped version sets:

- `Cache-Control: public, max-age=300` on JSON
- `X-Frame-Options: DENY`
- `Content-Security-Policy: default-src 'self' 'unsafe-inline' https:`

Adjust CSP if you embed third-party widgets (Chart.js is loaded from CDN by default — already allowed by `https:`).

## Rolling back a deploy

Cloudflare Pages keeps deploy history. To roll back:

1. Open Cloudflare dashboard → Pages → your project
2. Click the "Deployments" tab
3. Find the prior good deploy
4. Click the `⋯` menu → "Rollback to this deployment"

Or via git: revert the bad commit, push, the Action redeploys.

## Cost

- Pages: free (up to 500 builds/month, unlimited bandwidth)
- KV: free (up to 1 GB storage, 100K reads/day)
- Workers (Pages Functions): free (100K requests/day)

For a single internal dashboard, you'll never approach these limits.
