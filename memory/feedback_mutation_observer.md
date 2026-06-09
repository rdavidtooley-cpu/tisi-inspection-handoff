---
name: MutationObserver must disconnect before writing to DOM it observes
description: Any MutationObserver that mutates the observed DOM must disconnect during writes and reconnect after, or it infinite-loops and freezes the browser
type: feedback
originSessionId: 464c19e0-6b02-4a2b-9dd7-a26a979ae0a0
---
Any MutationObserver that writes to the DOM it observes MUST disconnect before each write and reconnect after, or it will infinite-loop and freeze the renderer.

**Why:** On 2026-04-21, all 14 sector Intel dashboards froze Chrome renderers after load with no console errors. Root cause: `csv_export.js` observed `document.body` with `subtree: true`, and its callback wrote to the DOM (`dataset.csvxAttached`, inserted `<button>` elements, rewrote `btn.textContent`) unconditionally. Each write re-fired the observer, which wrote again — tight infinite loop that pegged the main thread, blocked paint, blocked `/api/auth/validate` fetch processing, and made pages appear "stuck loading with no data." Took hours to isolate because console stayed empty. Users experienced it as "page unresponsive" browser prompts.

**How to apply:** When writing or auditing any JS that uses `MutationObserver`:
- Wrap all DOM writes inside `mo.disconnect() ... mo.observe(...)` 
- Debounce bursts with `requestIdleCallback` or `setTimeout` and a `scheduled` flag
- Narrow scope: prefer `subtree: false`; observe the smallest container that catches the work
- Short-circuit mutations whose targets are the observer's own injected elements (check `id`/`classList`)
- Compare values before assignment: `if (btn.textContent !== newText) btn.textContent = newText`
- Never update a button's text/attributes on every fire "just in case"

Applies to `csv_export.js` and any shared utility shipped to all 14 Intel sites.
