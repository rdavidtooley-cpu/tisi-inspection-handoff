#!/usr/bin/env python3
"""
Pipeline fix — add `change_pct` field at source in all refresh_dashboard.py
scripts so Peer / Industry / Company Summary pages render real daily % change
straight from the injected MD blobs, without depending on the client-side
hotfix script.

Idempotent by content check: if `change_pct` already appears adjacent to the
target line, the edit is skipped.

Targets (14 refresh scripts):
  * Oil_Gas_Intel/Dashboard/refresh_dashboard.py                    (template)
  * Autos_Intel/Dashboard/refresh_dashboard.py                      (scaffolded)
  * Aerospace_Defense_Intel/Dashboard/refresh_dashboard.py          (scaffolded)
  * Chemicals_Intel/Dashboard/refresh_dashboard.py                  (scaffolded)
  * Homebuilders_Intel/Dashboard/refresh_dashboard.py               (scaffolded)
  * Power_Utilities_Intel/Dashboard/refresh_dashboard.py            (scaffolded)
  * REITs_Intel/Dashboard/refresh_dashboard.py                      (scaffolded)
  * Rail_Logistics_Intel/Dashboard/refresh_dashboard.py             (scaffolded)
  * Semiconductors_Intel/Dashboard/refresh_dashboard.py             (scaffolded)
  * Shipping_Intel/Dashboard/refresh_dashboard.py                   (scaffolded)
  * Casino_Gaming_Intel/_scripts/refresh_casino_gaming_dashboard.py (bespoke)
  * Inspection_Intel/_scripts/refresh_inspection_dashboard.py       (bespoke)
  * Metal_Mining_Intel/_scripts/refresh_metal_mining_dashboard.py   (bespoke)
  * Media_Broadcasting_Intel/Dashboard/refresh_media_dashboard.py   (bespoke)

Transforms:
  T1 — fetch_ticker_data() dict: add `'change_pct'` alias next to existing
       `'daily_change_pct': info.get('regularMarketChangePercent')` line.
  T2 — OG-style Industry bundle market_data builder: add `'change_pct'` next
       to `'daily_change': r.get('daily_change')`.
  T3 — OG-style Peer md_dict: add `'daily_change'` + `'change_pct'` before
       `'category': p.get('og_subsector', ...)`.
  T4 — OG-style Company Summary market_data_summary: add `'change_pct'` next
       to `'daily_change_pct': r.get('daily_change')`.
  T5 — Media refresh line `'daily_change': info.get('regularMarketChangePercent')`
       → add `'change_pct'` alias right after.

Run:
  python3 _shared/fix_pipeline_change_pct.py              # dry run
  python3 _shared/fix_pipeline_change_pct.py --apply
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TARGETS = [
    'Oil_Gas_Intel/Dashboard/refresh_dashboard.py',
    'Autos_Intel/Dashboard/refresh_dashboard.py',
    'Aerospace_Defense_Intel/Dashboard/refresh_dashboard.py',
    'Chemicals_Intel/Dashboard/refresh_dashboard.py',
    'Homebuilders_Intel/Dashboard/refresh_dashboard.py',
    'Power_Utilities_Intel/Dashboard/refresh_dashboard.py',
    'REITs_Intel/Dashboard/refresh_dashboard.py',
    'Rail_Logistics_Intel/Dashboard/refresh_dashboard.py',
    'Semiconductors_Intel/Dashboard/refresh_dashboard.py',
    'Shipping_Intel/Dashboard/refresh_dashboard.py',
    'Casino_Gaming_Intel/_scripts/refresh_casino_gaming_dashboard.py',
    'Inspection_Intel/_scripts/refresh_inspection_dashboard.py',
    'Metal_Mining_Intel/_scripts/refresh_metal_mining_dashboard.py',
    'Media_Broadcasting_Intel/Dashboard/refresh_media_dashboard.py',
]


def patch_t1_fetch_ticker(text: str):
    """Add `'change_pct'` alias after any line matching
    `'daily_change_pct': info.get('regularMarketChangePercent')`.
    """
    pat = re.compile(
        r"(^(\s*)'daily_change_pct':\s*info\.get\('regularMarketChangePercent'\)[^\n]*\n)",
        re.MULTILINE,
    )
    n = 0

    def sub(m):
        nonlocal n
        line = m.group(1)
        indent = m.group(2)
        # idempotent — skip if the next line already defines change_pct
        after = text[m.end():m.end() + 200]
        if re.match(r"\s*'change_pct':", after):
            return line
        n += 1
        return line + f"{indent}'change_pct': info.get('regularMarketChangePercent'),\n"

    return pat.sub(sub, text), n


def patch_t2_industry_bundle(text: str):
    """OG-style industry bundle: add change_pct next to daily_change inline."""
    # Pattern matches a single line containing `'daily_change': r.get('daily_change'), 'pe_ratio':`
    pat = re.compile(
        r"('daily_change':\s*r\.get\('daily_change'\),\s*)('pe_ratio':\s*r\.get\('pe_ratio'\))",
    )
    n = 0

    def sub(m):
        nonlocal n
        prefix = m.group(1)
        suffix = m.group(2)
        # Already patched?
        if "'change_pct'" in prefix:
            return m.group(0)
        n += 1
        return prefix + "'change_pct': r.get('daily_change'), " + suffix

    return pat.sub(sub, text), n


def patch_t3_peer_mddict(text: str):
    """OG-style peer md_dict: insert daily_change + change_pct before
    `'category': p.get('og_subsector', 'Other'),` inside the md_dict builder.
    Scope: only inside an `md_dict[p['ticker']] = {` block.
    """
    # Locate the block
    block_re = re.compile(
        r"(md_dict\[p\['ticker'\]\]\s*=\s*\{)(.*?)(\n\s*\})",
        re.DOTALL,
    )
    total = 0

    def block_sub(bm):
        nonlocal total
        head, body, tail = bm.group(1), bm.group(2), bm.group(3)
        if "'daily_change'" in body and "'change_pct'" in body:
            return bm.group(0)
        cat_re = re.compile(
            r"(^(\s*)'category':\s*p\.get\('og_subsector',\s*'Other'\),)",
            re.MULTILINE,
        )
        m = cat_re.search(body)
        if not m:
            return bm.group(0)
        indent = m.group(2)
        inject = (
            f"{indent}'daily_change': p.get('daily_change'),\n"
            f"{indent}'change_pct': p.get('daily_change'),\n"
        )
        new_body = body[:m.start()] + inject + body[m.start():]
        total += 1
        return head + new_body + tail

    return block_re.sub(block_sub, text), total


def patch_t4_summary_market_data(text: str):
    """OG-style Company Summary market_data_summary: add change_pct after
    daily_change_pct line."""
    pat = re.compile(
        r"(^(\s*)'daily_change_pct':\s*r\.get\('daily_change'\),\s*\n)",
        re.MULTILINE,
    )
    n = 0

    def sub(m):
        nonlocal n
        line = m.group(1)
        indent = m.group(2)
        after = text[m.end():m.end() + 200]
        if re.match(r"\s*'change_pct':", after):
            return line
        n += 1
        return line + f"{indent}'change_pct': r.get('daily_change'),\n"

    return pat.sub(sub, text), n


def patch_t5_media(text: str):
    """Media refresh: add change_pct after
    `'daily_change': info.get('regularMarketChangePercent', None)`.
    """
    pat = re.compile(
        r"(^(\s*)'daily_change':\s*info\.get\('regularMarketChangePercent',\s*None\),\s*\n)",
        re.MULTILINE,
    )
    n = 0

    def sub(m):
        nonlocal n
        line = m.group(1)
        indent = m.group(2)
        after = text[m.end():m.end() + 200]
        if re.match(r"\s*'change_pct':", after):
            return line
        n += 1
        return line + f"{indent}'change_pct': info.get('regularMarketChangePercent', None),\n"

    return pat.sub(sub, text), n


def process(apply: bool):
    total_changes = 0
    per_file = []
    for rel in TARGETS:
        path = ROOT / rel
        if not path.exists():
            per_file.append((rel, None, "missing"))
            continue
        text = path.read_text(encoding='utf-8')
        orig = text
        stats = {}
        text, stats['T1'] = patch_t1_fetch_ticker(text)
        text, stats['T2'] = patch_t2_industry_bundle(text)
        text, stats['T3'] = patch_t3_peer_mddict(text)
        text, stats['T4'] = patch_t4_summary_market_data(text)
        text, stats['T5'] = patch_t5_media(text)
        changed = sum(stats.values())
        per_file.append((rel, stats, "ok"))
        total_changes += changed
        if apply and changed and text != orig:
            path.write_text(text, encoding='utf-8')

    print(f"\n=== fix_pipeline_change_pct.py — {'APPLY' if apply else 'DRY-RUN'} ===\n")
    for rel, stats, status in per_file:
        if status == "missing":
            print(f"  [skip]   {rel} — missing")
            continue
        counts = ' '.join(f"{k}={v}" for k, v in stats.items())
        total = sum(stats.values())
        mark = '*' if total else ' '
        print(f"  [{mark}]      {rel}  ({counts}, total={total})")
    print(f"\nTotal edits: {total_changes}")
    if not apply:
        print("Re-run with --apply to write changes.")


if __name__ == '__main__':
    process('--apply' in sys.argv)
