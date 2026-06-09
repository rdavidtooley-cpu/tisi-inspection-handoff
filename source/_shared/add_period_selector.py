#!/usr/bin/env python3
"""
Add financial period selector to equities dashboards (templates + live files).

Applies three idempotent transformations per file:
  1. Inject `var FINANCIALS_HISTORY = {};` into the INJECTED_DATA block.
  2. Inject a period <select> + label into the Financials tab filter-row.
  3. Append helper JS (populateFinPeriodSelect, getFinPeriodRow, applyFinancialsPeriod)
     and wrap existing renderFinancials() to use the selected period.

Does nothing to files that already have `populateFinPeriodSelect(` (already migrated).

Usage:
    python3 add_period_selector.py            # dry run
    python3 add_period_selector.py --apply    # write changes
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TARGETS = [
    # Oil & Gas
    ("Oil_Gas_Intel/Dashboard/equities_template.html", "OG_Company_Summary.html"),
    ("Oil_Gas_Intel/Dashboard/OG_Equities_Dashboard.html", "OG_Company_Summary.html"),
    # Metal Mining
    ("Metal_Mining_Intel/Dashboard/equities_template.html", "MM_Company_Summary.html"),
    ("Metal_Mining_Intel/Dashboard/MM_Equities_Dashboard.html", "MM_Company_Summary.html"),
    # Note: Inspection uses charts-only Financials tab (no filter row) and Media Broadcasting
    # has no Financials tab. Handle those separately.
]

PERIOD_SELECTOR_HTML = """<label>Period:</label>
                <select class="filter-select" id="finPeriodSelect" onchange="renderFinancials()">
                    <option value="ttm">Most Recent (TTM)</option>
                </select>
                <span style="color:var(--text-secondary);font-size:12px;">Showing: <strong id="finPeriodLabel" style="color:var(--accent);">TTM</strong></span>
                <label style="margin-left:16px;">"""

HELPER_JS = """
/* === Financials period selector helpers (inserted by add_period_selector.py) === */
function populateFinPeriodSelect() {
    var sel = document.getElementById('finPeriodSelect');
    if (!sel || sel.dataset.populated === '1') return;
    var periodsSet = {};
    var fh = (typeof FINANCIALS_HISTORY === 'object' && FINANCIALS_HISTORY) ? FINANCIALS_HISTORY : {};
    Object.keys(fh).forEach(function(t) {
        var th = fh[t] || {};
        (th.quarterly || []).forEach(function(r) { if (r && r.period) periodsSet['Q|' + r.period] = r.period; });
        (th.annual || []).forEach(function(r) { if (r && r.period) periodsSet['A|' + r.period] = r.period; });
    });
    var qKeys = Object.keys(periodsSet).filter(function(k){ return k.charAt(0) === 'Q'; }).sort().reverse();
    var aKeys = Object.keys(periodsSet).filter(function(k){ return k.charAt(0) === 'A'; }).sort().reverse();
    var html = '<option value="ttm">Most Recent (TTM)</option>';
    if (qKeys.length) {
        html += '<optgroup label="Quarterly">';
        qKeys.forEach(function(k){ var p=periodsSet[k]; html += '<option value="Q:'+p+'">'+p+'</option>'; });
        html += '</optgroup>';
    }
    if (aKeys.length) {
        html += '<optgroup label="Annual">';
        aKeys.forEach(function(k){ var p=periodsSet[k]; html += '<option value="A:'+p+'">FY '+p+'</option>'; });
        html += '</optgroup>';
    }
    sel.innerHTML = html;
    sel.dataset.populated = '1';
}
function getFinPeriodRow(ticker, periodKey) {
    var fh = (typeof FINANCIALS_HISTORY === 'object' && FINANCIALS_HISTORY) ? FINANCIALS_HISTORY : {};
    var th = fh[ticker]; if (!th) return null;
    var kind = periodKey.charAt(0) === 'Q' ? 'quarterly' : 'annual';
    var bsKind = periodKey.charAt(0) === 'Q' ? 'balance_sheet_quarterly' : 'balance_sheet_annual';
    var period = periodKey.split(':')[1];
    var incomeRow = (th[kind] || []).filter(function(r){ return r && r.period === period; })[0];
    var bsRow = (th[bsKind] || []).filter(function(r){ return r && r.period === period; })[0];
    if (!incomeRow && !bsRow) return null;
    var merged = {};
    if (incomeRow) Object.keys(incomeRow).forEach(function(k){ merged[k] = incomeRow[k]; });
    if (bsRow) Object.keys(bsRow).forEach(function(k){ if (merged[k] === undefined) merged[k] = bsRow[k]; });
    return merged;
}
/* Override financial fields on each ticker row with historical-period values if selected. */
function applyFinancialsPeriod(rows) {
    populateFinPeriodSelect();
    var sel = document.getElementById('finPeriodSelect');
    var periodKey = sel ? sel.value : 'ttm';
    var lbl = document.getElementById('finPeriodLabel');
    if (lbl) {
        lbl.textContent = periodKey === 'ttm' ? 'TTM'
                        : periodKey.charAt(0) === 'Q' ? periodKey.split(':')[1]
                        : 'FY ' + periodKey.split(':')[1];
    }
    if (periodKey === 'ttm') return rows;
    return rows.map(function(d) {
        var h = getFinPeriodRow(d.ticker, periodKey);
        if (!h) {
            var blank = {};
            Object.keys(d).forEach(function(k){ blank[k] = d[k]; });
            blank._period_missing = true;
            blank.revenue = null; blank.ebitda = null; blank.net_income = null;
            blank.total_debt = null; blank.ebitda_margin = null;
            blank.debt_ebitda = null; blank.interest_coverage = null; blank.roe = null;
            return blank;
        }
        var out = {};
        Object.keys(d).forEach(function(k){ out[k] = d[k]; });
        out.revenue = h.revenue != null ? h.revenue : null;
        out.ebitda = h.ebitda != null ? h.ebitda : null;
        out.net_income = h.net_income != null ? h.net_income : null;
        out.total_debt = h.total_debt != null ? h.total_debt : null;
        out.ebitda_margin = (h.revenue && h.ebitda) ? (h.ebitda / h.revenue) : null;
        out.debt_ebitda = (h.ebitda && h.total_debt) ? (h.total_debt / h.ebitda) : null;
        out.interest_coverage = (h.ebitda && h.interest_expense) ? (h.ebitda / Math.abs(h.interest_expense)) : null;
        return out;
    });
}
/* ============================================================= */
"""


def inject_financials_history_var(content: str) -> (str, bool):
    """Insert `var FINANCIALS_HISTORY = {};` before INJECTED_DATA_END if not present."""
    if "FINANCIALS_HISTORY" in content:
        return content, False
    # Find INJECTED_DATA_END
    m = re.search(r"//\s*INJECTED_DATA_END", content)
    if not m:
        return content, False
    # Insert before
    insertion = "var FINANCIALS_HISTORY = {};\n"
    return content[: m.start()] + insertion + content[m.start():], True


def inject_period_selector_html(content: str) -> (str, bool):
    """Inject period <select> before the Search label in Financials filter-row."""
    if 'id="finPeriodSelect"' in content:
        return content, False
    # Find the filter-row that contains id="finSearch" AND id="finSectorFilter"
    # Locate <label>Search:</label> near finSearch input and replace with period selector + original label
    # We need to do this only in the Financials filter-row, not other tabs. The Financials filter-row
    # has id="finSearch" nearby.
    pat = re.compile(
        r'(<div class="filter-row">\s*)<label>Search:</label>\s*(<input[^>]*id="finSearch"[^>]*>)',
        re.MULTILINE,
    )
    m = pat.search(content)
    if not m:
        return content, False
    replacement = (
        m.group(1)
        + PERIOD_SELECTOR_HTML
        + "Search:</label>\n                "
        + m.group(2)
    )
    return content[: m.start()] + replacement + content[m.end():], True


def inject_helper_js(content: str) -> (str, bool):
    """Insert helper JS + wrap renderFinancials.

    Approach: append HELPER_JS just before </script> that contains `function renderFinancials(`,
    AND modify renderFinancials body to call applyFinancialsPeriod on the data array.
    """
    if "populateFinPeriodSelect" in content:
        return content, False

    # Find the renderFinancials() function definition
    func_pat = re.compile(r"function renderFinancials\(\)\s*\{", re.MULTILINE)
    m = func_pat.search(content)
    if not m:
        return content, False

    # Insert HELPER_JS immediately before the function definition
    new_content = content[: m.start()] + HELPER_JS + "\n" + content[m.start():]

    # Now patch the function body to apply period override on data.
    # The common pattern is: `var data = filterData(getDataArray(), 'finSearch', 'finSectorFilter');`
    # or `var data = getDataArray();` followed by filtering.
    # Wrap the data assignment with applyFinancialsPeriod(...).
    new_content = re.sub(
        r"(function renderFinancials\(\)\s*\{\s*\n)(\s*)var data = ([^;]+);",
        r"\1\2var data = applyFinancialsPeriod(\3);",
        new_content,
        count=1,
    )
    return new_content, True


def process_file(path: str, apply: bool):
    content = open(path, "r", encoding="utf-8").read()
    original = content
    c1, did1 = inject_financials_history_var(content)
    c2, did2 = inject_period_selector_html(c1)
    c3, did3 = inject_helper_js(c2)
    rel = os.path.relpath(path, ROOT)
    print(f"{'APPLY' if apply else 'DRY  '} {rel}")
    print(f"    var_added={did1}  select_html_added={did2}  helper_js_added={did3}")
    if apply and c3 != original:
        open(path, "w", encoding="utf-8").write(c3)


def main():
    apply = "--apply" in sys.argv
    for rel, _summary_file in TARGETS:
        full = os.path.join(ROOT, rel)
        if not os.path.isfile(full):
            print(f"SKIP (missing): {rel}")
            continue
        process_file(full, apply)
    print("\nDone." + ("" if apply else " DRY RUN — run with --apply to write."))


if __name__ == "__main__":
    main()
