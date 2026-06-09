---
name: Unique KV namespace per sector site
description: Every Intel sector site must have its own KV namespace IDs in wrangler.toml — never copy IDs from another site's scaffold
type: feedback
originSessionId: f430370d-1bcf-47c8-8af7-4af247f50b33
---
Every sector site must have its OWN KV namespace IDs in `*_Intel/Dashboard/wrangler.toml`. Never copy a `wrangler.toml` from one sector to another without recreating its KV namespaces.

**Why:** On 2026-05-05 found Inspection and Oil & Gas were both bound to the same `SUBSCRIBERS` KV (`72d8c376992c4ec69b22340ae1f16fd8`) because Inspection's wrangler.toml was scaffolded by copy-paste from Oil & Gas. Latent bug — first real subscriber to either site would have appeared on both digests. Caught only by accident while auditing email-digest failures.

**How to apply:**
- Audit command: `grep -rh "^id = " */Dashboard/wrangler.toml | sort | uniq -c | sort -rn` — any count ≥ 2 = duplicate.
- When scaffolding a new sector: after copying a template `wrangler.toml`, run `npx wrangler kv namespace create "SUBSCRIBERS_<SITE>"` and patch the returned ID into the new file before deploy.
- `_shared/scaffold_new_sector.py` should automate this step. Same rule for any future per-site KVs (preferences, alerts, sessions, etc.).
- Post-fix audit (2026-05-05): all 14 sites now have unique KV IDs.
