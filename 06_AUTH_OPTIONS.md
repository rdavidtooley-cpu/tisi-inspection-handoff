# 06 — Auth Options

Pick **one** before deploy. Both options keep the same UX: visit the URL → password gate → 24hr session. The difference is the back end.

The original Inspection Intel site started with Option A and later moved to a hub-based system across many sites. For a single TISI-only deployment, **Option A is recommended.**

---

## Option A — Standalone single password (recommended)

One password, shared by all users. SHA-256 hash baked into `auth.js`. Session stored in localStorage for 24 hours. No backend, no Pages Functions for auth, no KV.

### How it works

1. User visits any page
2. `auth.js` checks `localStorage.tisi_auth` for a valid session
3. If missing or expired, redirect to `login.html`
4. User enters password
5. `auth.js` computes SHA-256 in the browser, compares to baked-in hash
6. If match, write `{token: <random>, expires_at: <now + 24h>}` to localStorage
7. Redirect back

### Pros

- Zero backend complexity
- Works on any static host (not just Cloudflare)
- One password for the user to share with the team
- Can rotate by editing one constant + redeploying

### Cons

- No per-user audit trail
- Password is in client-side JS (anyone can read the hash — but can't reverse it for a strong password)
- No revoke for individual users

### Setup

The handoff ships `source/Dashboard/auth.js` already configured for Option A. Just replace the hash:

```javascript
// auth.js — change this line
const PASSWORD_HASH = "__SET_YOUR_PASSWORD_HASH__";
const SESSION_KEY = "tisi_auth";    // rename if you want
const SESSION_HOURS = 24;
```

Generate the hash:

```bash
echo -n "YourStrongPassword!" | shasum -a 256 | awk '{print $1}'
```

Drop the 64-char hex into `PASSWORD_HASH`. Done.

### login.html

A minimal form with one password input + submit button. The shipped `login.html` already does this. After successful auth, redirects to `index.html`.

---

## Option B — Per-site user accounts

Per-user accounts with email + password, admin approval workflow, password reset, audit log. Backed by Cloudflare KV.

### How it works

1. New user visits `register.html`, submits email + password
2. Pages Function `/api/auth/register` writes pending user to KV `USERS` namespace
3. Admin gets email notification, approves via `admin.html`
4. User logs in at `login.html`, Pages Function `/api/auth/login` writes session to KV
5. Session token stored in localStorage, validated against KV via `/api/auth/me`

### Pros

- Per-user audit trail
- Revoke individual users without rotating a shared password
- Email-based password reset
- Supports admin tier

### Cons

- Three more Pages Functions to maintain (`/api/auth/{register,login,logout,me}`, `/api/admin/users`)
- KV namespace to manage (`USERS`)
- Admin email setup required
- More code surface to audit

### Setup outline

1. Create a `USERS` KV namespace: `npx wrangler kv:namespace create USERS`
2. Add binding to `wrangler.toml`:

   ```toml
   [[kv_namespaces]]
   binding = "USERS"
   id = "<new id>"
   ```

3. Replace `Dashboard/auth.js` with the user-account variant (template below)
4. Add Pages Functions:
   - `Dashboard/functions/api/auth/register.js`
   - `Dashboard/functions/api/auth/login.js`
   - `Dashboard/functions/api/auth/logout.js`
   - `Dashboard/functions/api/auth/me.js`
   - `Dashboard/functions/api/admin/users.js`
5. Add `register.html`, `admin.html` pages
6. Set `ADMIN_EMAIL` env var on the Pages project for new-registration notifications

This is meaningfully more work — count on 1–2 hours of careful build and testing. If you don't need per-user audit, **don't.**

### KV schema (if you build Option B)

- `user:{email}` → `{email, name, password_hash, salt, role, created_at, last_login}`
- `session:{token}` → `{user_email, expires_at}` with 7-day TTL
- `_user_index` → JSON array of all email addresses

Password hashing: SHA-256 with 16-byte random salt, stored as `salt:hash`. Roles: `pending` → `user` → `admin`. First registrant auto-becomes admin.

---

## Critical auth.js rules (apply to BOTH options)

- **Never set `document.visibility:hidden` during validate.** Causes Chrome renderer freeze on large dashboards. The shipped auth.js does not do this — don't add it.
- **MutationObservers that write to observed DOM must disconnect during writes.** Self-trigger loops freeze the browser.
- Validate runs once on page load and on focus events — not on every paint.

---

## Where each option lives in the shipped source

- The shipped `source/Dashboard/auth.js` is Option A (standalone single password) with the hash replaced by `__SET_YOUR_PASSWORD_HASH__`.
- The shipped `source/Dashboard/login.html` is the Option A login form.
- The shipped `source/Dashboard/functions/api/` contains **only** the subscribe/quotes endpoints — no auth functions. If you choose Option B, add the auth functions yourself.

## Recommendation

Start with Option A. If the user later needs per-user audit (regulatory, contractor access, etc.), Option B is a clean upgrade path — the dashboards don't change, only the auth layer.
