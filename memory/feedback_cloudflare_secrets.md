---
name: Cloudflare Pages secrets drift from local .env
description: Rotating API keys requires updating every Pages project separately; never swallow webhook/email failures silently
type: feedback
originSessionId: 8ca7f5e1-bab5-4175-8b7f-2f92cc145c63
---
Cloudflare Pages project secrets are **independent** of local `.env`. Rotating a key in `.env` does NOT propagate — each Pages project stores its own copy.

**Why:** Three hub self-registrations (Olivia 4-13, Tom 4-17, Oleg 4-21) silently failed to email admin because `RESEND_API_KEY` on the `sector-intel-hub` Pages project was `re_YdHKx...` (old/revoked), while the working key in local `.env` was `re_69dbnk...`. Resend returned `401 validation_error` which was swallowed by a try/catch `/* email failure is non-fatal */`. Robert lost visibility on real access requests for 8 days.

**How to apply:**
1. When rotating any API key (Resend, Stripe, third-party webhook), run `npx wrangler pages secret put <KEY> --project-name=<proj>` for EVERY Pages project that uses it. Known RESEND_API_KEY consumers: `sector-intel-hub`, `casino-gaming-intel`, `oil-gas-intel`, `inspection-intel`, `metal-mining-intel`, `media-broadcasting-intel`.
2. Never swallow third-party API failures silently. Pattern:
   ```js
   if (!r.ok) console.error(`[scope] Resend failed ${r.status}: ${await r.text()}`);
   ```
   `console.error` surfaces in Cloudflare Pages function logs.
3. When debugging why a Pages Function integration "works locally but not in production," add temporary debug fields to the API response (key_prefix, response status, response body), curl the live endpoint, read the response, then remove debug and redeploy.
4. Always test end-to-end through the live endpoint after rotating a secret — a direct API call from your Mac does not prove the Pages secret is correct.
