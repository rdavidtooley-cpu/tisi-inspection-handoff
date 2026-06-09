// Inspection Intel — Shared Export & Deep Link Utilities

// ===== CSV EXPORT =====
function exportTableToCSV(tableEl, filename) {
    if (typeof tableEl === 'string') tableEl = document.getElementById(tableEl);
    if (!tableEl) return;
    const rows = tableEl.querySelectorAll('tr');
    const csv = [];
    rows.forEach(row => {
        const cols = row.querySelectorAll('th, td');
        const rowData = [];
        cols.forEach(col => {
            let text = col.textContent.trim().replace(/"/g, '""');
            if (text.includes(',') || text.includes('"') || text.includes('\n')) text = '"' + text + '"';
            rowData.push(text);
        });
        csv.push(rowData.join(','));
    });
    csv.push('');
    csv.push('"DISCLAIMER: The information provided is for informational and educational purposes only and does not constitute investment advice, financial advice, legal advice, or any other form of professional advice. No representation or warranty is made regarding the accuracy, completeness, or reliability of any information presented. Always consult a qualified professional before making any investment or financial decisions."');
    const blob = new Blob([csv.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename || 'export.csv';
    link.click();
    URL.revokeObjectURL(link.href);
}

// ===== DEEP LINK: TAB =====
function applyDeepLinkTab() {
    const hash = window.location.hash.slice(1);
    if (!hash) return;
    const params = new URLSearchParams(hash);
    const tab = params.get('tab');
    if (tab) {
        const btn = document.querySelector(`.tab-btn[onclick*="'${tab}'"]`);
        if (btn) { btn.click(); }
    }
    return params;
}

function updateHashParam(key, value) {
    const hash = window.location.hash.slice(1);
    const params = new URLSearchParams(hash);
    params.set(key, value);
    history.replaceState(null, '', '#' + params.toString());
}

// ===== EXPORT BUTTON HELPER =====
function addExportButton(containerSelector, tableId, filename, label) {
    const container = document.querySelector(containerSelector);
    if (!container) return;
    const btn = document.createElement('button');
    btn.className = 'export-btn';
    btn.textContent = label || 'Export CSV';
    btn.onclick = () => exportTableToCSV(tableId, filename);
    const h3 = container.querySelector('h3');
    if (h3) {
        h3.style.display = 'flex';
        h3.style.justifyContent = 'space-between';
        h3.style.alignItems = 'center';
        h3.appendChild(btn);
    } else {
        container.insertBefore(btn, container.firstChild);
    }
}
