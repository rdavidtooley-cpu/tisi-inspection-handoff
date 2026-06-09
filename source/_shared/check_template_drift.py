#!/usr/bin/env python3
"""
check_template_drift.py — pre-deploy guardrail for the template→live drift bug.

PROBLEM: Every Intel sector site has *_template.html files. The morning refresh
script does `shutil.copy2(template, live)` and then injects market data into the
live file. If a developer (or AI) hand-edits the live file without also patching
the template, the next morning's pipeline silently overwrites the fix.

SOLUTION: Before deploying, run this. It compares each template to its
corresponding live file, ignoring the data-injection blocks (`var X = {...};`
that legitimately differ post-refresh). If anything ELSE differs — JS handlers,
HTML structure, nav links, tooltips, CSS — that's drift, and the live file or
the template is out of sync.

USAGE:
    python3 _shared/check_template_drift.py                  # check all sites
    python3 _shared/check_template_drift.py Inspection_Intel # check one site
    python3 _shared/check_template_drift.py --diff           # show full diff
    python3 _shared/check_template_drift.py --fail-on-drift  # exit 1 on drift

Exit codes:
    0 — no drift detected (or drift only in data blocks)
    1 — structural drift detected (with --fail-on-drift)
"""

from __future__ import annotations
import argparse
import difflib
import pathlib
import re
import sys

# ──────────────────────────────────────────────────────────────────────
# Template → live mapping by category keyword.
# Each template name stem maps to a list of substring matchers used to
# find the live counterpart in the same directory.
# ──────────────────────────────────────────────────────────────────────
TEMPLATE_TO_LIVE = {
    "earnings_template.html":         ["Earnings_Dashboard"],
    "equities_template.html":         ["Equities_Dashboard", "Equities"],
    "industry_template.html":         ["Industry_Dashboard", "Industry_Overview"],
    "news_template.html":             ["News_Dashboard"],
    "ma_template.html":               ["MA_Dashboard", "M_A_Dashboard"],
    "peer_analysis_template.html":    ["Peer_Analysis_Dashboard", "Peer_Analysis"],
    "company_summary_template.html":  ["Company_Summary", "Company_Dashboard"],
    "index_template.html":            ["index.html"],
    "market_template.html":           ["Market_Dashboard", "Market"],
    # dashboard_template.html — legacy scaffold blueprint, not 1:1 with any
    # live file. Excluded to avoid noise.
}

# Match the LHS of an injected-data assignment. The RHS (the literal { ... }
# or [ ... ] which can be megabytes of JSON with arbitrary nesting) is walked
# character-by-character — regex can't reliably handle balanced braces.
DATA_LHS_RE = re.compile(
    r"\b(?:var|let|const|window\.)\s+[A-Z_][A-Za-z0-9_]*\s*=\s*",
)


def _walk_balanced(text: str, start: int) -> int:
    """Given text[start] is '{' or '[', return index just past the matching
    closer, or -1 if unbalanced. Handles strings and escapes properly."""
    open_ch = text[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    i = start
    n = len(text)
    in_str = None  # current string delimiter or None
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c in ('"', "'", "`"):
            in_str = c
            i += 1
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


# Some templates use literal string placeholders the refresh script swaps in
# (rather than empty `{}` placeholders). Match `= __FOO_BAR__;`.
PLACEHOLDER_TOKEN_RE = re.compile(
    r"(\b(?:var|let|const|window\.)\s+[A-Z_][A-Za-z0-9_]*\s*=\s*)"
    r"(__[A-Z][A-Z0-9_]*__)"
    r"(\s*;)",
)


def normalize(text: str) -> str:
    """Replace each data-injection RHS with `<DATA>` so structural diffs
    ignore the bits that legitimately differ post-refresh."""
    # Pass 1: object/array literals (any size — convention is uppercase data vars)
    out_parts = []
    last = 0
    for m in DATA_LHS_RE.finditer(text):
        rhs_start = m.end()
        if rhs_start >= len(text) or text[rhs_start] not in "{[":
            continue
        end = _walk_balanced(text, rhs_start)
        if end < 0:
            continue
        out_parts.append(text[last:rhs_start])
        out_parts.append("<DATA>")
        last = end
    out_parts.append(text[last:])
    out = "".join(out_parts)
    # Pass 2: __PLACEHOLDER_TOKEN__ style
    out = PLACEHOLDER_TOKEN_RE.sub(lambda m: f"{m.group(1)}<DATA>{m.group(3)}", out)
    # Pass 3: refresh scripts sometimes preserve original indentation when injecting,
    # so the live file's `var X = <DATA>;` line may have different leading whitespace
    # than the template's. Normalize indentation on lines that contain only injected
    # data + adjacent INJECTED_DATA marker lines.
    lines = out.splitlines()
    normalized = []
    for line in lines:
        stripped = line.lstrip()
        if (
            "<DATA>" in line
            or stripped.startswith("// INJECTED_DATA_START")
            or stripped.startswith("// INJECTED_DATA_END")
        ):
            normalized.append(stripped.rstrip())
        else:
            normalized.append(line.rstrip())
    return "\n".join(normalized)


# Canonical site prefix per *_Intel directory. Used to disambiguate when a
# directory holds both a legacy file (`Casino_*.html`) and the current one
# (`CG_*.html`). The current/live file always uses the prefix below.
SITE_PREFIX = {
    "Aerospace_Defense_Intel": "AD_",
    "Autos_Intel": "AUTO_",
    "Casino_Gaming_Intel": "CG_",
    "Chemicals_Intel": "CHM_",
    "Homebuilders_Intel": "HOME_",
    "Inspection_Intel": "TIC_NDT_",
    "Media_Broadcasting_Intel": "MB_",
    "Metal_Mining_Intel": "MM_",
    "Oil_Gas_Intel": "OG_",
    "Power_Utilities_Intel": "PU_",
    "REITs_Intel": "REIT_",
    "Rail_Logistics_Intel": "RL_",
    "Semiconductors_Intel": "SEMI_",
    "Shipping_Intel": "SHP_",
}


def template_is_pipeline_source(template: pathlib.Path) -> bool:
    """A template is a pipeline source iff its name appears in any of the
    site's refresh / build scripts. Some sites put scripts in `_scripts/`
    (most), others in `Dashboard/` itself (Oil_Gas). If no script references
    the template (e.g. Media_Broadcasting writes JSON only), the templates
    are orphaned scaffolding and drift against them is a false alarm."""
    site_root = template.parent.parent
    name = template.name
    search_dirs = [site_root / "_scripts", site_root / "Dashboard"]
    for d in search_dirs:
        if not d.is_dir():
            continue
        for py in d.glob("*.py"):
            try:
                if name in py.read_text(errors="ignore"):
                    return True
            except Exception:
                continue
    return False


def find_live_for_template(template: pathlib.Path) -> pathlib.Path | None:
    """Find the live HTML file that this template populates."""
    name = template.name
    matchers = TEMPLATE_TO_LIVE.get(name, [])
    if not matchers:
        return None
    site_name = template.parent.parent.name
    site_prefix = SITE_PREFIX.get(site_name)
    candidates = [
        f for f in template.parent.glob("*.html")
        if f.name != name
        and "template" not in f.name.lower()
        and f.name != "login.html"
    ]
    if name == "index_template.html":
        idx = template.parent / "index.html"
        return idx if idx.exists() else None
    # Pass 1: prefer files matching the canonical site prefix
    prefixed = [c for c in candidates if site_prefix and c.name.startswith(site_prefix)]
    for matcher in matchers:
        m_norm = matcher.lower().replace("&", "_a_").replace("-", "_")
        for c in prefixed:
            c_norm = c.name.lower().replace("&", "_a_").replace("-", "_")
            if m_norm in c_norm:
                return c
    # Pass 2: fall back to any candidate
    for matcher in matchers:
        m_norm = matcher.lower().replace("&", "_a_").replace("-", "_")
        for c in candidates:
            c_norm = c.name.lower().replace("&", "_a_").replace("-", "_")
            if m_norm in c_norm:
                return c
    return None


def compare(template: pathlib.Path, live: pathlib.Path, show_diff: bool):
    t = normalize(template.read_text(errors="ignore"))
    l = normalize(live.read_text(errors="ignore"))
    if t == l:
        return None  # no drift
    diff = list(difflib.unified_diff(
        t.splitlines(),
        l.splitlines(),
        fromfile=str(template),
        tofile=str(live),
        n=2,
        lineterm="",
    ))
    drift_lines = [d for d in diff if d.startswith(("+", "-")) and not d.startswith(("+++", "---"))]
    if show_diff:
        print("\n".join(diff[:120]))
        if len(diff) > 120:
            print(f"\n  ... ({len(diff)-120} more diff lines suppressed; rerun with --diff-full)")
    return len(drift_lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("site", nargs="?", help="Limit to one site (e.g. Inspection_Intel). Default: all sites.")
    ap.add_argument("--diff", action="store_true", help="Show structural diff for each drifting pair.")
    ap.add_argument("--fail-on-drift", action="store_true", help="Exit 1 if any structural drift found.")
    args = ap.parse_args()

    root = pathlib.Path(__file__).resolve().parent.parent
    site_dirs = (
        [root / args.site / "Dashboard"]
        if args.site
        else sorted(root.glob("*_Intel/Dashboard"))
    )

    total_pairs = 0
    drifted = []
    unmapped = []
    orphaned = []

    for site in site_dirs:
        if not site.is_dir():
            continue
        site_name = site.parent.name
        for tmpl in sorted(site.glob("*_template.html")):
            if not template_is_pipeline_source(tmpl):
                orphaned.append(tmpl)
                continue
            live = find_live_for_template(tmpl)
            if not live:
                unmapped.append(tmpl)
                continue
            total_pairs += 1
            drift_count = compare(tmpl, live, args.diff)
            if drift_count:
                drifted.append((site_name, tmpl.name, live.name, drift_count))
                print(f"⚠️  DRIFT  {site_name}: {tmpl.name} ↔ {live.name}  ({drift_count} differing lines)")
            else:
                print(f"✓ clean  {site_name}: {tmpl.name} ↔ {live.name}")

    print()
    print(f"Pairs checked: {total_pairs}")
    print(f"Drift found:   {len(drifted)}")
    if unmapped:
        print(f"Unmapped templates (no live file matched): {len(unmapped)}")
        for u in unmapped:
            print(f"  - {u.relative_to(root)}")
    if orphaned:
        print(f"Orphaned templates (refresh scripts don't reference them — drift is harmless): {len(orphaned)}")
        for o in orphaned:
            print(f"  - {o.relative_to(root)}")
    if drifted:
        print()
        print("REMEDIATION:")
        print("  Drift means the template and live file disagree on JS/HTML structure.")
        print("  Either (a) the live file has an unfixed bug that the next refresh will reintroduce")
        print("    → patch the template to match the live file, OR")
        print("  (b) the template has a fix the live file lost in a manual edit")
        print("    → re-apply the template's content to the live file (or just re-run refresh).")
        print("  Use --diff to inspect.")
        if args.fail_on_drift:
            sys.exit(1)


if __name__ == "__main__":
    main()
