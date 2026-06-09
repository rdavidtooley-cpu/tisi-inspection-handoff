---
name: Info icon tooltip positioning rules
description: Info icons must use position:fixed tooltips positioned via JS; never position:absolute with pseudo-elements (that pattern clips inside overflow containers)
type: feedback
---

**Canonical pattern (2026-04-16, replaces all prior patterns):** info-icon tooltips must use `position:fixed` on the popup with JavaScript positioning via `getBoundingClientRect()`. The older `.info-icon[data-tip]:hover::after { position:absolute; ... }` pseudo-element pattern is BROKEN — it gets clipped inside overflow containers (scrollable tables, sticky headers, tab panes) and can make the icon appear visually detached from the text it describes.

**Correct CSS:**
```css
.info-icon { position:relative; cursor:help; font-size:14px; color:var(--accent); opacity:1; display:inline-block; }
.info-icon:hover { color:#fbbf24; }
.info-tooltip { display:none; position:fixed; z-index:99999; width:360px; max-width:90vw; background:#1e2130; border:1px solid rgba(245,158,11,0.25); border-radius:10px; padding:16px 18px; font-size:11.5px; line-height:1.55; color:#d0d0d0; box-shadow:0 8px 32px rgba(0,0,0,0.5); pointer-events:none; }
```

**Correct JS** (inject once before `</body>`, idempotent):
```js
(function(){
  if (window.__infoIconTipInit) return;
  window.__infoIconTipInit = true;
  function initInfoTooltips() {
    var tooltip = document.createElement('div');
    tooltip.className = 'info-tooltip';
    document.body.appendChild(tooltip);
    document.addEventListener('mouseover', function(e) {
      var icon = e.target.closest('.info-icon[data-tip]'); if (!icon) return;
      tooltip.textContent = icon.getAttribute('data-tip');
      tooltip.style.display = 'block';
      var rect = icon.getBoundingClientRect();
      var tw = tooltip.offsetWidth || 360, th = tooltip.offsetHeight || 120;
      var left = rect.right + 10, top = rect.top - 10;
      if (left + tw > window.innerWidth - 16) left = rect.left - tw - 10;
      if (left < 16) left = Math.max(16, (window.innerWidth - tw) / 2);
      if (top + th > window.innerHeight - 16) top = window.innerHeight - th - 16;
      if (top < 16) top = 16;
      tooltip.style.left = left + 'px'; tooltip.style.top = top + 'px';
    });
    document.addEventListener('mouseout', function(e) {
      if (!e.target.closest('.info-icon[data-tip]')) return;
      tooltip.style.display = 'none';
    });
    document.addEventListener('scroll', function(){ tooltip.style.display = 'none'; }, true);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initInfoTooltips);
  else initInfoTooltips();
})();
```

**Why:** the pseudo-element pattern (`::after`) is constrained to its positioned ancestor box. Inside a table with `overflow-x:auto` or a tab pane, the tooltip gets clipped. `position:fixed` renders the tooltip in viewport coordinates so no ancestor can clip it.

**How to apply:**
- Keep markup as `<span class="info-icon" data-tip="...">&#9432;</span>` — the JS handler reads `data-tip`.
- Icons must stay inline next to their label (never float:right the parent, never put the icon in a separate container).
- Opacity must always be 1 — users cannot find icons they cannot see.
- Use `z-index:99999` so popups sit above sticky headers and modal-like panels.
- Migration tool for any codebase of dashboards: copy the logic from `${PROJECT_ROOT}/_shared/fix_info_tooltips.py`.

**Applies broadly:** any HTML dashboard or data-heavy web UI with info icons inside scrollable containers, tab panes, or sticky headers — not just Intel sites.
