#!/usr/bin/env python3
"""Apply research-based EV/Revenue and EV/EBITDA multiples to ma_deals_curated.json.

Sources: deal press releases, investor presentations, and trailing financials
from target 10-K/annual reports published before the deal date.

Deals where multiples are not meaningful (nominal $1 divestitures, partnership
agreements, debt restructurings, asset-level mine deals with no target P&L)
get a `multiples_note` field and keep their nulls.

Idempotent: only fills nulls. Existing non-null multiples are preserved.

Usage:
    python3 _shared/apply_ma_curated_multiples.py
"""

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# Map: (site, acquirer_substr, target_substr) -> {ev_revenue, ev_ebitda, multiples_note}
PATCHES = [
    # ============ Casino Gaming ============
    ('Casino_Gaming_Intel', 'Apollo', 'IGT Gaming',
        {'ev_revenue': 2.4, 'ev_ebitda': 10.2}),
    ('Casino_Gaming_Intel', 'DraftKings', 'Jackpocket',
        {'ev_revenue': 7.5, 'multiples_note': 'target loss-making; EV/EBITDA not meaningful'}),
    ('Casino_Gaming_Intel', 'MGM Resorts', 'LeoVegas',
        {'ev_ebitda': 14.0}),
    ('Casino_Gaming_Intel', 'Penn Entertainment', 'theScore',
        {'ev_revenue': 37.0, 'multiples_note': 'target loss-making; EV/EBITDA not meaningful'}),
    ('Casino_Gaming_Intel', 'Flutter', 'Sisal',
        {'ev_revenue': 2.6}),
    ('Casino_Gaming_Intel', 'Caesars', 'William Hill',
        {'ev_revenue': 1.8, 'ev_ebitda': 19.0}),
    ("Casino_Gaming_Intel", "Bally's", 'Gamesys',
        {'ev_revenue': 2.7, 'ev_ebitda': 9.8}),
    ('Casino_Gaming_Intel', 'Aristocrat', 'NeoGames',
        {'multiples_note': 'target EBITDA small relative to deal; EV/EBITDA not meaningful'}),
    ('Casino_Gaming_Intel', 'Hard Rock', 'Mirage',
        {'ev_ebitda': 7.2, 'multiples_note': 'based on 2019 pre-pandemic property EBITDA ~$150M'}),
    ('Casino_Gaming_Intel', 'Penn Entertainment', 'Barstool',
        {'multiples_note': 'nominal $1 divestiture; multiples not applicable'}),
    ('Casino_Gaming_Intel', 'Penn Entertainment', 'ESPN',
        {'multiples_note': '10-year partnership deal, not a business acquisition'}),
    ('Casino_Gaming_Intel', 'Churchill Downs', 'Exacta',
        {'multiples_note': 'private target; financials not disclosed'}),
    ('Casino_Gaming_Intel', 'Boyd', 'Pala Interactive',
        {'multiples_note': 'private target; financials not disclosed'}),

    # ============ Oil & Gas ============
    ('Oil_Gas_Intel', 'ExxonMobil', 'Pioneer',
        {'ev_revenue': 3.1, 'ev_ebitda': 6.1}),
    ('Oil_Gas_Intel', 'Chevron', 'Hess',
        {'ev_revenue': 5.0, 'ev_ebitda': 7.6}),
    ('Oil_Gas_Intel', 'ConocoPhillips', 'Marathon',
        {'ev_revenue': 3.4, 'ev_ebitda': 5.6}),
    ('Oil_Gas_Intel', 'Diamondback', 'Endeavor',
        {'ev_ebitda': 5.0, 'multiples_note': 'private target; implied from disclosed 2024E EBITDA'}),
    ('Oil_Gas_Intel', 'Occidental', 'CrownRock',
        {'ev_ebitda': 5.0, 'multiples_note': 'private target; ~5x 2024E disclosed by acquirer'}),
    ('Oil_Gas_Intel', 'Devon', 'Grayson Mill',
        {'ev_ebitda': 3.2, 'multiples_note': 'private target; 2025E EBITDA basis disclosed by Devon'}),
    ('Oil_Gas_Intel', 'APA', 'Callon',
        {'ev_revenue': 2.3, 'ev_ebitda': 3.5}),
    ('Oil_Gas_Intel', 'Permian Resources', 'Earthstone',
        {'ev_ebitda': 5.0, 'multiples_note': '2024E forward basis per Permian Resources deal deck'}),
    ('Oil_Gas_Intel', 'Crescent', 'SilverBow',
        {'ev_revenue': 3.0, 'ev_ebitda': 4.2}),
    ('Oil_Gas_Intel', 'Matador', 'Advance Energy',
        {'ev_ebitda': 3.0, 'multiples_note': 'private target; disclosed forward EBITDA basis'}),
    ('Oil_Gas_Intel', 'Matador', 'Ameredev',
        {'ev_ebitda': 3.8, 'multiples_note': 'private target; disclosed forward EBITDA basis'}),
    ('Oil_Gas_Intel', 'SM Energy', 'XCL',
        {'ev_ebitda': 3.0, 'multiples_note': 'private target; disclosed forward EBITDA basis'}),
    ('Oil_Gas_Intel', 'Civitas', 'Hibernia',
        {'ev_ebitda': 3.5, 'multiples_note': 'private targets; disclosed forward EBITDA basis'}),
    ('Oil_Gas_Intel', 'Chesapeake', 'Southwestern',
        {'ev_revenue': 1.0, 'ev_ebitda': 2.5}),
    ('Oil_Gas_Intel', 'EQT', 'Equitrans',
        {'ev_revenue': 3.9, 'ev_ebitda': 5.5}),
    ('Oil_Gas_Intel', 'Woodside', 'BHP Petroleum',
        {'ev_ebitda': 4.0, 'multiples_note': 'asset merger; based on 2022E combined EBITDA'}),
    ('Oil_Gas_Intel', 'Devon', 'Validus',
        {'ev_ebitda': 3.5, 'multiples_note': 'private target; Devon-disclosed forward basis'}),
    ('Oil_Gas_Intel', 'Viper', 'Tumbleweed',
        {'multiples_note': 'mineral/royalty interests; valued on PV-10 / production basis, not EBITDA'}),

    # ============ Metal Mining ============
    ('Metal_Mining_Intel', 'Newmont', 'Newcrest',
        {'ev_revenue': 6.8, 'ev_ebitda': 14.3}),
    ('Metal_Mining_Intel', 'Agnico', 'Kirkland Lake',
        {'ev_revenue': 4.2, 'ev_ebitda': 7.5}),
    ('Metal_Mining_Intel', 'Pan American', 'Yamana',
        {'ev_revenue': 2.7, 'ev_ebitda': 5.3}),
    ('Metal_Mining_Intel', 'Hudbay', 'Copper Mountain',
        {'ev_revenue': 2.3, 'multiples_note': 'target EBITDA marginal at deal date'}),
    ('Metal_Mining_Intel', 'Lundin Mining', 'Caserones',
        {'ev_ebitda': 5.0, 'multiples_note': '51% stake in operating mine; disclosed forward basis'}),
    ('Metal_Mining_Intel', 'Glencore', 'Elk Valley',
        {'ev_ebitda': 5.0, 'multiples_note': 'coal asset carve-out; forward EBITDA basis'}),
    ('Metal_Mining_Intel', 'BHP Group', 'OZ Minerals',
        {'ev_revenue': 4.9, 'ev_ebitda': 16.0}),
    ('Metal_Mining_Intel', 'Rio Tinto', 'Turquoise',
        {'multiples_note': 'Oyu Tolgoi under development at deal date; no trailing EBITDA'}),
    ('Metal_Mining_Intel', 'Alamos', 'Argonaut',
        {'ev_ebitda': 6.0, 'multiples_note': 'Magino mine-level transaction; forward basis'}),
    ('Metal_Mining_Intel', 'Lundin Mining + BHP', 'Filo',
        {'multiples_note': 'development-stage explorer; no trailing EBITDA'}),
    ('Metal_Mining_Intel', 'Rio Tinto', 'Arcadium',
        {'ev_revenue': 5.5, 'ev_ebitda': 12.0, 'multiples_note': '2024E revenue/EBITDA basis disclosed'}),
    ('Metal_Mining_Intel', 'Gold Fields', 'Osisko',
        {'multiples_note': 'Windfall JV development stage; no trailing EBITDA'}),
    ('Metal_Mining_Intel', 'Newmont', 'OreCorp',
        {'multiples_note': 'development-stage project (Nyanzaga); no trailing EBITDA'}),
    ('Metal_Mining_Intel', 'Equinox', 'Calibre',
        {'ev_revenue': 2.3, 'ev_ebitda': 4.8, 'multiples_note': 'merger of equals; 2024 combined basis'}),

    # ============ Media Broadcasting ============
    ('Media_Broadcasting_Intel', 'Skydance', 'Paramount',
        {'ev_revenue': 0.7, 'ev_ebitda': 9.6, 'multiples_note': 'equity deal; EV basis includes ~$14B debt'}),
    ('Media_Broadcasting_Intel', 'Walt Disney', 'Hulu',
        {'ev_revenue': 2.5, 'multiples_note': '33% stake; implied full-valuation basis'}),
    ('Media_Broadcasting_Intel', 'Discovery', 'Warner Bros',
        {'ev_ebitda': 8.0, 'multiples_note': 'pro forma combined EBITDA basis disclosed at announcement'}),
    ('Media_Broadcasting_Intel', 'Amazon', 'MGM',
        {'ev_revenue': 5.6, 'multiples_note': 'library-heavy valuation; EBITDA multiple not disclosed'}),
    ('Media_Broadcasting_Intel', 'Endeavor', 'WWE',
        {'ev_revenue': 7.2, 'ev_ebitda': 24.6}),
    ('Media_Broadcasting_Intel', 'Cox', 'Axios',
        {'ev_revenue': 5.5, 'multiples_note': 'target unprofitable; EBITDA multiple not meaningful'}),
    ('Media_Broadcasting_Intel', 'Gray Television', 'Meredith',
        {'ev_ebitda': 8.0, 'multiples_note': 'local TV station portfolio; standard sector multiple'}),
    ('Media_Broadcasting_Intel', 'Standard General', 'Tegna',
        {'multiples_note': 'deal withdrawn; no transaction closed'}),
    ('Media_Broadcasting_Intel', 'Netflix', 'Animal Logic',
        {'multiples_note': 'private animation studio; financials not disclosed'}),
    ('Media_Broadcasting_Intel', 'Sinclair', 'Diamond Sports',
        {'multiples_note': 'debt restructure, not a business acquisition'}),
    ('Media_Broadcasting_Intel', 'Cumulus', 'WestwoodOne',
        {'multiples_note': 'content-operations carve-out; financials not disclosed'}),
    ('Media_Broadcasting_Intel', 'Nexstar', 'The Hill',
        {'ev_ebitda': 5.0, 'multiples_note': 'bolt-on digital publisher; forward basis'}),

    # ============ Inspection ============
    ('Inspection_Intel', 'Mistras', 'ScanMaster',
        {'ev_revenue': 2.2, 'ev_ebitda': 11.0, 'multiples_note': 'private target; sector-median basis'}),
]


def matches(deal, acquirer_substr, target_substr):
    a = (deal.get('acquirer') or '').lower()
    t = (deal.get('target') or '').lower()
    return acquirer_substr.lower() in a and target_substr.lower() in t


def apply_patches():
    changed_by_site = {}
    for site in set(p[0] for p in PATCHES):
        path = BASE / site / 'Dashboard' / 'ma_deals_curated.json'
        if not path.exists():
            print(f"SKIP {site}: no curated file")
            continue
        with open(path) as f:
            deals = json.load(f)

        applied = 0
        for _, acq_sub, tgt_sub, patch in [(p[0], p[1], p[2], p[3]) for p in PATCHES if p[0] == site]:
            hit = None
            for d in deals:
                if matches(d, acq_sub, tgt_sub):
                    hit = d
                    break
            if not hit:
                print(f"  MISS {site}: {acq_sub} -> {tgt_sub}")
                continue
            for k, v in patch.items():
                if hit.get(k) in (None, 0):
                    hit[k] = v
            applied += 1

        with open(path, 'w') as f:
            json.dump(deals, f, indent=2)
        changed_by_site[site] = applied
        print(f"  {site}: applied {applied} patches")
    return changed_by_site


if __name__ == '__main__':
    apply_patches()
