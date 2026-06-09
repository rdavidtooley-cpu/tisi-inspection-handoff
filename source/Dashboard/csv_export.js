// Shared CSV Export Utility — Sector Intelligence Dashboards
// Auto-scans every <table> on the page that has a <thead> and <tbody>,
// injects a per-table "Export CSV" button, and a page-level "Download All (ZIP)" button.
//
// Loaded on every dashboard page via <script src="csv_export.js" defer></script>.
// Uses JSZip (loaded lazily from CDN) for the master ZIP download.

(function () {
  'use strict';

  var DISCLAIMER = 'DISCLAIMER: The information provided is for informational and educational purposes only and does not constitute investment advice, financial advice, legal advice, or any other form of professional advice. No representation or warranty is made regarding the accuracy, completeness, or reliability of any information presented. Always consult a qualified professional before making any investment or financial decisions.';

  var JSZIP_CDN = 'https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js';

  // ===== CSS =====
  function injectStyles() {
    if (document.getElementById('csvx-styles')) return;
    var css = [
      '.csvx-btn{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;font-size:11px;font-weight:600;',
      'color:#fff;background:#0ea5e9;border:none;border-radius:4px;cursor:pointer;margin-left:8px;',
      'font-family:inherit;letter-spacing:.02em;transition:background .15s;}',
      '.csvx-btn:hover{background:#0284c7;}',
      '.csvx-btn.csvx-master{position:fixed;bottom:14px;right:14px;z-index:9999;',
      'width:30px;height:30px;padding:0;border-radius:50%;font-size:14px;line-height:30px;',
      'text-align:center;margin-left:0;opacity:.35;background:#059669;',
      'box-shadow:0 2px 6px rgba(0,0,0,.2);overflow:hidden;white-space:nowrap;',
      'transition:width .2s ease,opacity .2s ease,border-radius .2s ease,padding .2s ease;}',
      '.csvx-btn.csvx-master:hover{opacity:1;width:auto;border-radius:16px;padding:0 14px;background:#047857;}',
      '.csvx-btn.csvx-master .csvx-label{display:none;margin-left:6px;font-size:11px;}',
      '.csvx-btn.csvx-master:hover .csvx-label{display:inline;}',
      '.csvx-wrap{display:inline-block;}',
    ].join('');
    var s = document.createElement('style');
    s.id = 'csvx-styles';
    s.textContent = css;
    document.head.appendChild(s);
  }

  // ===== Helpers =====
  function cellText(cell) {
    // Strip our own buttons and sort arrows, keep real content
    var clone = cell.cloneNode(true);
    clone.querySelectorAll('.csvx-btn, .sort-arrow, button').forEach(function (n) { n.remove(); });
    return clone.textContent.replace(/\s+/g, ' ').trim();
  }

  function escapeCSV(text) {
    text = String(text == null ? '' : text).replace(/"/g, '""');
    if (/[",\n\r]/.test(text)) text = '"' + text + '"';
    return text;
  }

  function tableToCSV(table) {
    var rows = [];
    table.querySelectorAll('tr').forEach(function (tr) {
      // Skip hidden rows (e.g. filtered out)
      if (tr.offsetParent === null && tr.style.display === 'none') return;
      var cols = tr.querySelectorAll('th, td');
      if (!cols.length) return;
      var row = [];
      cols.forEach(function (c) { row.push(escapeCSV(cellText(c))); });
      rows.push(row.join(','));
    });
    rows.push('');
    rows.push(escapeCSV(DISCLAIMER));
    return rows.join('\n');
  }

  function slugify(s) {
    return (s || 'table').toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
      .slice(0, 60) || 'table';
  }

  function tableTitle(table) {
    // Try caption → preceding h2/h3 → section h2/h3 → "table"
    var cap = table.querySelector('caption');
    if (cap) return cap.textContent.trim();
    var prev = table.previousElementSibling;
    while (prev) {
      if (/^H[1-4]$/.test(prev.tagName)) return prev.textContent.trim();
      prev = prev.previousElementSibling;
    }
    var parent = table.parentElement;
    for (var i = 0; i < 4 && parent; i++) {
      var h = parent.querySelector('h1, h2, h3, h4');
      if (h && h.textContent.trim()) return h.textContent.trim();
      parent = parent.parentElement;
    }
    return table.id || 'table';
  }

  function pageSlug() {
    var t = document.title || 'dashboard';
    return slugify(t.split('—')[0].split('|')[0]);
  }

  function downloadBlob(blob, filename) {
    var link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    setTimeout(function () {
      URL.revokeObjectURL(link.href);
      link.remove();
    }, 500);
  }

  // ===== Per-table button =====
  function attachPerTableButtons() {
    var tables = document.querySelectorAll('table');
    var idx = 0;
    tables.forEach(function (table) {
      if (table.dataset.csvxAttached) return;
      if (!table.querySelector('thead') || !table.querySelector('tbody')) return;
      if (!table.querySelector('tbody tr')) return; // skip empty
      table.dataset.csvxAttached = '1';
      idx++;

      var title = tableTitle(table);
      var slug = slugify(title) + '_' + idx;

      var btn = document.createElement('button');
      btn.className = 'csvx-btn';
      btn.type = 'button';
      btn.textContent = '↓ CSV';
      btn.title = 'Export "' + title + '" to CSV';
      btn.onclick = function (e) {
        e.preventDefault();
        e.stopPropagation();
        var csv = tableToCSV(table);
        var blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
        downloadBlob(blob, slug + '.csv');
      };

      // Placement: preceding heading if nearby, else just before the table.
      var placed = false;
      var prev = table.previousElementSibling;
      if (prev && /^H[1-4]$/.test(prev.tagName)) {
        prev.appendChild(btn);
        placed = true;
      } else {
        var parent = table.parentElement;
        var h = parent && parent.querySelector('h1, h2, h3, h4');
        if (h && !h.contains(table)) {
          h.appendChild(btn);
          placed = true;
        }
      }
      if (!placed) {
        var wrap = document.createElement('div');
        wrap.className = 'csvx-wrap';
        wrap.style.marginBottom = '6px';
        wrap.appendChild(btn);
        table.parentNode.insertBefore(wrap, table);
      }
    });
    return idx;
  }

  // ===== Master (all-tables) button =====
  function loadJSZip() {
    if (window.JSZip) return Promise.resolve(window.JSZip);
    return new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = JSZIP_CDN;
      s.onload = function () { resolve(window.JSZip); };
      s.onerror = function () { reject(new Error('JSZip load failed')); };
      document.head.appendChild(s);
    });
  }

  function exportAll() {
    var tables = Array.prototype.filter.call(
      document.querySelectorAll('table'),
      function (t) {
        return t.querySelector('thead') && t.querySelector('tbody tr');
      }
    );
    if (!tables.length) return;

    if (tables.length === 1) {
      var csv = tableToCSV(tables[0]);
      var blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
      downloadBlob(blob, pageSlug() + '.csv');
      return;
    }

    loadJSZip().then(function (JSZip) {
      var zip = new JSZip();
      var usedNames = {};
      tables.forEach(function (t, i) {
        var base = slugify(tableTitle(t));
        var name = base;
        var n = 1;
        while (usedNames[name]) { n++; name = base + '_' + n; }
        usedNames[name] = 1;
        zip.file(name + '.csv', '\ufeff' + tableToCSV(t));
      });
      zip.generateAsync({ type: 'blob' }).then(function (blob) {
        downloadBlob(blob, pageSlug() + '_tables.zip');
      });
    }).catch(function (err) {
      // Fallback: concatenated CSV with section headers
      var parts = [];
      tables.forEach(function (t) {
        parts.push('# ' + tableTitle(t));
        parts.push(tableToCSV(t));
        parts.push('');
      });
      var blob = new Blob(['\ufeff' + parts.join('\n')], { type: 'text/csv;charset=utf-8;' });
      downloadBlob(blob, pageSlug() + '_all.csv');
    });
  }

  function attachMasterButton(tableCount) {
    if (document.getElementById('csvx-master-btn')) return;
    if (tableCount < 1) return;
    var btn = document.createElement('button');
    btn.id = 'csvx-master-btn';
    btn.type = 'button';
    btn.className = 'csvx-btn csvx-master';
    var labelText = tableCount > 1 ? 'Download all (' + tableCount + ')' : 'Download CSV';
    btn.innerHTML = '\u2193<span class="csvx-label">' + labelText + '</span>';
    btn.title = labelText;
    btn.onclick = function (e) { e.preventDefault(); exportAll(); };
    document.body.appendChild(btn);
  }

  // ===== Init =====
  function init() {
    injectStyles();
    var count = attachPerTableButtons();
    attachMasterButton(count);

    // Re-scan for tables rendered after page load (dynamic dashboards).
    // Guard against self-trigger: disconnect during our own writes.
    var mo;
    var lastLabel = '';
    var rescanPending = false;
    function rescan() {
      if (rescanPending) return;
      rescanPending = true;
      setTimeout(function () {
        rescanPending = false;
        if (mo) mo.disconnect();
        try {
          attachPerTableButtons();
          var total = document.querySelectorAll('table[data-csvx-attached]').length;
          if (total < 1) return;
          var labelText = total > 1 ? 'Download all (' + total + ')' : 'Download CSV';
          var btn = document.getElementById('csvx-master-btn');
          if (!btn) {
            attachMasterButton(total);
            lastLabel = labelText;
          } else if (labelText !== lastLabel) {
            btn.innerHTML = '\u2193<span class="csvx-label">' + labelText + '</span>';
            btn.title = labelText;
            lastLabel = labelText;
          }
        } finally {
          if (mo) mo.observe(document.body, { childList: true, subtree: true });
        }
      }, 150);
    }
    mo = new MutationObserver(rescan);
    mo.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
