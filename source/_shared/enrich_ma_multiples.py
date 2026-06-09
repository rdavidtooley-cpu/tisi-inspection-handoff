#!/usr/bin/env python3
"""Enrich M&A curated deal multiples (ev_revenue, ev_ebitda) using yfinance.

For each deal in every site's ma_deals_curated.json where target_ticker is set
and ev_revenue or ev_ebitda is null, pull the target's last annual financials
reported *before* the deal date and compute:

    ev_revenue  = round(value_m / revenue_m,  1)
    ev_ebitda   = round(value_m / ebitda_m,   1)

If yfinance cannot resolve the ticker or lacks a pre-deal annual period (common
for deals where the target was subsequently delisted), the deal is left alone
and flagged in the run log for manual curation.

Usage:
    python3 _shared/enrich_ma_multiples.py          # dry run, prints what would change
    python3 _shared/enrich_ma_multiples.py --write  # writes back to the curated JSONs
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

try:
    import yfinance as yf
except ImportError:
    sys.stderr.write("yfinance not installed. pip3 install yfinance\n")
    sys.exit(1)

BASE = Path(__file__).resolve().parent.parent
SITES = [
    'Casino_Gaming_Intel',
    'Oil_Gas_Intel',
    'Metal_Mining_Intel',
    'Media_Broadcasting_Intel',
    'Inspection_Intel',
]


def _best_annual(df, deal_date: str):
    """Return (period_label, series) for the latest annual column with period-end < deal_date."""
    if df is None or df.empty:
        return None
    cols = [c for c in df.columns if str(c)[:10] < deal_date]
    if not cols:
        return None
    col = max(cols)
    return col, df[col]


def _num(val):
    """yfinance returns numpy scalars / NaN. Coerce to float or None."""
    try:
        f = float(val)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


def compute_multiples(ticker: str, deal_date: str, value_m: float) -> dict:
    """Return {'ev_revenue': x, 'ev_ebitda': y, 'note': str} or {} on failure."""
    try:
        t = yf.Ticker(ticker)
        fin = t.financials  # annual income statement
        cf = t.cashflow     # annual cash flow (fallback for D&A)
    except Exception as e:
        return {'note': f'yfinance error: {e}'}

    pick_fin = _best_annual(fin, deal_date)
    if not pick_fin:
        return {'note': f'no annual financials before {deal_date}'}

    _, series = pick_fin
    revenue = _num(series.get('Total Revenue'))
    ebitda = _num(series.get('EBITDA'))

    # Fallback: OperatingIncome + D&A from cash flow same period
    if ebitda is None:
        op_income = _num(series.get('Operating Income'))
        da = None
        if cf is not None and not cf.empty:
            pick_cf = _best_annual(cf, deal_date)
            if pick_cf:
                _, cf_series = pick_cf
                da = _num(cf_series.get('Depreciation And Amortization'))
        if op_income is not None and da is not None:
            ebitda = op_income + da

    out = {}
    if revenue and revenue > 0:
        mult = round(value_m / (revenue / 1_000_000.0), 1)
        if 0.1 <= mult <= 100:
            out['ev_revenue'] = mult
    if ebitda and ebitda > 0:
        mult = round(value_m / (ebitda / 1_000_000.0), 1)
        if 0.1 <= mult <= 100:
            out['ev_ebitda'] = mult
    if not out:
        out['note'] = 'target financials present but multiples out of sane range or zero'
    return out


def process_site(site: str, write: bool) -> dict:
    path = BASE / site / 'Dashboard' / 'ma_deals_curated.json'
    if not path.exists():
        return {'site': site, 'error': 'missing ma_deals_curated.json'}
    with open(path) as f:
        deals = json.load(f)

    before_filled = sum(1 for d in deals if d.get('ev_revenue') or d.get('ev_ebitda'))
    total = len(deals)
    changed = 0
    log = []

    for d in deals:
        tgt = d.get('target_ticker')
        val = d.get('value_m')
        if not tgt or not val:
            continue
        if d.get('ev_revenue') and d.get('ev_ebitda'):
            continue  # already both filled
        res = compute_multiples(tgt, d.get('date', ''), val)
        time.sleep(0.3)  # macOS DNS safety (lesson #3)
        note = res.pop('note', None)
        if not res:
            log.append(f"  SKIP {tgt:8} {d.get('target','')[:30]:30} — {note}")
            continue
        updated = False
        for k, v in res.items():
            if d.get(k) in (None, 0):
                d[k] = v
                updated = True
        if updated:
            changed += 1
            log.append(f"  FILL {tgt:8} {d.get('target','')[:30]:30} ev/rev={d.get('ev_revenue')} ev/ebitda={d.get('ev_ebitda')}")

    after_filled = sum(1 for d in deals if d.get('ev_revenue') or d.get('ev_ebitda'))

    if write and changed:
        with open(path, 'w') as f:
            json.dump(deals, f, indent=2)

    return {
        'site': site,
        'total': total,
        'before_filled': before_filled,
        'after_filled': after_filled,
        'changed': changed,
        'log': log,
    }


def main():
    write = '--write' in sys.argv
    print(f"Mode: {'WRITE' if write else 'DRY-RUN'}\n")
    for site in SITES:
        res = process_site(site, write)
        if res.get('error'):
            print(f"{site}: {res['error']}")
            continue
        print(f"{site}")
        print(f"  before: {res['before_filled']} filled / {res['total']} total")
        print(f"  after:  {res['after_filled']} filled / {res['total']} total (changed {res['changed']})")
        for line in res['log']:
            print(line)
        print()


if __name__ == '__main__':
    main()
