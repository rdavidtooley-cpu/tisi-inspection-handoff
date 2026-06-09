# 07 — Email Digest (optional)

The original site sends a weekday morning digest via Resend. Skip this entire doc if email isn't needed.

## What gets sent

A daily digest with:

- Top movers (intraday and 1-week)
- New M&A deals (last 24h)
- Earnings transcripts summarized in the last 24h
- Notable SEC filings
- Industry news headlines

Sent at ~6:30am ET weekdays via GitHub Actions or Resend API directly from the pipeline.

## Prereqs

- Resend account (free tier: 100 emails/day, 3,000/month)
- A domain you control, added to Resend and DNS-verified (SPF + DKIM)
- `RESEND_API_KEY` from `https://resend.com/api-keys`

## Step 1 — Verify your domain in Resend

1. Sign up at `https://resend.com`
2. Add your domain (e.g. `tisi.com`)
3. Add the SPF + DKIM DNS records to your DNS provider
4. Wait for verification (usually <5 minutes)
5. Create an API key with Full Access (or limited send-only)

## Step 2 — Set Pages env vars

In Cloudflare dashboard → Pages → your project → Settings → Environment variables:

| Variable | Value |
|---|---|
| `RESEND_API_KEY` | Your Resend API key (e.g. `re_...`) |
| `FROM_EMAIL` | `intel@yourdomain.com` (must be on the verified domain) |
| `ADMIN_EMAIL` | The admin's email for alerts |

Set them for both Production and Preview environments if you want them to work in both.

## Step 3 — Subscriber storage

The shipped `Dashboard/functions/api/subscribe.js` and `unsubscribe.js` write subscriber emails to the `SUBSCRIBERS` KV namespace created in `05_DEPLOYMENT.md`.

Schema:
- `email:{lowercase-email}` → `{email, name, subscribed_at, source}`
- `_subscriber_index` → JSON array of all emails

## Step 4 — Sending the digest

Two options:

### Option 4a — Cron via GitHub Actions

Create `.github/workflows/daily-digest.yml`:

```yaml
name: Daily Digest

on:
  schedule:
    - cron: '30 11 * * 1-5'   # 6:30am ET weekdays (UTC offset adjusts for DST)

jobs:
  send:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Send digest
        env:
          RESEND_API_KEY: ${{ secrets.RESEND_API_KEY }}
          FROM_EMAIL: ${{ secrets.FROM_EMAIL }}
        run: |
          python3 -m pip install requests
          python3 _scripts/check_alerts.py --send-digest
```

### Option 4b — Run from the daily LaunchAgent

The local `morning_pipeline.sh` already calls `_scripts/check_alerts.py` after the dashboard regenerates. It reads `.env` for `RESEND_API_KEY` and pushes the digest.

Create `.env` at the project root:

```bash
RESEND_API_KEY=re_...
FROM_EMAIL=intel@yourdomain.com
ADMIN_EMAIL=admin@yourdomain.com
```

`.env` must be gitignored. The shipped `_shared/pipeline_notify.py` and `_scripts/check_alerts.py` both load it.

## Subscribe / unsubscribe links in emails

Every digest email should include footer links:

```
You're receiving this because you subscribed to TISI Intel.
Unsubscribe: https://<your-site>/api/unsubscribe?email=<encoded-email>&token=<hmac>
```

The `token` is an HMAC of the email + a server-side secret, so users can't unsubscribe each other. The shipped Function validates this.

## Sending limits & gotchas

- **Resend free tier:** 100 emails/day. If your subscriber list grows past that, upgrade.
- **Domain reputation:** keep your bounce rate under 5%. Resend will throttle senders with high bounce rates.
- **First-touch tracking:** Resend reports opens/clicks in their dashboard. Useful for tuning content.
- **Cloudflare API requirements:** Resend's API requires an explicit User-Agent header. The shipped `pipeline_notify.py` sets one. FRED, by contrast, requires the **default** curl User-Agent (no custom). See the User-Agent reference memory file.

## Testing

Send a one-off test before scheduling:

```bash
cd ~/code/tisi-intel
export $(cat .env | xargs)
python3 _scripts/check_alerts.py --test --to admin@yourdomain.com
```

The test path sends a single email with the day's digest content to the specified address. Verify the email arrives, links work, and unsubscribe round-trips correctly.

## Disabling the digest

If you decide not to send emails:

1. Don't set `RESEND_API_KEY`
2. `check_alerts.py` will detect the missing key and skip silently
3. Subscribe API still works (collects emails) but no sends happen

That gives you the option to enable later without redeploying.
