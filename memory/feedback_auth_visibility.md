---
name: auth.js must not hide page during validate
description: Never gate page visibility on async auth validation — causes Chrome renderer freeze on large dashboards
type: feedback
originSessionId: 464c19e0-6b02-4a2b-9dd7-a26a979ae0a0
---
auth.js on sector Intel dashboards must never set `document.documentElement.style.visibility = 'hidden'` (or equivalent document-wide hide) while awaiting `/api/auth/validate`. Let the page render; redirect on failure.

**Why:** On 2026-04-21 users reported most sector dashboards opened as a "blank page with spinning icon" when launched from the hub. Chrome's renderer froze (CDP `Runtime.evaluate` timed out at 45s) on 300KB+ pages with heavy inline scripts while visibility was hidden during the ~100-500ms validate fetch. Headless Chromium was unaffected, which masked the bug in CI-style testing. Removing the visibility gate from auth.js across all 14 sector sites restored normal rendering.

**How to apply:** When creating or editing any dashboard auth.js (sector-intel sites, new verticals, templated clones), verify no document-wide hide is used. If blocking UI is needed during validate, use a small overlay element — never the whole document. Applies to auth scripts at the per-site level, not to the hub gateway itself.
