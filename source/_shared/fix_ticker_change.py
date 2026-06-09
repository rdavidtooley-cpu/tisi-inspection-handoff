#!/usr/bin/env python3
"""
Hotfix v2: make Peer/Industry/Company renderTicker show real change %.

v1 bug: called page-global renderTicker() with no args. That works for Peer
and Industry (which read from globals) but Company Summary's renderTicker
requires a quotes array — calling with no args threw silently.

v2 fix: build a synthesized quotes array from market_data.json and pass it
to renderTicker. Pages that ignore args (Peer, Industry) still render from
their now-updated globals. Pages that need the array (Company Summary)
receive it.

Also replaces any v1 marker block with the v2 block automatically.

Idempotent via __ticker_change_fix_v4 marker.
"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITES = [p for p in ROOT.iterdir() if p.is_dir() and p.name.endswith('_Intel')]

MARKER_V1 = '__ticker_change_fix_v1'
MARKER_V2 = '__ticker_change_fix_v2'
MARKER_V3 = '__ticker_change_fix_v3'
MARKER_V4 = '__ticker_change_fix_v4'

BOOTSTRAP = """
<script>
/* __ticker_change_fix_v4 — appended by fix_ticker_change.py */
(function(){
  function mergeInto(target, src){
    if (!target || !src) return false;
    var changed = false;
    Object.keys(src).forEach(function(tk){
      var s = src[tk]; if (!s || typeof s !== 'object') return;
      var dc = (s.daily_change != null) ? s.daily_change
             : (s.day_change_pct != null) ? s.day_change_pct
             : (s.change_pct != null) ? s.change_pct : null;
      if (dc == null) return;
      if (!target[tk] || typeof target[tk] !== 'object') target[tk] = {ticker: tk};
      if (target[tk].daily_change == null) { target[tk].daily_change = dc; changed = true; }
      if (target[tk].change_pct == null)   { target[tk].change_pct   = dc; changed = true; }
      if (target[tk].price == null && s.price != null) { target[tk].price = s.price; changed = true; }
    });
    return changed;
  }
  function buildQuotes(src){
    var out = [];
    Object.keys(src).forEach(function(t){
      var r = src[t]; if (!r || r.price == null) return;
      var dc = (r.daily_change != null) ? r.daily_change
             : (r.day_change_pct != null) ? r.day_change_pct
             : (r.change_pct != null) ? r.change_pct : 0;
      out.push({ ticker: t, display: t, price: Number(r.price), changePct: Number(dc) });
    });
    return out;
  }
  function wireUp(){
    var p = fetch('market_data.json').then(function(r){ return r.ok ? r.json() : null; }).catch(function(){ return null; });
    p.then(function(data){
      if (!data) return;
      var src = {};
      if (Array.isArray(data)) {
        data.forEach(function(r){ if (r && r.ticker) src[r.ticker] = r; });
      } else if (typeof data === 'object') {
        src = data;
      }
      var touched = false;
      if (typeof MD !== 'undefined')
        touched = mergeInto(MD, src) || touched;
      if (typeof INDUSTRY_DATA !== 'undefined' && INDUSTRY_DATA && INDUSTRY_DATA.market_data)
        touched = mergeInto(INDUSTRY_DATA.market_data, src) || touched;
      if (typeof INJECTED_SUMMARY_DATA !== 'undefined' && INJECTED_SUMMARY_DATA && INJECTED_SUMMARY_DATA.market_data)
        touched = mergeInto(INJECTED_SUMMARY_DATA.market_data, src) || touched;
      var quotes = buildQuotes(src);
      function renderToDOM(strip){
        if (!strip) return false;
        // Detect class pattern from first existing item (Peer uses t-sym; else tk-sym)
        var first = strip.querySelector('.ticker-item');
        var isPeer = !!(first && first.querySelector('.t-sym'));
        var html = '';
        quotes.forEach(function(q){
          var chg = q.changePct || 0;
          var arrow = chg > 0 ? '\u25B2' : chg < 0 ? '\u25BC' : '';
          if (isPeer) {
            var dir = chg > 0 ? 'up' : chg < 0 ? 'dn' : '';
            html += '<div class="ticker-item"><span class="t-sym">'+(q.display||q.ticker)+'</span><span class="t-price"> '+Number(q.price||0).toFixed(2)+'</span><span class="t-chg '+dir+'">'+arrow+(chg>=0?'+':'')+chg.toFixed(1)+'%</span></div>';
          } else {
            var dir = chg > 0 ? 'tk-up' : chg < 0 ? 'tk-down' : 'tk-flat';
            html += '<div class="ticker-item"><span class="tk-sym">'+(q.display||q.ticker)+'</span><span class="tk-price">$'+Number(q.price||0).toFixed(2)+'</span><span class="tk-chg '+dir+'">'+arrow+(chg>=0?'+':'')+chg.toFixed(1)+'%</span></div>';
          }
        });
        strip.innerHTML = html + html;
        var duration = Math.max(60, Math.round((quotes.length / 40) * 120));
        strip.style.animationDuration = duration + 's';
        return true;
      }
      function paint(){
        // Try page-global renderTicker (Peer, Industry use this).
        if (typeof renderTicker === 'function') {
          try { renderTicker(quotes); } catch(e){}
          try { renderTicker(); } catch(e){}
        }
        // Always also do direct-DOM paint so closure-scoped renderers (Company Summary) get updated too.
        var strip = document.getElementById('ticker-track')
                  || document.getElementById('ticker-inner')
                  || document.getElementById('tickerTrack');
        renderToDOM(strip);
      }
      // Initial paint + delayed paints (to beat /api/quotes race on Company Summary).
      paint();
      setTimeout(paint, 1500);
      setTimeout(paint, 4000);
      // Re-assert every 65s to overwrite any /api/quotes setInterval that narrows to ~15 tickers.
      setInterval(paint, 65000);
    });
  }
  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    setTimeout(wireUp, 400);
  } else {
    document.addEventListener('DOMContentLoaded', function(){ setTimeout(wireUp, 400); });
  }
})();
</script>
"""

# Matches either the v1 or v2 block (including the enclosing <script>…</script>).
V1_BLOCK_RE = re.compile(
    r"\n?<script>\s*/\*\s*__ticker_change_fix_v1.*?</script>\s*",
    re.DOTALL,
)
V2_BLOCK_RE = re.compile(
    r"\n?<script>\s*/\*\s*__ticker_change_fix_v2.*?</script>\s*",
    re.DOTALL,
)
V3_BLOCK_RE = re.compile(
    r"\n?<script>\s*/\*\s*__ticker_change_fix_v3.*?</script>\s*",
    re.DOTALL,
)
V4_BLOCK_RE = re.compile(
    r"\n?<script>\s*/\*\s*__ticker_change_fix_v4.*?</script>\s*",
    re.DOTALL,
)


def is_target(name: str) -> bool:
    n = name.lower()
    return (('peer' in n and n.endswith('.html'))
            or ('industry' in n and 'dashboard' in n and n.endswith('.html'))
            or ('company_summary' in n))


def strip_old_blocks(text: str) -> str:
    text = V1_BLOCK_RE.sub('', text)
    text = V2_BLOCK_RE.sub('', text)
    text = V3_BLOCK_RE.sub('', text)
    text = V4_BLOCK_RE.sub('', text)
    return text


def append_before_body_close(text: str, snippet: str) -> str:
    idx = text.rfind('</body>')
    if idx < 0:
        return text + snippet
    return text[:idx] + snippet + '\n' + text[idx:]


def process(apply: bool):
    touched, skipped = [], []
    for site in SITES:
        dash = site / 'Dashboard'
        if not dash.is_dir():
            continue
        for html in sorted(dash.glob('*.html')):
            if 'template' in html.name.lower():
                continue
            if not is_target(html.name):
                continue
            text = html.read_text(encoding='utf-8')
            has_v4 = MARKER_V4 in text and 'renderToDOM' in text
            if has_v4:
                skipped.append((html, 'already-v4'))
                continue
            cleaned = strip_old_blocks(text)
            new = append_before_body_close(cleaned, BOOTSTRAP)
            touched.append(html)
            if apply:
                html.write_text(new, encoding='utf-8')

    print(f"\n=== fix_ticker_change.py v2 — {'APPLY' if apply else 'DRY-RUN'} ===")
    print(f"Files to patch: {len(touched)}")
    for f in touched:
        print(f"  {f.relative_to(ROOT)}")
    print(f"Skipped (already v2): {len(skipped)}")
    if not apply:
        print("\nRe-run with --apply to write changes.")


if __name__ == '__main__':
    apply = '--apply' in sys.argv
    process(apply)
