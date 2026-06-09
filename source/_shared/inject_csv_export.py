#!/usr/bin/env python3
"""Inject <script src="csv_export.js"> into every dashboard HTML file.

Idempotent: skips files that already have the tag. Touches both template and
live files so the nightly rebuild doesn't strip the tag.
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SITES = [
    'Casino_Gaming_Intel',
    'Oil_Gas_Intel',
    'Metal_Mining_Intel',
    'Media_Broadcasting_Intel',
    'Inspection_Intel',
]

TAG = '<script src="csv_export.js" defer></script>'
MARKER = 'csv_export.js'


def inject(path: Path) -> str:
    html = path.read_text()
    if MARKER in html:
        return 'skip (already has tag)'
    if '</body>' in html:
        new_html = html.replace('</body>', f'  {TAG}\n</body>', 1)
    elif '</html>' in html:
        new_html = html.replace('</html>', f'{TAG}\n</html>', 1)
    else:
        new_html = html + '\n' + TAG + '\n'
    path.write_text(new_html)
    return 'injected'


def main():
    total = 0
    injected = 0
    skipped = 0
    for site in SITES:
        dash = BASE / site / 'Dashboard'
        if not dash.exists():
            print(f'{site}: missing Dashboard/')
            continue
        print(f'\n{site}')
        for p in sorted(dash.glob('*.html')):
            total += 1
            status = inject(p)
            if status.startswith('injected'):
                injected += 1
            else:
                skipped += 1
            print(f'  {p.name:45} {status}')
    print(f'\nTotal: {total}  injected: {injected}  skipped: {skipped}')


if __name__ == '__main__':
    main()
