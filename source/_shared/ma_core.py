#!/usr/bin/env python3
"""
M&A Deal Core — shared helpers for M&A Dashboard pipelines.

Responsibilities:
  1. Normalize acquirer/target names to produce a stable deal ID
     (same deal from curated + 8-K sources collapses to one record)
  2. Merge curated + EDGAR-extracted deals into a single deduped list
  3. Validate deal record shape

Deal schema (all fields optional except id, date, acquirer, target, status, source):
    {
      "id": "exxonmobil|pioneer|2023-10",
      "date": "2023-10-11",
      "acquirer": "ExxonMobil",
      "acquirer_ticker": "XOM",
      "target": "Pioneer Natural Resources",
      "target_ticker": "PXD",
      "value_m": 64500,
      "ev_revenue": null,
      "ev_ebitda": null,
      "sector": "Upstream E&P",
      "rationale": "...",
      "status": "completed",       # completed | pending | rumored
      "source": "curated",         # curated | 8-K | curated+8-K
      "source_url": "https://..."
    }
"""

import json
import re
from pathlib import Path

# Corporate suffixes stripped during normalization
_SUFFIXES = [
    'incorporated', 'corporation', 'holdings', 'company',
    'inc', 'corp', 'ltd', 'llc', 'lp', 'plc',
    'group', 'co', 'nv', 'sa', 'ag', 'ab', 'ag',
]

_NON_ALPHA = re.compile(r'[^a-z0-9]+')


def normalize_entity(name: str) -> str:
    """Lowercase, strip corporate suffixes + punctuation + whitespace.

    ExxonMobil Corp         -> exxonmobil
    Pioneer Natural Res Inc -> pioneernaturalres
    IGT Gaming & Digital    -> igtgamingdigital
    """
    if not name:
        return ''
    n = name.lower().strip()
    # Strip suffixes (possibly comma-separated "Target, Inc.")
    for suf in sorted(_SUFFIXES, key=len, reverse=True):
        n = re.sub(r'[,\s]+' + re.escape(suf) + r'\b\.?$', '', n)
    n = _NON_ALPHA.sub('', n)
    return n


def make_deal_id(acquirer: str, target: str, date: str) -> str:
    """Stable ID = {acquirer_norm}|{target_norm}|{YYYY-MM}.

    Date is truncated to year-month so deals re-announced on a different
    day (common for M&A) still collapse to one record.
    """
    ym = (date or '')[:7]  # YYYY-MM
    return f'{normalize_entity(acquirer)}|{normalize_entity(target)}|{ym}'


_SOURCE_TOKENS = {'curated', '8-K', 'wire'}
_SOURCE_ORDER = ['curated', '8-K', 'wire']

# All valid single and compound source values
_VALID_SOURCES = {
    'curated', '8-K', 'wire',
    'curated+8-K', 'curated+wire', '8-K+wire',
    'curated+8-K+wire',
}


def _merge_sources(a: str, b: str) -> str:
    """Combine two source strings into a sorted compound tag.

    Order: curated first, 8-K second, wire third.
    """
    tokens = set()
    for src in (a, b):
        for tok in (src or '').split('+'):
            tok = tok.strip()
            if tok:
                tokens.add(tok)
    return '+'.join(t for t in _SOURCE_ORDER if t in tokens)


def validate_deal(d: dict) -> list:
    """Return list of validation errors (empty list = valid)."""
    errors = []
    required = ['date', 'acquirer', 'target', 'status', 'source']
    for f in required:
        if not d.get(f):
            errors.append(f'missing required field: {f}')
    status = d.get('status')
    if status and status not in ('completed', 'pending', 'rumored'):
        errors.append(f'invalid status: {status}')
    source = d.get('source')
    if source and source not in _VALID_SOURCES:
        errors.append(f'invalid source: {source}')
    date = d.get('date', '')
    if date and not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
        errors.append(f'invalid date format (need YYYY-MM-DD): {date}')
    return errors


def merge_deals(curated: list, edgar: list, wire: list = None) -> list:
    """Merge curated + EDGAR + wire deals.

    Curated is authoritative. EDGAR and wire deals add new rows or enrich
    existing rows with missing value_m. Source tags combine via set-union
    ordered curated > 8-K > wire.

    wire defaults to [] for backward compatibility.
    """
    if wire is None:
        wire = []

    out = {}

    # Curated first — primary source
    for d in curated:
        did = d.get('id') or make_deal_id(d.get('acquirer', ''), d.get('target', ''), d.get('date', ''))
        d = dict(d)
        d['id'] = did
        if not d.get('source'):
            d['source'] = 'curated'
        out[did] = d

    # EDGAR second — enrich or append
    for d in edgar:
        did = d.get('id') or make_deal_id(d.get('acquirer', ''), d.get('target', ''), d.get('date', ''))
        d = dict(d)
        d['id'] = did
        if did in out:
            existing = out[did]
            if existing.get('value_m') in (None, 0) and d.get('value_m'):
                existing['value_m'] = d['value_m']
            existing['source'] = _merge_sources(existing.get('source', ''), '8-K')
        else:
            if not d.get('source'):
                d['source'] = '8-K'
            out[did] = d

    # Wire third — enrich or append
    for d in wire:
        did = d.get('id') or make_deal_id(d.get('acquirer', ''), d.get('target', ''), d.get('date', ''))
        d = dict(d)
        d['id'] = did
        if did in out:
            existing = out[did]
            if existing.get('value_m') in (None, 0) and d.get('value_m'):
                existing['value_m'] = d['value_m']
            if existing.get('rationale') in (None, '') and d.get('rationale'):
                existing['rationale'] = d['rationale']
            existing['source'] = _merge_sources(existing.get('source', ''), 'wire')
        else:
            if not d.get('source'):
                d['source'] = 'wire'
            out[did] = d

    # Sort by date desc
    result = sorted(out.values(), key=lambda x: x.get('date', ''), reverse=True)
    return result


def build_site_deals(site_dir: Path) -> list:
    """Load curated + edgar + wire json from a site's Dashboard folder and return merged deals.

    site_dir is the Dashboard/ folder containing:
      - ma_deals_curated.json  (required)
      - ma_deals_edgar.json    (optional; defaults to [])
      - ma_deals_wire.json     (optional; defaults to [])

    Writes merged result to ma_deals.json and returns the list.
    """
    curated_path = site_dir / 'ma_deals_curated.json'
    edgar_path = site_dir / 'ma_deals_edgar.json'
    wire_path = site_dir / 'ma_deals_wire.json'
    out_path = site_dir / 'ma_deals.json'

    curated = []
    if curated_path.exists():
        with open(curated_path) as f:
            curated = json.load(f)

    edgar = []
    if edgar_path.exists():
        with open(edgar_path) as f:
            edgar = json.load(f)

    wire = []
    if wire_path.exists():
        with open(wire_path) as f:
            wire = json.load(f)

    # Validate curated (stricter)
    all_errors = []
    for i, d in enumerate(curated):
        errs = validate_deal(d)
        if errs:
            all_errors.append(f'curated[{i}] ({d.get("acquirer")} -> {d.get("target")}): {errs}')
    if all_errors:
        raise ValueError('Curated deal validation failed:\n  ' + '\n  '.join(all_errors))

    merged = merge_deals(curated, edgar, wire)
    with open(out_path, 'w') as f:
        json.dump(merged, f, indent=2)
    return merged


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('Usage: python3 ma_core.py <site_dashboard_dir>')
        sys.exit(1)
    site = Path(sys.argv[1])
    merged = build_site_deals(site)
    curated_count = sum(1 for d in merged if d.get('source') == 'curated')
    edgar_count = sum(1 for d in merged if '8-K' in d.get('source', ''))
    wire_count = sum(1 for d in merged if 'wire' in d.get('source', ''))
    compound = [d for d in merged if '+' in d.get('source', '')]
    print(f'Wrote {len(merged)} deals to {site}/ma_deals.json')
    print(f'  curated-only: {curated_count}, with 8-K: {edgar_count}, with wire: {wire_count}, compound: {len(compound)}')
    if compound:
        ex = compound[0]
        print(f'  Example compound: {ex["acquirer"]} → {ex["target"]} [{ex["source"]}]')
