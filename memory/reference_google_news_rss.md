---
name: Google News RSS for free news aggregation
description: Free zero-token replacement for paid news-aggregation APIs like Bigdata, News API, Factiva. Useful any project that needs filtered news feeds.
type: reference
originSessionId: 21eb761b-ad39-41aa-bde6-806259037929
---
Google News RSS is a free, stdlib-only aggregator of PR Newswire, Business Wire, and essentially all English-language trade press. Zero API key, zero tokens, zero dependencies — just `urllib.request` + `xml.etree.ElementTree`.

**URL format:**
```
https://news.google.com/rss/search?q={QUERY}&hl=en-US&gl=US&ceid=US:en
```

URL-encode the query via `urllib.parse.urlencode({"q": query, "hl": "en-US", ...})`.

**Query pattern** — combine topic terms with sector keywords using boolean operators:
```
(acquires OR acquisition OR merger OR buyout) AND (mining OR gold OR copper)
```

**RSS item structure** — each `<item>` has:
- `<title>` — headline, BUT appended with ` - {PublisherName}` (must be stripped)
- `<description>` — article snippet (HTML-encoded, needs unescape + tag stripping)
- `<pubDate>` — RFC-822 format, parse with `email.utils.parsedate_to_datetime`
- `<link>` — article URL (via Google News redirect)
- `<source>` — publisher name tag

**Two critical gotchas:**

1. **Strip publisher suffix from titles** — Google News appends ` - Reuters` / ` - Bloomberg` / etc. to every headline. This breaks any regex that anchors to end-of-string. Always clean first:
   ```python
   title = re.sub(r"\s+-\s+[^-]{2,60}$", "", title)
   ```

2. **Google's keyword matching is fuzzy** — searching for "mining" will sometimes return pharma, data-mining, cryptocurrency-mining stories. Always add a relevance post-filter requiring at least one strong sector token (e.g. for mining: `["mining", "ore", "mineral", "gold", "copper", "lithium", "smelter"]`) in the title, acquirer, or target. Without this, cross-sector noise leaks in.

**User-Agent:** Use a real browser-shaped UA (`Mozilla/5.0 ...`). Google News sometimes serves empty feeds to CLI-shaped UAs.

**Rate limits:** None in practice for reasonable use (~dozens of calls/day per IP). No API key required.

**Reference implementation:** `_shared/fetch_ma_rss.py` in Master Intelligence — uses Google News RSS as the "wire" source for M&A deal discovery across 5 sector dashboards. Replaced a paid Bigdata MCP dependency with zero loss of coverage.

**When to use this over paid APIs:**
- News aggregation / press release monitoring
- Sector-specific event tracking (M&A, earnings, regulatory actions)
- Any workflow where Google News' 50k+ indexed sources provide sufficient recall

**When NOT to use:**
- Full article text extraction (RSS only gives snippets; would need scraping the redirect target)
- Real-time alerts (pubDate can lag 5-30 min)
- Historical archives older than ~30 days (Google News RSS is recency-biased)
