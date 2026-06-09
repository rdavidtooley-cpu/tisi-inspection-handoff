---
name: Always include Adjusted EBITDA
description: Financial data displays and extractions must include Adjusted EBITDA alongside reported EBITDA — it's what analysts focus on
type: feedback
---

Always include Adjusted EBITDA and Adjusted EBITDA margins alongside reported EBITDA in financial data.

**Why:** Most companies report adjusted EBITDA separately — it strips out one-time charges, restructuring costs, etc. and is the metric analysts actually use for valuation and comparisons. Showing only reported EBITDA misses what matters.

**How to apply:**
- Transcript metric extraction: add "adjusted EBITDA", "Adj. EBITDA", "Adjusted EBITDAR" to regex patterns
- Dashboard financial tables: show Adjusted EBITDA as the primary metric, reported as secondary
- Peer analysis: use adjusted figures for cross-company comparison
- Applies to all Intel projects (O&G, Casino, Inspection, Metal Mining)
