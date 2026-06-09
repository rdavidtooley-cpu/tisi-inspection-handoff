---
name: Always deploy Cloudflare Pages changes immediately
description: For any edit to a live dashboard on Cloudflare Pages, run wrangler pages deploy as part of the same task — don't leave changes local. Exception for net-new sector scaffolding in build-and-pause mode.
type: feedback
originSessionId: e0327c90-0531-46f5-98de-3653b99c0918
---
Any edit to a Cloudflare-Pages-hosted dashboard (Casino Gaming, Oil & Gas, Metal Mining, Inspection, Media & Broadcasting, Power & Utilities, Shipping & Maritime, Chemicals, Aerospace & Defense, Rail & Logistics, Sector Intel Hub) must be deployed in the same task, not left for Robert to request.

**Why:** Robert cannot see changes on the live site until they're deployed. Saying "done" while the files are only local is misleading and wastes a cycle — he has to come back and ask for deployment.

**How to apply:**
- After editing any file in `*/Dashboard/` directories on a *live* sector, run `npx wrangler pages deploy . --project-name=<project> --commit-dirty=true` from that Dashboard folder as part of the same task
- Project names: `casino-gaming-intel`, `oil-gas-intel`, `metal-mining-intel`, `inspection-intel`, `media-broadcasting-intel`, `power-utilities-intel`, `shipping-intel`, `chemicals-intel`, `aerospace-defense-intel`, `rail-logistics-intel`, `sector-intel-hub`
- Edit the template AND the live file, then deploy
- Include the deploy step in the todo list so it's visible
- Report the deploy URL(s) in the summary so Robert can verify directly

**Exception — build-and-pause sector scaffolding:**
When scaffolding a *net-new* sector that has a scheduled deploy date in the future (via `scheduled-tasks` MCP), do NOT deploy the Dashboard/ during the build session. The dashboard stays local, the Pages project + KV namespaces stay empty, and the Sector Intel Hub card remains hidden (`style="display:none;" data-deploy-date="YYYY-MM-DD"`) until the scheduled task fires on Monday of deploy week. This is how the staggered one-per-week rollout works. When editing the hub for a *future* sector card, do NOT deploy the hub — the card is hidden anyway.
