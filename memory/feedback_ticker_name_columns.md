---
name: Two-column tables — Ticker column = ticker only, Company column = name only
description: When a dashboard table has separate Ticker and Company columns, each cell shows only its own value. Never duplicate as "Name (TICKER)" inline.
type: feedback
originSessionId: 8c8c4e3a-a921-47d1-a25a-6df1a7e8d1f5
---
When a table has BOTH a Ticker column AND a Company/Name column, each cell renders only its own field:
- Ticker cell: just the ticker (link to company summary is fine).
- Company/Name cell: just the company name (optional website link).

**Why:** Robert flagged Inspection Intel showing "Name (TICKER)" inside a Ticker column AND inside the Company column right next to it on Equities/Peer/MA/Industry dashboards. Duplicates the name, buries the ticker, and looks unprofessional. The bug was in `yfLink(t)` / `coLink(t)` helpers that both returned `${d.name} (${d.display_ticker})`.

**How to apply:**
- Inline `${d.name} (${d.display_ticker})` is fine for SINGLE-column contexts only — `<select>` options, mover cards, headline copy, tooltip `title=` attributes.
- Any new sector dashboard: check `yfLink` / `coLink` helpers and any direct `<td>...name.*ticker...</td>` patterns against the column header — if there are separate Ticker and Company columns, strip the duplicate.
- The older `feedback_info_icons` rule that says "Show Company Name (TICKER) not just ticker symbols" applies to single-column displays only, NOT to two-column tables. Do not apply that rule to fix a two-column table.
- Canonical reference for correct rendering: Casino Gaming Intel `CG_Equities_Dashboard.html` and Inspection Intel `TIC_NDT_Company_Summary.html` (post-fix).

**Related:** Earnings dashboards may also have a separate bug where the "Full transcript" link uses `t.file` while the data field is actually `html_file`, AND the link prepends `transcripts/` even though `html_file` already starts with `transcripts/`. Check the working Company Summary pattern (`<a href="${t.html_file}">`) when porting to other sector earnings pages.
