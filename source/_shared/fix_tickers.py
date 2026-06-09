#!/usr/bin/env python3
"""
Fix three classes of ticker bugs across every Intel site.

T1 — Company Summary "undefined" bug: null-guards on q.display / q.price /
     q.changePct.
T2 — M&A Dashboard empty ticker bar: the ticker-inner <div> is never populated.
     Append a self-contained live /api/quotes IIFE before </body>.
T3 — Stale sub-dashboards (Earnings, Equities, Industry, Market, News, Peer):
     ticker renders once from the morning snapshot and never refreshes. Append
     an overlay IIFE that fetches /api/quotes every 60s and updates prices
     in place when possible, or full-renders when the container is empty.

Usage:
    python3 fix_tickers.py              # dry-run, prints plan
    python3 fix_tickers.py --apply      # write changes
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITES = [p for p in ROOT.iterdir() if p.is_dir() and p.name.endswith('_Intel')]

# Marker so the script is idempotent across runs.
MARKER = '__ticker_live_v2'
OLD_MARKERS = ['__ticker_live_v1']

# --- T1 replacements (Company Summary) -------------------------------------
T1_REPLACEMENTS = [
    (r'\$\{q\.display\}', '${q.display||q.ticker}'),
    (r'\$\{q\.price\.toFixed\(2\)\}', '${(q.price||0).toFixed(2)}'),
    (r'\$\{q\.changePct\.toFixed\(1\)\}', '${(q.changePct||0).toFixed(1)}'),
    (r'\$\{q\.changePct\.toFixed\(2\)\}', '${(q.changePct||0).toFixed(2)}'),
]

# --- T2/T3 universal live-ticker IIFE --------------------------------------
LIVE_TICKER_IIFE = """
<script>
/* __ticker_live_v2 — appended by fix_tickers.py (idempotent) */
(function(){
    var el = document.getElementById('ticker-track')
          || document.getElementById('ticker-inner')
          || document.getElementById('tickerTrack');
    if (!el) return;
    var useT = (el.id === 'ticker-inner');
    function fullRender(quotes){
        var html = '';
        quotes.forEach(function(q){
            var chg = q.changePct || 0;
            var arrow = chg > 0 ? '\\u25B2' : chg < 0 ? '\\u25BC' : '';
            if (useT) {
                var dir = chg > 0 ? 'up' : chg < 0 ? 'dn' : '';
                html += '<div class="ticker-item"><span class="t-sym">' + q.ticker + '</span><span class="t-price">$' + (q.price||0).toFixed(2) + '</span><span class="t-chg ' + dir + '">' + arrow + (chg >= 0 ? '+' : '') + chg.toFixed(1) + '%</span></div>';
            } else {
                var dir = chg > 0 ? 'tk-up' : chg < 0 ? 'tk-down' : 'tk-flat';
                html += '<div class="ticker-item"><span class="tk-sym">' + q.ticker + '</span><span class="tk-price">$' + (q.price||0).toFixed(2) + '</span><span class="' + dir + '">' + arrow + (chg >= 0 ? '+' : '') + chg.toFixed(1) + '%</span></div>';
            }
        });
        el.innerHTML = html + html;
    }
    function hasEmptySymbols(){
        var items = el.querySelectorAll('.ticker-item');
        if (items.length === 0) return false;
        var firstSym = items[0].querySelector('.tk-sym, .t-sym');
        return !firstSym || !(firstSym.textContent || '').trim();
    }
    function overlayUpdate(quotes){
        var qm = {};
        quotes.forEach(function(q){ qm[q.ticker] = q; });
        var items = el.querySelectorAll('.ticker-item');
        items.forEach(function(item){
            var sym = item.querySelector('.tk-sym, .t-sym');
            if (!sym) return;
            var tk = (sym.textContent || '').trim();
            var q = qm[tk];
            if (!q) return;
            var priceEl = item.querySelector('.tk-price, .t-price');
            if (priceEl) priceEl.textContent = '$' + (q.price||0).toFixed(2);
            var chg = q.changePct || 0;
            var arrow = chg > 0 ? '\\u25B2' : chg < 0 ? '\\u25BC' : '';
            var spans = item.querySelectorAll('span');
            var chgEl = spans[spans.length - 1];
            if (chgEl) chgEl.textContent = arrow + (chg >= 0 ? '+' : '') + chg.toFixed(1) + '%';
        });
    }
    function refresh(){
        var c = new AbortController();
        var t = setTimeout(function(){ c.abort(); }, 8000);
        fetch('/api/quotes', { signal: c.signal })
            .then(function(r){ if (!r.ok) throw 0; return r.json(); })
            .then(function(d){
                if (!d || !d.quotes || !d.quotes.length) return;
                var items = el.querySelectorAll('.ticker-item');
                if (items.length === 0 || hasEmptySymbols()) fullRender(d.quotes);
                else overlayUpdate(d.quotes);
            })
            .catch(function(){})
            .finally(function(){ clearTimeout(t); });
    }
    setTimeout(refresh, 1000);
    var __ti = setInterval(refresh, 60000);
    window.addEventListener('pagehide', function(){ clearInterval(__ti); });
})();
</script>
"""

# --- File classification ---------------------------------------------------
def classify(path: Path) -> str | None:
    """Return 't1', 't2', 't3' or None based on filename."""
    name = path.name.lower()
    if name == 'index.html' or name == 'index_template.html':
        return None
    if 'company_summary' in name:
        return 't1'
    if 'ma_dashboard' in name or name == 'ma_template.html':
        return 't2'
    for kw in ('earnings', 'equities', 'industry', 'market_dashboard',
               'market_template', 'news', 'peer'):
        if kw in name:
            return 't3'
    return None


def has_live_fetch(text: str) -> bool:
    return '/api/quotes' in text


def has_ticker_container(text: str) -> bool:
    return ('id="ticker-inner"' in text
            or "id='ticker-inner'" in text
            or 'id="ticker-track"' in text
            or "id='ticker-track'" in text
            or 'id="tickerTrack"' in text
            or "id='tickerTrack'" in text)


def append_before_body_close(text: str, snippet: str) -> str:
    idx = text.rfind('</body>')
    if idx < 0:
        return text + snippet
    return text[:idx] + snippet + '\n' + text[idx:]


# --- Main ------------------------------------------------------------------
def process(apply: bool):
    t1_files, t2_files, t3_files, skipped = [], [], [], []
    for site in SITES:
        dash = site / 'Dashboard'
        if not dash.is_dir():
            continue
        for html in sorted(dash.glob('*.html')):
            kind = classify(html)
            if not kind:
                continue
            text = html.read_text(encoding='utf-8')

            if kind == 't1':
                new = text
                for pat, repl in T1_REPLACEMENTS:
                    new = re.sub(pat, repl, new)
                if new != text:
                    t1_files.append(html)
                    if apply:
                        html.write_text(new, encoding='utf-8')
                else:
                    skipped.append((html, 't1-noop'))
                continue

            # T2 / T3 — append live-ticker IIFE if missing.
            if MARKER in text:
                skipped.append((html, f'{kind}-already-patched'))
                continue
            if not has_ticker_container(text):
                skipped.append((html, f'{kind}-no-ticker-container'))
                continue

            # Strip old version blocks so we can re-apply the new one.
            for old in OLD_MARKERS:
                # Match `<script>...old_marker...</script>` (non-greedy).
                text = re.sub(
                    r'\n?<script>[^<]*?' + re.escape(old) + r'.*?</script>\n?',
                    '',
                    text,
                    flags=re.DOTALL,
                )

            new = append_before_body_close(text, LIVE_TICKER_IIFE)
            if kind == 't2':
                t2_files.append(html)
            else:
                t3_files.append(html)
            if apply:
                html.write_text(new, encoding='utf-8')

    # --- Report ---
    print(f"\n=== fix_tickers.py — {'APPLY' if apply else 'DRY-RUN'} ===")
    print(f"\nT1 (Company Summary null-guards): {len(t1_files)} files")
    for f in t1_files:
        print(f"  {f.relative_to(ROOT)}")
    print(f"\nT2 (M&A live ticker append):     {len(t2_files)} files")
    for f in t2_files:
        print(f"  {f.relative_to(ROOT)}")
    print(f"\nT3 (sub-dashboard live ticker):  {len(t3_files)} files")
    for f in t3_files:
        print(f"  {f.relative_to(ROOT)}")
    print(f"\nTotal to change: {len(t1_files)+len(t2_files)+len(t3_files)}")
    print(f"Skipped: {len(skipped)} (already patched, has api/quotes, or no ticker)")
    if not apply:
        print("\nRe-run with --apply to write changes.")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='write changes (default: dry-run)')
    args = ap.parse_args()
    process(args.apply)
