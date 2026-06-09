---
name: User-Agent rules for third-party APIs
description: Cloudflare-fronted APIs block default Python/generic UAs; FRED blocks custom UAs. Two opposite rules — pick the right one per endpoint.
type: reference
originSessionId: 8ca7f5e1-bab5-4175-8b7f-2f92cc145c63
---
HTTP User-Agent rules differ by endpoint provider. Getting this wrong causes silent failures (timeouts, 403s) that look like auth or network issues.

## Cloudflare-fronted APIs (Resend, most modern SaaS): set an EXPLICIT UA
- `api.resend.com` and similar return `HTTP 403 error code: 1010` ("access denied based on browser signature") when called with Python's default `Python-urllib/3.x` UA.
- Python stdlib example:
  ```python
  headers = {
      "Authorization": f"Bearer {key}",
      "Content-Type": "application/json",
      "User-Agent": "YourScript/1.0",
  }
  ```
- Discovered 2026-04-21 while building `pending_users_digest.py` — 403 on first run, worked immediately after adding UA header.

## FRED (fred.stlouisfed.org): use DEFAULT UA — strip `-A` from curl
- FRED silently blocks custom User-Agent strings. Request hangs until timeout.
- Discovered 2026-04-17 after weeks of silent pipeline failures (lesson #20 in Master Intelligence).

## Rule of thumb
- Cloudflare / modern SaaS → **explicit UA required**
- FRED / some government APIs → **no custom UA, use library default**
- When a script works from a Cloudflare Workers runtime but fails from local Python (or vice versa), check UA headers first before suspecting auth or network.
