#!/usr/bin/env python3
"""Build M&A Dashboard pages for all 5 Intel sites.

Each site gets a standalone M&A page:
  - Reuses the site's existing peer_analysis template as the HTML shell (nav, ticker, page header, auth, footer)
  - Replaces the content area with the M&A Tracker UI (KPIs, filters, charts, deal log)
  - Inlines the merged ma_deals.json data

Output: {PREFIX}_MA_Dashboard.html (live) + ma_template.html (for sites with templates).
Inspection has no template system — only the live file.

Usage: python3 build_ma_pages.py
"""

import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

SITES = [
    {
        'name': 'Casino Gaming Intel',
        'prefix': 'CG',
        'dashboard': BASE / 'Casino_Gaming_Intel' / 'Dashboard',
        'shell_template': 'peer_analysis_template.html',
        'live_file': 'CG_Peer_Analysis.html',
        'page_title': 'Casino Gaming Intel — M&A Tracker',
    },
    {
        'name': 'Oil & Gas Intel',
        'prefix': 'OG',
        'dashboard': BASE / 'Oil_Gas_Intel' / 'Dashboard',
        'shell_template': 'peer_analysis_template.html',
        'live_file': 'OG_Peer_Analysis.html',
        'page_title': 'Oil & Gas Intel — M&A Tracker',
    },
    {
        'name': 'Metal Mining Intel',
        'prefix': 'MM',
        'dashboard': BASE / 'Metal_Mining_Intel' / 'Dashboard',
        'shell_template': 'peer_analysis_template.html',
        'live_file': 'MM_Peer_Analysis.html',
        'page_title': 'Metal Mining Intel — M&A Tracker',
    },
    {
        'name': 'Media & Broadcasting Intel',
        'prefix': 'MB',
        'dashboard': BASE / 'Media_Broadcasting_Intel' / 'Dashboard',
        'shell_template': 'peer_analysis_template.html',
        'live_file': 'MB_Peer_Analysis.html',
        'page_title': 'Media & Broadcasting Intel — M&A Tracker',
    },
    {
        'name': 'Inspection Intel',
        'prefix': 'TIC_NDT',
        'dashboard': BASE / 'Inspection_Intel' / 'Dashboard',
        'shell_template': None,  # no template system
        'live_file': 'TIC_NDT_Peer_Analysis_Dashboard.html',
        'page_title': 'Inspection Intel — M&A Tracker',
    },
    {
        'name': 'Aerospace & Defense Intel',
        'prefix': 'AD',
        'dashboard': BASE / 'Aerospace_Defense_Intel' / 'Dashboard',
        'shell_template': 'peer_analysis_template.html',
        'live_file': 'AD_Peer_Analysis.html',
        'page_title': 'Aerospace & Defense Intel — M&A Tracker',
    },
    {
        'name': 'Autos Intel',
        'prefix': 'AUTO',
        'dashboard': BASE / 'Autos_Intel' / 'Dashboard',
        'shell_template': 'peer_analysis_template.html',
        'live_file': 'AUTO_Peer_Analysis.html',
        'page_title': 'Autos Intel — M&A Tracker',
    },
    {
        'name': 'Chemicals Intel',
        'prefix': 'CHM',
        'dashboard': BASE / 'Chemicals_Intel' / 'Dashboard',
        'shell_template': 'peer_analysis_template.html',
        'live_file': 'CHM_Peer_Analysis.html',
        'page_title': 'Chemicals Intel — M&A Tracker',
    },
    {
        'name': 'Homebuilders Intel',
        'prefix': 'HOME',
        'dashboard': BASE / 'Homebuilders_Intel' / 'Dashboard',
        'shell_template': 'peer_analysis_template.html',
        'live_file': 'HOME_Peer_Analysis.html',
        'page_title': 'Homebuilders Intel — M&A Tracker',
    },
    {
        'name': 'Power & Utilities Intel',
        'prefix': 'PU',
        'dashboard': BASE / 'Power_Utilities_Intel' / 'Dashboard',
        'shell_template': 'peer_analysis_template.html',
        'live_file': 'PU_Peer_Analysis.html',
        'page_title': 'Power & Utilities Intel — M&A Tracker',
    },
    {
        'name': 'REITs Intel',
        'prefix': 'REIT',
        'dashboard': BASE / 'REITs_Intel' / 'Dashboard',
        'shell_template': 'peer_analysis_template.html',
        'live_file': 'REIT_Peer_Analysis.html',
        'page_title': 'REITs Intel — M&A Tracker',
    },
    {
        'name': 'Rail & Logistics Intel',
        'prefix': 'RL',
        'dashboard': BASE / 'Rail_Logistics_Intel' / 'Dashboard',
        'shell_template': 'peer_analysis_template.html',
        'live_file': 'RL_Peer_Analysis.html',
        'page_title': 'Rail & Logistics Intel — M&A Tracker',
    },
    {
        'name': 'Semiconductors Intel',
        'prefix': 'SEMI',
        'dashboard': BASE / 'Semiconductors_Intel' / 'Dashboard',
        'shell_template': 'peer_analysis_template.html',
        'live_file': 'SEMI_Peer_Analysis.html',
        'page_title': 'Semiconductors Intel — M&A Tracker',
    },
    {
        'name': 'Shipping Intel',
        'prefix': 'SHP',
        'dashboard': BASE / 'Shipping_Intel' / 'Dashboard',
        'shell_template': 'peer_analysis_template.html',
        'live_file': 'SHP_Peer_Analysis.html',
        'page_title': 'Shipping Intel — M&A Tracker',
    },
]


# The M&A Tracker body (CSS + HTML + JS). Portable across sites.
MA_CSS = """
<style id="ma-dashboard-styles">
.ma-container { max-width: 1500px; margin: 0 auto; padding: 24px; }
.ma-page-header { background: var(--bg-card, #1a1d29); border: 1px solid rgba(255,255,255,0.06); padding: 28px 32px; border-radius: 10px; margin-bottom: 24px; box-shadow: inset 0 1px 0 rgba(255,255,255,0.04); }
.ma-page-header h1 { font-size: 1.5rem; color: var(--text-primary, #e8eaed); margin-bottom: 4px; }
.ma-page-header p { color: var(--text-secondary, #9aa0a6); font-size: 0.9rem; }
.ma-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
.ma-kpi { background: var(--bg-card, #1a1d29); border: 1px solid rgba(255,255,255,0.06); border-radius: 10px; padding: 16px 20px; }
.ma-kpi .label { font-size: 11px; color: var(--text-secondary, #9aa0a6); text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 4px; }
.ma-kpi .value { font-size: 28px; font-weight: 700; color: var(--accent, #f59e0b); }
.ma-kpi .sub { font-size: 12px; color: var(--text-secondary, #9aa0a6); margin-top: 2px; }
.ma-filters { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.ma-filters select { padding: 6px 12px; border: 1px solid rgba(255,255,255,0.12); border-radius: 6px; background: var(--bg-card, #1a1d29); color: var(--text-primary, #e8eaed); font-size: 13px; cursor: pointer; }
.ma-filters select option { background: var(--bg-card, #1a1d29); }
.ma-card { background: var(--bg-card, #1a1d29); border: 1px solid rgba(255,255,255,0.06); border-radius: 10px; padding: 20px; margin-bottom: 24px; }
.ma-card-title { font-size: 14px; font-weight: 600; color: var(--text-primary, #e8eaed); margin-bottom: 12px; }
.ma-chart-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }
.ma-chart-wrap { background: var(--bg-card, #1a1d29); border: 1px solid rgba(255,255,255,0.06); border-radius: 10px; padding: 20px; }
.ma-chart-wrap h3 { font-size: 14px; font-weight: 600; color: var(--text-primary, #e8eaed); margin-bottom: 12px; }
.ma-chart-wrap canvas { max-height: 280px; }
.ma-deal-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.ma-deal-table th { text-align: left; padding: 10px 12px; color: var(--text-secondary, #9aa0a6); font-size: 11px; text-transform: uppercase; letter-spacing: 0.4px; border-bottom: 1px solid rgba(255,255,255,0.1); cursor: pointer; user-select: none; }
.ma-deal-table th:hover { color: var(--accent, #f59e0b); }
.ma-deal-table td { padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,0.04); color: var(--text-primary, #e8eaed); }
.ma-deal-table tr:hover td { background: rgba(255,255,255,0.02); }
.status-badge { display: inline-block; font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
.status-completed { background: rgba(34,197,94,0.15); color: #22c55e; }
.status-pending { background: rgba(245,158,11,0.15); color: #f59e0b; }
.status-rumored { background: rgba(186,104,200,0.15); color: #ba68c8; }
.sector-tag { display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 4px; background: rgba(79,195,247,0.12); color: #4fc3f7; }
.source-tag { font-size: 10px; color: var(--text-secondary, #9aa0a6); text-transform: uppercase; letter-spacing: 0.3px; }
.source-badge { display: inline-block; font-size: 10px; font-weight: 600; padding: 2px 7px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.4px; margin-left: 4px; }
.source-curated { background: #e5e7eb; color: #374151; }
.source-8k { background: #dbeafe; color: #1e40af; }
.source-wire { background: #fef3c7; color: #92400e; }
.ma-rationale { font-size: 12px; color: var(--text-secondary, #9aa0a6); max-width: 300px; line-height: 1.4; }
.ma-empty { padding: 48px 24px; text-align: center; color: var(--text-secondary, #9aa0a6); font-size: 14px; }
@media (max-width: 900px) {
  .ma-chart-row { grid-template-columns: 1fr; }
  .ma-kpis { grid-template-columns: repeat(2, 1fr); }
  .ma-filters { flex-direction: column; }
}
</style>
"""

MA_BODY = """
<div class="ma-container">
    <div class="ma-page-header">
        <h1>M&amp;A Tracker</h1>
        <p>Announced, pending, and completed M&amp;A activity across the {SITE_NAME} coverage universe. Curated from public filings and press releases; enriched by nightly 8-K extraction.</p>
    </div>

    <div class="ma-kpis" id="ma-kpis"></div>

    <div class="ma-filters">
        <select id="ma-filter-status" onchange="renderMATab()">
            <option value="all">All Statuses</option>
            <option value="completed">Completed</option>
            <option value="pending">Pending</option>
            <option value="rumored">Rumored / Withdrawn</option>
        </select>
        <select id="ma-filter-sector" onchange="renderMATab()">
            <option value="all">All Sectors</option>
        </select>
        <select id="ma-filter-acquirer" onchange="renderMATab()">
            <option value="all">All Acquirers</option>
        </select>
        <select id="ma-filter-year" onchange="renderMATab()">
            <option value="all">All Years</option>
        </select>
    </div>

    <div class="ma-chart-row">
        <div class="ma-chart-wrap"><h3>Deal Activity Timeline</h3><canvas id="chart-ma-timeline"></canvas></div>
        <div class="ma-chart-wrap"><h3>Deal Value by Acquirer</h3><canvas id="chart-ma-acquirer"></canvas></div>
    </div>
    <div class="ma-chart-row">
        <div class="ma-chart-wrap"><h3>EV/EBITDA Multiples by Deal</h3><canvas id="chart-ma-multiples"></canvas></div>
        <div class="ma-chart-wrap"><h3>Deals by Sector</h3><canvas id="chart-ma-sector"></canvas></div>
    </div>

    <div class="ma-card">
        <div class="ma-card-title">Deal Log <span class="source-tag" id="ma-deal-count"></span></div>
        <div style="overflow-x:auto;">
            <table class="ma-deal-table" id="ma-deal-table">
                <thead><tr>
                    <th onclick="sortMATable(0)">Date</th>
                    <th onclick="sortMATable(1)">Target</th>
                    <th onclick="sortMATable(2)">Acquirer</th>
                    <th onclick="sortMATable(3)" style="text-align:right;">Value ($M)</th>
                    <th onclick="sortMATable(4)" style="text-align:right;">EV/Rev</th>
                    <th onclick="sortMATable(5)" style="text-align:right;">EV/EBITDA</th>
                    <th onclick="sortMATable(6)">Sector</th>
                    <th>Rationale</th>
                    <th onclick="sortMATable(8)">Status / Source</th>
                </tr></thead>
                <tbody id="ma-deal-tbody"></tbody>
            </table>
            <div class="ma-empty" id="ma-empty" style="display:none;">No deals match the current filters.</div>
        </div>
    </div>
</div>
"""

MA_JS = r"""
<script id="ma-dashboard-script">
var MA_DEALS = __MA_DEALS_JSON__;
var MA_COLORS = ['#4fc3f7','#81c784','#ffb74d','#e57373','#ba68c8','#4db6ac','#fff176','#f48fb1','#90a4ae','#a1887f'];
var maCharts = {};
var maSortCol = 0, maSortAsc = false;

function destroyMAChart(id) { if (maCharts[id]) { maCharts[id].destroy(); delete maCharts[id]; } }

function fmtVal(v) {
    if (v == null || isNaN(v)) return '—';
    if (v >= 1000) return '$' + (v/1000).toFixed(1) + 'B';
    return '$' + v.toLocaleString() + 'M';
}

function renderMATab() {
    var statusFilter = document.getElementById('ma-filter-status').value;
    var sectorFilter = document.getElementById('ma-filter-sector').value;
    var acquirerFilter = document.getElementById('ma-filter-acquirer').value;
    var yearFilter = document.getElementById('ma-filter-year').value;

    var deals = MA_DEALS.slice();
    if (statusFilter !== 'all') deals = deals.filter(function(d){return d.status === statusFilter;});
    if (sectorFilter !== 'all') deals = deals.filter(function(d){return d.sector === sectorFilter;});
    if (acquirerFilter !== 'all') deals = deals.filter(function(d){return d.acquirer === acquirerFilter;});
    if (yearFilter !== 'all') deals = deals.filter(function(d){return (d.date || '').slice(0,4) === yearFilter;});

    // KPIs (computed on UNFILTERED base to show universe totals)
    var completed = MA_DEALS.filter(function(d){return d.status === 'completed';});
    var totalValue = completed.reduce(function(s,d){return s + (d.value_m || 0);}, 0);
    var evRevDeals = completed.filter(function(d){return d.ev_revenue;});
    var avgEvRev = evRevDeals.length ? evRevDeals.reduce(function(s,d){return s + d.ev_revenue;}, 0) / evRevDeals.length : 0;
    var evEbDeals = completed.filter(function(d){return d.ev_ebitda;});
    var avgEvEbitda = evEbDeals.length ? evEbDeals.reduce(function(s,d){return s + d.ev_ebitda;}, 0) / evEbDeals.length : 0;

    document.getElementById('ma-kpis').innerHTML =
        '<div class="ma-kpi"><div class="label">Total Deals Tracked</div><div class="value">' + MA_DEALS.length + '</div><div class="sub">' + completed.length + ' completed · ' + (MA_DEALS.length - completed.length) + ' pending/rumored</div></div>' +
        '<div class="ma-kpi"><div class="label">Aggregate Deal Value</div><div class="value">' + (totalValue >= 1000 ? '$' + (totalValue/1000).toFixed(1) + 'B' : '$' + totalValue.toLocaleString() + 'M') + '</div><div class="sub">Completed deals with disclosed values</div></div>' +
        '<div class="ma-kpi"><div class="label">Avg EV/Revenue</div><div class="value">' + (avgEvRev > 0 ? avgEvRev.toFixed(1) + 'x' : '—') + '</div><div class="sub">' + evRevDeals.length + ' deals with disclosed EV/Rev</div></div>' +
        '<div class="ma-kpi"><div class="label">Avg EV/EBITDA</div><div class="value">' + (avgEvEbitda > 0 ? avgEvEbitda.toFixed(1) + 'x' : '—') + '</div><div class="sub">' + evEbDeals.length + ' deals with disclosed EV/EBITDA</div></div>';

    // Deal table
    var tbody = document.getElementById('ma-deal-tbody');
    var sorted = deals.slice().sort(function(a,b){return (new Date(b.date)) - (new Date(a.date));});
    if (!sorted.length) {
        tbody.innerHTML = '';
        document.getElementById('ma-empty').style.display = 'block';
    } else {
        document.getElementById('ma-empty').style.display = 'none';
        tbody.innerHTML = sorted.map(function(d){
            var acquirerCell = d.source_url ? '<a href="' + d.source_url + '" target="_blank" rel="noopener" style="color:var(--accent,#f59e0b);text-decoration:none;">' + d.acquirer + '</a>' : d.acquirer;
            return '<tr>' +
                '<td>' + (d.date || '—') + '</td>' +
                '<td style="font-weight:700;">' + (d.target || '—') + '</td>' +
                '<td>' + acquirerCell + '</td>' +
                '<td style="text-align:right;">' + (d.value_m ? '$' + d.value_m.toLocaleString() : '—') + '</td>' +
                '<td style="text-align:right;">' + (d.ev_revenue ? d.ev_revenue.toFixed(1) + 'x' : '—') + '</td>' +
                '<td style="text-align:right;">' + (d.ev_ebitda ? d.ev_ebitda.toFixed(1) + 'x' : '—') + '</td>' +
                '<td><span class="sector-tag">' + (d.sector || '—') + '</span></td>' +
                '<td class="ma-rationale">' + (d.rationale || '') + '</td>' +
                '<td><span class="status-badge status-' + d.status + '">' + d.status + '</span>' + (d.source ? d.source.split('+').map(function(s){var cls=s==='8-K'?'source-8k':s==='wire'?'source-wire':'source-curated'; return '<span class="source-badge '+cls+'">'+s+'</span>';}).join('') : '') + '</td>' +
                '</tr>';
        }).join('');
    }
    document.getElementById('ma-deal-count').textContent = sorted.length + ' deals';

    // Charts
    var timelineDeals = deals.filter(function(d){return d.value_m;}).sort(function(a,b){return (new Date(a.date)) - (new Date(b.date));});
    destroyMAChart('chart-ma-timeline');
    var tlCtx = document.getElementById('chart-ma-timeline');
    if (tlCtx && window.Chart) {
        maCharts['chart-ma-timeline'] = new Chart(tlCtx, {
            type: 'bar',
            data: {
                labels: timelineDeals.map(function(d){return (d.date || '').slice(0,7);}),
                datasets: [{
                    label: 'Deal Value ($M)',
                    data: timelineDeals.map(function(d){return d.value_m;}),
                    backgroundColor: timelineDeals.map(function(d){return d.status==='completed' ? 'rgba(79,195,247,0.7)' : d.status==='pending' ? 'rgba(255,183,77,0.7)' : 'rgba(186,104,200,0.7)';}),
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: { callbacks: { title: function(items){var d = timelineDeals[items[0].dataIndex]; return d.acquirer + ' → ' + d.target;}, label: function(item){return fmtVal(item.raw);} } } },
                scales: { x: { ticks: { color: '#9aa0a6', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' } }, y: { ticks: { color: '#9aa0a6', callback: function(v){return fmtVal(v);} }, grid: { color: 'rgba(255,255,255,0.04)' } } }
            }
        });
    }

    // Acquirer aggregation
    var acquirerMap = {};
    deals.filter(function(d){return d.value_m;}).forEach(function(d){acquirerMap[d.acquirer] = (acquirerMap[d.acquirer] || 0) + d.value_m;});
    var acqSorted = Object.entries(acquirerMap).sort(function(a,b){return b[1] - a[1];}).slice(0, 10);
    destroyMAChart('chart-ma-acquirer');
    var acqCtx = document.getElementById('chart-ma-acquirer');
    if (acqCtx && window.Chart) {
        maCharts['chart-ma-acquirer'] = new Chart(acqCtx, {
            type: 'bar',
            data: {
                labels: acqSorted.map(function(a){return a[0];}),
                datasets: [{ label: 'Total Deal Value ($M)', data: acqSorted.map(function(a){return a[1];}), backgroundColor: MA_COLORS.slice(0, acqSorted.length).map(function(c){return c + 'cc';}), borderRadius: 4 }]
            },
            options: {
                indexAxis: 'y', responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: { callbacks: { label: function(i){return fmtVal(i.raw);} } } },
                scales: { x: { ticks: { color: '#9aa0a6', callback: function(v){return fmtVal(v);} }, grid: { color: 'rgba(255,255,255,0.04)' } }, y: { ticks: { color: '#9aa0a6', font: { size: 11 } }, grid: { display: false } } }
            }
        });
    }

    // Multiples
    var multiDeals = deals.filter(function(d){return d.ev_ebitda;});
    destroyMAChart('chart-ma-multiples');
    var mCtx = document.getElementById('chart-ma-multiples');
    if (mCtx && window.Chart) {
        maCharts['chart-ma-multiples'] = new Chart(mCtx, {
            type: 'bar',
            data: {
                labels: multiDeals.map(function(d){return d.target.length > 18 ? d.target.slice(0,16) + '…' : d.target;}),
                datasets: [
                    { label: 'EV/Revenue', data: multiDeals.map(function(d){return d.ev_revenue;}), backgroundColor: 'rgba(79,195,247,0.6)', borderRadius: 4 },
                    { label: 'EV/EBITDA', data: multiDeals.map(function(d){return d.ev_ebitda;}), backgroundColor: 'rgba(129,199,132,0.6)', borderRadius: 4 }
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { labels: { color: '#9aa0a6', font: { size: 11 } } }, tooltip: { callbacks: { label: function(i){return i.dataset.label + ': ' + (i.raw ? i.raw.toFixed(1) + 'x' : '—');} } } },
                scales: { x: { ticks: { color: '#9aa0a6', font: { size: 10 }, maxRotation: 45 }, grid: { color: 'rgba(255,255,255,0.04)' } }, y: { ticks: { color: '#9aa0a6', callback: function(v){return v + 'x';} }, grid: { color: 'rgba(255,255,255,0.04)' } } }
            }
        });
    }

    // Sector doughnut
    var sectorMap = {};
    deals.forEach(function(d){sectorMap[d.sector] = (sectorMap[d.sector] || 0) + 1;});
    destroyMAChart('chart-ma-sector');
    var sCtx = document.getElementById('chart-ma-sector');
    if (sCtx && window.Chart) {
        maCharts['chart-ma-sector'] = new Chart(sCtx, {
            type: 'doughnut',
            data: {
                labels: Object.keys(sectorMap),
                datasets: [{ data: Object.values(sectorMap), backgroundColor: MA_COLORS.slice(0, Object.keys(sectorMap).length), borderWidth: 0 }]
            },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { color: '#9aa0a6', font: { size: 11 }, padding: 12 } } } }
        });
    }
}

function sortMATable(col) {
    if (maSortCol === col) maSortAsc = !maSortAsc; else { maSortCol = col; maSortAsc = true; }
    var tbody = document.getElementById('ma-deal-tbody');
    var rows = Array.from(tbody.querySelectorAll('tr'));
    rows.sort(function(a,b){
        var av = a.cells[col].textContent.trim(), bv = b.cells[col].textContent.trim();
        var an = parseFloat(av.replace(/[$,x]/g, '')), bn = parseFloat(bv.replace(/[$,x]/g, ''));
        if (!isNaN(an) && !isNaN(bn)) return maSortAsc ? an - bn : bn - an;
        return maSortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
    });
    rows.forEach(function(r){tbody.appendChild(r);});
}

function initMAFilters() {
    var sectors = Array.from(new Set(MA_DEALS.map(function(d){return d.sector;}))).filter(Boolean).sort();
    var acquirers = Array.from(new Set(MA_DEALS.map(function(d){return d.acquirer;}))).filter(Boolean).sort();
    var years = Array.from(new Set(MA_DEALS.map(function(d){return (d.date||'').slice(0,4);}))).filter(Boolean).sort().reverse();
    var sectorSel = document.getElementById('ma-filter-sector');
    var acqSel = document.getElementById('ma-filter-acquirer');
    var yearSel = document.getElementById('ma-filter-year');
    sectors.forEach(function(s){var o = document.createElement('option'); o.value = s; o.textContent = s; sectorSel.appendChild(o);});
    acquirers.forEach(function(a){var o = document.createElement('option'); o.value = a; o.textContent = a; acqSel.appendChild(o);});
    years.forEach(function(y){var o = document.createElement('option'); o.value = y; o.textContent = y; yearSel.appendChild(o);});
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function(){ initMAFilters(); renderMATab(); });
} else {
    initMAFilters(); renderMATab();
}
</script>
"""


def replace_content_region(shell_html: str, prefix: str, site_name: str, page_title: str, deals: list) -> str:
    """Take the peer_analysis shell HTML and replace the content between page-header and footer with the M&A Tracker.

    Conservative approach: find the `<div class="container">` open tag, and the closing `</div>` before
    `<footer>` / "Sector Intelligence". Replace everything in between with the M&A content.

    Also updates:
    - <title> to page_title
    - peer analysis nav link to not be "active"
    - adds the M&A content + style + script
    """
    html = shell_html

    # 1) Update <title>
    html = re.sub(r'<title>[^<]*</title>', f'<title>{page_title}</title>', html, count=1)

    # 2) Update <h1> page-header text (first h1 in a .page-header)
    # We'll override it anyway by replacing the container. But if the shell's nav uses class="active"
    # on peer analysis link, remove that class.
    # Strip class="active" but preserve the original href (the optional `_Dashboard` suffix
    # matters — Inspection Intel uses TIC_NDT_Peer_Analysis_Dashboard.html, all others use
    # XX_Peer_Analysis.html). Capture the suffix and re-emit it.
    html = re.sub(
        r'<a([^>]+)_Peer_Analysis(_Dashboard)?\.html"\s*class="active"',
        r'<a\1_Peer_Analysis\2.html"',
        html,
    )

    # 3) Remove the peer analysis body. Peer templates have a <div class="container"> ... </div> followed by footer.
    # We replace container content with our ma-container and our JS.
    # Strategy: replace everything from the first `<div class="container">` through just before the first `<footer` tag
    # (or "Sector Intelligence" text) with our body.

    m_container_start = re.search(r'<div class="(?:container|wrap|dashboard-container)">', html)
    if not m_container_start:
        raise RuntimeError('Shell does not contain a container div (container|wrap|dashboard-container)')

    # Find end: first <footer tag OR a footer div with "Sector Intelligence" text.
    tail = html[m_container_start.end():]
    m_footer = re.search(r'<footer', tail)
    m_div_footer = re.search(r'<div[^>]*class="[^"]*footer[^"]*"[^>]*>', tail)
    candidates = [m for m in [m_footer, m_div_footer] if m]
    if not candidates:
        raise RuntimeError('Shell does not contain a footer marker')
    footer_start = min(m.start() for m in candidates)
    end_idx = m_container_start.end() + footer_start

    # We also need to close the container div. The shell had </div> </div> ... before footer. Our MA_BODY
    # already uses ma-container, so we don't need the outer .container. Replace entirely.
    new_content = '\n' + MA_CSS + '\n' + MA_BODY.replace('{SITE_NAME}', site_name) + '\n'

    html = html[:m_container_start.start()] + new_content + html[end_idx:]

    # 4) Append the JS just before </body>. Inject deals JSON.
    deals_json = json.dumps(deals, indent=None, separators=(',', ':'))
    # Escape </script in JSON (just in case)
    deals_json = deals_json.replace('</script', '<\\/script')
    script_block = MA_JS.replace('__MA_DEALS_JSON__', deals_json)

    # 5) Remove any existing <script> blocks that reference PEER_DATA / buildRankings / scatterChart / perfChart / MARKET_DATA / INJECTED_DATA_START-END
    # Simple: remove the big <script>...</script> block after the MA body (the one from peer_analysis). We can find it by looking between the last our-inserted </div> and the footer point.
    # Actually simpler: after our replacement, there will be any leftover scripts from peer_analysis in the tail (before </body>). We need to find and remove ALL <script> blocks EXCEPT Chart.js (CDN) and auth.js (the ones in the <head>).
    # Those CDN/auth scripts are in <head> or near top of <body>. The big embedded script is after the container (which we just removed). Let's remove any <script>...</script> blocks that contain "PEER_DATA" or "buildRankings" or "buildScatterCharts".
    def strip_old_peer_scripts(h):
        pattern = re.compile(r'<script[^>]*>((?:(?!</script>)[\s\S])*?)</script>', re.IGNORECASE)
        out = []
        last = 0
        for m in pattern.finditer(h):
            body = m.group(1)
            if ('PEER_DATA' in body) or ('buildRankings' in body) or ('buildScatterCharts' in body) or ('buildPerfChart' in body) or ('MARKET_DATA' in body and 'PEER_DATA' in body):
                out.append(h[last:m.start()])
                last = m.end()
            elif 'COMPARE_METRICS' in body or 'updateComparison' in body:
                out.append(h[last:m.start()])
                last = m.end()
        out.append(h[last:])
        return ''.join(out)

    html = strip_old_peer_scripts(html)

    # 6) Insert MA script just before </body>
    html = html.replace('</body>', script_block + '\n</body>', 1)

    return html


def main():
    for site in SITES:
        dash = site['dashboard']
        deals_path = dash / 'ma_deals.json'
        if not deals_path.exists():
            print(f'SKIP {site["prefix"]}: no ma_deals.json')
            continue
        with open(deals_path) as f:
            deals = json.load(f)

        shell_live_path = dash / site['live_file']
        if not shell_live_path.exists():
            print(f'SKIP {site["prefix"]}: no shell live file {site["live_file"]}')
            continue
        shell_html = shell_live_path.read_text()

        page = replace_content_region(shell_html, site['prefix'], site['name'], site['page_title'], deals)

        # Write live file
        out_live = dash / f'{site["prefix"]}_MA_Dashboard.html'
        out_live.write_text(page)
        print(f'Wrote {out_live.relative_to(BASE)} ({len(deals)} deals)')

        # Write template (if site has templates)
        if site['shell_template']:
            shell_template_path = dash / site['shell_template']
            if shell_template_path.exists():
                tpl_html = shell_template_path.read_text()
                page_tpl = replace_content_region(tpl_html, site['prefix'], site['name'], site['page_title'], deals)
                out_tpl = dash / 'ma_template.html'
                out_tpl.write_text(page_tpl)
                print(f'Wrote {out_tpl.relative_to(BASE)}')


if __name__ == '__main__':
    main()
