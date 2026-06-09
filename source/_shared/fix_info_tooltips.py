#!/usr/bin/env python3
"""
One-time migration: apply the position:fixed + JS info-icon tooltip pattern
to all dashboard HTML files that still have the broken ::after/::before pattern
or are simply missing the tooltip behavior entirely.

Reference implementation: Metal_Mining_Intel/Dashboard/equities_template.html
- .info-tooltip CSS (position:fixed)
- initInfoTooltips() JS function (reads data-tip, uses getBoundingClientRect)

Usage:
    python3 fix_info_tooltips.py            # dry-run, prints intended changes
    python3 fix_info_tooltips.py --apply    # writes changes

Per-file logic:
    1. If file has no `class="info-icon"`, skip.
    2. If file already has `initInfoTooltips(`, skip (already fixed).
    3. Strip any `.info-icon[data-tip]:hover::after { ... }` and
       `.info-icon[data-tip]:hover::before { ... }` rules (broken pattern).
    4. Insert canonical `.info-tooltip` CSS rule inside the existing <style> block,
       immediately after `.info-icon:hover { ... }` (or at end of style if not found).
    5. Insert the canonical JS block (initInfoTooltips function + auto-call on DOMContentLoaded)
       just before </body>.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Canonical CSS rule (single line, matches Metal Mining pattern)
CANONICAL_CSS = (
    ".info-tooltip { display:none; position:fixed; z-index:99999; width:360px; "
    "max-width:90vw; background:#1e2130; border:1px solid rgba(245,158,11,0.25); "
    "border-radius:10px; padding:16px 18px; font-size:11.5px; line-height:1.55; "
    "color:#d0d0d0; box-shadow:0 8px 32px rgba(0,0,0,0.5); pointer-events:none; }"
)

# Canonical JS block (auto-initialises on DOMContentLoaded, idempotent)
CANONICAL_JS = """<script>
/* Info-icon tooltip — position:fixed so overflow containers cannot clip */
(function(){
  if (window.__infoIconTipInit) return;
  window.__infoIconTipInit = true;
  function initInfoTooltips() {
    if (document.querySelector('.info-tooltip[data-global="1"]')) return;
    var tooltip = document.createElement('div');
    tooltip.className = 'info-tooltip';
    tooltip.setAttribute('data-global', '1');
    document.body.appendChild(tooltip);
    function showTip(e) {
      var icon = e.target.closest('.info-icon[data-tip]');
      if (!icon) return;
      var tip = icon.getAttribute('data-tip');
      if (!tip) return;
      tooltip.textContent = tip;
      tooltip.style.display = 'block';
      var rect = icon.getBoundingClientRect();
      var tw = tooltip.offsetWidth || 360;
      var th = tooltip.offsetHeight || 120;
      var left = rect.right + 10;
      var top = rect.top - 10;
      if (left + tw > window.innerWidth - 16) left = rect.left - tw - 10;
      if (left < 16) left = Math.max(16, (window.innerWidth - tw) / 2);
      if (top + th > window.innerHeight - 16) top = window.innerHeight - th - 16;
      if (top < 16) top = 16;
      tooltip.style.left = left + 'px';
      tooltip.style.top = top + 'px';
    }
    function hideTip(e) {
      if (!e.target.closest('.info-icon[data-tip]')) return;
      tooltip.style.display = 'none';
    }
    document.addEventListener('mouseover', showTip);
    document.addEventListener('mouseout', hideTip);
    document.addEventListener('scroll', function(){ tooltip.style.display = 'none'; }, true);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initInfoTooltips);
  } else {
    initInfoTooltips();
  }
})();
</script>"""


def find_target_files():
    targets = []
    for site in [
        "Casino_Gaming_Intel",
        "Oil_Gas_Intel",
        "Metal_Mining_Intel",
        "Inspection_Intel",
        "Media_Broadcasting_Intel",
    ]:
        dash_dir = os.path.join(ROOT, site, "Dashboard")
        if not os.path.isdir(dash_dir):
            continue
        for name in os.listdir(dash_dir):
            if not name.endswith(".html"):
                continue
            path = os.path.join(dash_dir, name)
            try:
                content = open(path, "r", encoding="utf-8").read()
            except Exception:
                continue
            if 'class="info-icon"' not in content:
                continue
            # Skip only if file is fully clean (no broken rules remaining).
            fully_clean = (
                "initInfoTooltips(" in content
                and ":hover::after" not in content.replace(".kpi-label[data-tip]:hover::after", "")
                .replace(".kpi-value[data-tip]:hover::after", "")
            )
            if fully_clean:
                continue
            targets.append(path)
    return targets


def transform(content: str) -> (str, dict):
    stats = {"removed_after": 0, "removed_before": 0, "css_added": False, "js_added": False}

    # 1. Strip broken pseudo-element rules. These are one-line rules like:
    # .info-icon[data-tip]:hover::after { content:... }
    # Regex matches the full line from '.info-icon[data-tip]:hover::after' through its closing brace.
    pat_after = re.compile(
        r"[ \t]*\.info-icon\[data-tip\]:hover::after\s*\{[^}]*\}\s*\n?",
        re.MULTILINE,
    )
    pat_before = re.compile(
        r"[ \t]*\.info-icon\[data-tip\]:hover::before\s*\{[^}]*\}\s*\n?",
        re.MULTILINE,
    )
    new_content, n1 = pat_after.subn("", content)
    stats["removed_after"] = n1
    new_content, n2 = pat_before.subn("", new_content)
    stats["removed_before"] = n2

    # 2. Insert canonical CSS right after `.info-icon:hover { ... }` rule if not present.
    if ".info-tooltip" not in new_content or "display:none; position:fixed" not in new_content:
        insert_marker_re = re.compile(
            r"(\.info-icon:hover\s*\{[^}]*\}\s*\n)", re.MULTILINE
        )
        m = insert_marker_re.search(new_content)
        if m:
            insertion = m.group(1) + CANONICAL_CSS + "\n"
            new_content = (
                new_content[: m.start()] + insertion + new_content[m.end():]
            )
            stats["css_added"] = True
        else:
            # Fallback: insert before closing </style>
            m = re.search(r"</style>", new_content)
            if m:
                new_content = (
                    new_content[: m.start()]
                    + CANONICAL_CSS
                    + "\n"
                    + new_content[m.start():]
                )
                stats["css_added"] = True

    # 3. Insert canonical JS just before </body> (only if not already present)
    if "__infoIconTipInit" not in new_content:
        m = re.search(r"</body>", new_content)
        if m:
            new_content = (
                new_content[: m.start()]
                + CANONICAL_JS
                + "\n"
                + new_content[m.start():]
            )
            stats["js_added"] = True

    return new_content, stats


def main():
    apply = "--apply" in sys.argv
    files = find_target_files()
    print(f"Found {len(files)} target files.\n")
    for path in files:
        original = open(path, "r", encoding="utf-8").read()
        updated, stats = transform(original)
        rel = os.path.relpath(path, ROOT)
        print(
            f"{'APPLY' if apply else 'DRY  '} {rel}\n"
            f"   removed ::after={stats['removed_after']}  ::before={stats['removed_before']}  "
            f"css_added={stats['css_added']}  js_added={stats['js_added']}"
        )
        if apply and updated != original:
            open(path, "w", encoding="utf-8").write(updated)
    print(f"\nDone. {'APPLIED' if apply else 'DRY RUN (use --apply to write changes)'}")


if __name__ == "__main__":
    main()
