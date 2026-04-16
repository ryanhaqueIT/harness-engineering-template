#!/usr/bin/env python3
"""Generate the Harness DAG Dashboard — a self-contained HTML file.

Produces .harness/dashboard.html with:
- Airflow-inspired DAG visualization of all 25 validation gates
- 4 tabs: Pipeline, Gates, Agents, History (Grid View)
- Live polling from dashboard_state.json (2-second interval)
- Dark/light theme toggle
- Click-to-inspect detail panel
- Zero external dependencies (no npm, no CDN, no build step)

Usage:
    python3 scripts/harness_dashboard.py              # Generate HTML
    python3 scripts/harness_dashboard.py --open        # Generate + open browser
    python3 scripts/harness_dashboard.py --serve       # Generate + HTTP server
    python3 scripts/harness_dashboard.py --serve --open # All three
"""

import json
import pathlib
import argparse
import subprocess
import webbrowser
import http.server
import threading
import os
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
HARNESS_DIR = REPO_ROOT / ".harness"
OUTPUT_FILE = HARNESS_DIR / "dashboard.html"

# Gate definitions with layer assignments
GATES = {
    "B1": {"name": "Lint", "layer": 1},
    "B2": {"name": "Format", "layer": 1},
    "B4": {"name": "Import Boundaries", "layer": 2},
    "B5": {"name": "Golden Principles", "layer": 2},
    "B6": {"name": "Architecture", "layer": 2},
    "B7": {"name": "Type Check", "layer": 2},
    "B8": {"name": "Wiring", "layer": 2},
    "B3": {"name": "Tests", "layer": 3},
    "F1": {"name": "TS Check", "layer": 4},
    "F2": {"name": "ESLint", "layer": 4},
    "F3": {"name": "Prettier", "layer": 4},
    "F4": {"name": "Build", "layer": 4},
    "F5": {"name": "Frontend Tests", "layer": 4},
    "F6": {"name": "UI Legibility", "layer": 5},
    "F7": {"name": "Playwright", "layer": 5},
    "I1": {"name": "Terraform Fmt", "layer": 5},
    "I2": {"name": "Terraform Validate", "layer": 5},
    "O1": {"name": "Observability", "layer": 6},
    "X1": {"name": "Doc Cross-Refs", "layer": 7},
    "X2": {"name": "No Secrets", "layer": 7},
    "X3": {"name": "E2E Local", "layer": 7},
    "X4": {"name": "E2E Deployed", "layer": 7},
    "X5": {"name": "Feature List", "layer": 7},
    "X6": {"name": "Live Features", "layer": 7},
    "X7": {"name": "Spec Compliance", "layer": 7},
    "R1": {"name": "Ratchet", "layer": 7},
}

LAYER_NAMES = {
    1: "Deterministic",
    2: "Structural",
    3: "Tests",
    4: "Build & Frontend",
    5: "UI & Infra",
    6: "Observability",
    7: "PRD Enforcement",
}

PIPELINE_STAGES = [
    {"id": "spec", "name": "Spec", "icon": "&#128196;"},
    {"id": "plan", "name": "Plan", "icon": "&#128203;"},
    {"id": "features", "name": "Features", "icon": "&#9776;"},
    {"id": "implement", "name": "Implement", "icon": "&#9000;"},
    {"id": "validate", "name": "Validate", "icon": "&#9989;"},
    {"id": "ship", "name": "Ship", "icon": "&#128640;"},
]

AGENTS = [
    {"id": "planner", "name": "Planner"},
    {"id": "tester", "name": "Tester"},
    {"id": "executor", "name": "Executor"},
    {"id": "build-fixer", "name": "Build Fixer"},
    {"id": "reviewer", "name": "Reviewer"},
    {"id": "entropy-cleaner", "name": "Entropy Cleaner"},
    {"id": "bootstrapper", "name": "Bootstrapper"},
    {"id": "post-build-reviewer", "name": "Post-Build Reviewer"},
]


def get_repo_info():
    """Get repo name and branch from git."""
    try:
        toplevel = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(REPO_ROOT), stderr=subprocess.DEVNULL
        ).decode().strip()
        name = toplevel.replace("\\", "/").split("/")[-1]
    except Exception:
        name = REPO_ROOT.name
    try:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"],
            cwd=str(REPO_ROOT), stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        branch = "unknown"
    return name, branch


def generate_css():
    return r"""
:root {
    --bg: #0f172a; --surface: #1e293b; --surface-elevated: #334155;
    --text: #e2e8f0; --text-muted: #94a3b8; --border: #334155;
    --passed-bg: #064e3b; --passed-border: #10b981; --passed-badge: #059669;
    --running-bg: #164e63; --running-border: #06b6d4; --running-badge: #0891b2;
    --failed-bg: #450a0a; --failed-border: #ef4444; --failed-badge: #dc2626;
    --skipped-bg: #27272a; --skipped-border: #71717a; --skipped-badge: #52525b;
    --pending-bg: #1e293b; --pending-border: #475569; --pending-badge: #475569;
    --warning-bg: #451a03; --warning-border: #f59e0b; --warning-badge: #d97706;
    --accent: #3b82f6; --accent-muted: #1e3a5f;
    --grade-a: #10b981; --grade-b: #3b82f6; --grade-c: #f59e0b; --grade-d: #ef4444;
    --node-w: 180; --node-h: 52; --layer-gap: 72; --node-gap: 16;
    --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
[data-theme="light"] {
    --bg: #f8fafc; --surface: #ffffff; --surface-elevated: #f1f5f9;
    --text: #0f172a; --text-muted: #64748b; --border: #e2e8f0;
    --passed-bg: #ecfdf5; --failed-bg: #fef2f2; --running-bg: #ecfeff;
    --skipped-bg: #f4f4f5; --pending-bg: #f8fafc; --warning-bg: #fffbeb;
    --accent-muted: #dbeafe;
}
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:var(--font); background:var(--bg); color:var(--text); height:100vh; display:flex; flex-direction:column; overflow:hidden; }
#app { display:flex; flex-direction:column; height:100vh; }

/* Header */
header { display:flex; align-items:center; justify-content:space-between; padding:10px 20px; background:var(--surface); border-bottom:1px solid var(--border); min-height:56px; flex-shrink:0; }
.hdr-left { display:flex; align-items:center; gap:12px; }
.hdr-logo { width:28px; height:28px; }
.hdr-repo { font-size:15px; font-weight:700; }
.hdr-branch { font-size:11px; padding:2px 8px; border-radius:10px; background:var(--surface-elevated); color:var(--text-muted); }
.hdr-center { display:flex; align-items:center; gap:16px; }
.grade-badge { font-size:22px; font-weight:800; padding:2px 14px; border-radius:8px; color:#fff; }
.grade-A { background:var(--grade-a); } .grade-B { background:var(--grade-b); }
.grade-C { background:var(--grade-c); } .grade-D, .grade-F { background:var(--grade-d); }
.grade-unknown { background:var(--pending-badge); }
.hdr-score { font-size:13px; color:var(--text-muted); }
.hdr-right { display:flex; align-items:center; gap:12px; font-size:12px; color:var(--text-muted); }
.ratchet-up { color:var(--passed-border); } .ratchet-down { color:var(--failed-border); }
.theme-btn { background:none; border:1px solid var(--border); color:var(--text-muted); padding:4px 10px; border-radius:6px; cursor:pointer; font-size:12px; }
.theme-btn:hover { background:var(--surface-elevated); }

/* Tabs */
nav { display:flex; gap:0; background:var(--surface); border-bottom:1px solid var(--border); flex-shrink:0; padding:0 20px; }
.tab { padding:10px 18px; font-size:13px; font-weight:500; color:var(--text-muted); cursor:pointer; border-bottom:3px solid transparent; transition: color .15s, border-color .15s; }
.tab:hover { color:var(--text); }
.tab.active { color:var(--accent); border-bottom-color:var(--accent); }

/* Main area */
main { flex:1; display:flex; overflow:hidden; position:relative; }
#dag-container { flex:1; overflow:auto; padding:20px; position:relative; }
#dag-canvas { display:block; }

/* Detail panel */
#detail-panel { width:320px; background:var(--surface); border-left:1px solid var(--border); overflow-y:auto; padding:16px; flex-shrink:0; transition: transform .2s; }
#detail-panel.hidden { display:none; }
.dp-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; }
.dp-title { font-size:14px; font-weight:700; }
.dp-close { background:none; border:none; color:var(--text-muted); cursor:pointer; font-size:18px; padding:2px 6px; }
.dp-close:hover { color:var(--text); }
.dp-badge { display:inline-flex; align-items:center; gap:4px; padding:3px 10px; border-radius:12px; font-size:11px; font-weight:600; color:#fff; }
.dp-stat { font-size:12px; color:var(--text-muted); margin:4px 0; }
.dp-section { margin-top:14px; }
.dp-section-title { font-size:12px; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:.5px; margin-bottom:6px; }
.dp-finding { font-size:12px; padding:6px 8px; margin:4px 0; background:var(--surface-elevated); border-radius:4px; border-left:3px solid var(--failed-border); }

/* Status bar */
footer { display:flex; align-items:center; justify-content:space-between; padding:6px 20px; background:var(--surface); border-top:1px solid var(--border); font-size:11px; color:var(--text-muted); flex-shrink:0; min-height:32px; }
.sb-gates { display:flex; gap:4px; align-items:center; }
.sb-dot { width:10px; height:10px; border-radius:3px; display:inline-block; }
.sb-dot-passed { background:var(--passed-border); } .sb-dot-failed { background:var(--failed-border); }
.sb-dot-skipped { background:var(--skipped-border); } .sb-dot-pending { background:var(--pending-border); }
.sb-dot-running { background:var(--running-border); }

/* Gate nodes (SVG styled via classes) */
.gate-node { cursor:pointer; transition: filter .15s; }
.gate-node:hover { filter: brightness(1.1); }
.gate-node.selected rect:first-child { stroke:var(--accent)!important; stroke-width:3px!important; }

/* Running glow animation */
@keyframes glow { 0%,100%{filter:drop-shadow(0 0 3px rgba(6,182,212,.3))} 50%{filter:drop-shadow(0 0 8px rgba(6,182,212,.6))} }
.gate-running { animation: glow 2s ease-in-out infinite; }

/* Edge animation */
@keyframes dash { to { stroke-dashoffset: -20; } }
.edge-animated { stroke-dasharray: 8 4; animation: dash .8s linear infinite; }

/* Spinner for running */
@keyframes spin { to { transform: rotate(360deg); } }

/* Grid View (History tab) */
.grid-container { overflow:auto; padding:20px; }
.grid-table { border-collapse:collapse; }
.grid-table th, .grid-table td { padding:0; }
.grid-header-cell { width:18px; text-align:center; padding:2px 0; position:relative; }
.grid-duration-bar { width:14px; margin:0 auto; border-radius:2px 2px 0 0; }
.grid-gate-label { font-size:11px; padding:2px 8px; text-align:left; white-space:nowrap; color:var(--text-muted); min-width:140px; }
.grid-cell { width:18px; height:20px; text-align:center; vertical-align:middle; }
.grid-badge { width:14px; height:14px; border-radius:3px; display:inline-block; font-size:8px; line-height:14px; text-align:center; color:#fff; }
.grid-badge-passed { background:var(--passed-badge); }
.grid-badge-failed { background:var(--failed-badge); }
.grid-badge-skipped { background:var(--skipped-badge); }
.grid-badge-pending { background:var(--pending-badge); }
.grid-layer-header { font-size:11px; font-weight:600; color:var(--text-muted); padding:6px 8px 2px; cursor:pointer; }
.grid-layer-header:hover { color:var(--text); }

/* Pipeline & Agent nodes */
.pipeline-node, .agent-node { cursor:pointer; transition: filter .15s; }
.pipeline-node:hover, .agent-node:hover { filter: brightness(1.1); }

/* Run selector bar (Gates tab) */
.run-selector { display:flex; align-items:center; gap:8px; padding:8px 20px; background:var(--surface); border-bottom:1px solid var(--border); font-size:12px; }
.run-nav-btn { background:none; border:1px solid var(--border); color:var(--text-muted); padding:3px 10px; border-radius:4px; cursor:pointer; font-size:13px; }
.run-nav-btn:hover:not(:disabled) { background:var(--surface-elevated); color:var(--text); }
.run-nav-btn:disabled { opacity:.3; cursor:default; }
.run-label { font-weight:600; color:var(--text); }
.run-meta { color:var(--text-muted); }
.run-live-badge { background:var(--running-badge); color:#fff; padding:1px 8px; border-radius:10px; font-size:10px; font-weight:600; animation: glow 2s ease-in-out infinite; }
.run-status-badge { padding:1px 8px; border-radius:10px; font-size:10px; font-weight:600; color:#fff; }
.run-status-passed { background:var(--passed-badge); }
.run-status-failed { background:var(--failed-badge); }

/* Clickable grid columns */
.grid-header-cell.clickable { cursor:pointer; }
.grid-header-cell.clickable:hover .grid-duration-bar { opacity:.7; }
.grid-header-cell.selected .grid-duration-bar { outline:2px solid var(--accent); outline-offset:1px; }
.grid-col-highlight td { background:var(--accent-muted)!important; }

/* Waiting state */
.waiting-msg { text-align:center; padding:80px 20px; color:var(--text-muted); }
.waiting-msg h2 { font-size:18px; margin-bottom:8px; color:var(--text); }
.waiting-msg p { font-size:13px; }
"""


def generate_js(gates_json, layers_json, pipeline_json, agents_json, repo_name, branch):
    return f"""
'use strict';

const GATES = {gates_json};
const LAYERS = {layers_json};
const PIPELINE_STAGES = {pipeline_json};
const AGENTS = {agents_json};
const REPO_NAME = {json.dumps(repo_name)};
const BRANCH = {json.dumps(branch)};
const POLL_MS = 2000;
const NODE_W = 180, NODE_H = 52, LAYER_GAP = 72, NODE_GAP = 16;

let currentState = null;
let historyData = [];
let activeTab = 'gates';
let selectedGate = null;
let selectedRunIndex = -1; // -1 = live/latest, 0+ = historical run index into historyData

// ── Layout computation (no dagre needed — fixed 7-layer structure) ──

function computeGatePositions() {{
    const layerGates = {{}};
    for (const [id, g] of Object.entries(GATES)) {{
        const l = g.layer;
        if (!layerGates[l]) layerGates[l] = [];
        layerGates[l].push(id);
    }}
    const positions = {{}};
    const sortedLayers = Object.keys(layerGates).map(Number).sort((a,b) => a-b);
    const maxInLayer = Math.max(...sortedLayers.map(l => layerGates[l].length));
    const totalW = maxInLayer * (NODE_W + NODE_GAP);

    for (let li = 0; li < sortedLayers.length; li++) {{
        const layer = sortedLayers[li];
        const gates = layerGates[layer];
        const layerW = gates.length * (NODE_W + NODE_GAP) - NODE_GAP;
        const startX = (totalW - layerW) / 2;
        const y = li * (NODE_H + LAYER_GAP);
        for (let gi = 0; gi < gates.length; gi++) {{
            positions[gates[gi]] = {{
                x: startX + gi * (NODE_W + NODE_GAP),
                y: y,
                layer: layer
            }};
        }}
    }}
    return {{ positions, totalW, totalH: sortedLayers.length * (NODE_H + LAYER_GAP) }};
}}

function computeEdges() {{
    const layers = {{}};
    for (const [id, g] of Object.entries(GATES)) {{
        const l = g.layer;
        if (!layers[l]) layers[l] = [];
        layers[l].push(id);
    }}
    const sorted = Object.keys(layers).map(Number).sort((a,b) => a-b);
    const edges = [];
    for (let i = 0; i < sorted.length - 1; i++) {{
        const fromLayer = layers[sorted[i]];
        const toLayer = layers[sorted[i+1]];
        // Connect center of from-layer to center of to-layer
        edges.push({{ from: fromLayer, to: toLayer, fromLayer: sorted[i], toLayer: sorted[i+1] }});
    }}
    return edges;
}}

// ── Rendering ──

const STATUS_COLORS = {{
    passed:  {{ border: '#10b981', badge: '#059669', bg: 'var(--passed-bg)',  icon: '\\u2713' }},
    running: {{ border: '#06b6d4', badge: '#0891b2', bg: 'var(--running-bg)', icon: '\\u25CC' }},
    failed:  {{ border: '#ef4444', badge: '#dc2626', bg: 'var(--failed-bg)',  icon: '\\u2717' }},
    skipped: {{ border: '#71717a', badge: '#52525b', bg: 'var(--skipped-bg)', icon: '\\u23ED' }},
    pending: {{ border: '#475569', badge: '#475569', bg: 'var(--pending-bg)', icon: '\\u25CB' }},
    warning: {{ border: '#f59e0b', badge: '#d97706', bg: 'var(--warning-bg)', icon: '\\u26A0' }},
}};

function isViewingHistory() {{
    return selectedRunIndex >= 0 && selectedRunIndex < historyData.length;
}}

function getViewedRun() {{
    if (isViewingHistory()) return historyData[selectedRunIndex];
    return null;
}}

function getGateStatus(gateId) {{
    // If viewing a historical run, use that run's gate data
    if (isViewingHistory()) {{
        const run = historyData[selectedRunIndex];
        if (run && run.gates && run.gates[gateId]) return run.gates[gateId];
        return 'pending';
    }}
    if (!currentState || !currentState.gates || !currentState.gates[gateId]) return 'pending';
    return currentState.gates[gateId].status || 'pending';
}}

function getGateInfo(gateId) {{
    // Historical runs only have status (no duration/findings detail)
    if (isViewingHistory()) {{
        const run = historyData[selectedRunIndex];
        const status = run && run.gates && run.gates[gateId] ? run.gates[gateId] : 'pending';
        return {{ status: status, name: GATES[gateId] ? GATES[gateId].name : gateId, duration_ms: null, findings: null, details: [] }};
    }}
    if (!currentState || !currentState.gates) return null;
    return currentState.gates[gateId] || null;
}}

function renderHeader() {{
    const hdr = document.getElementById('header');
    const st = currentState || {{}};
    const sc = st.scorecard || {{ grade: '?', score: 0, total: 31 }};
    const grade = sc.grade || '?';
    const gradeClass = grade.startsWith('A') ? 'grade-A' : grade.startsWith('B') ? 'grade-B' :
                       grade.startsWith('C') ? 'grade-C' : grade.startsWith('D') || grade.startsWith('F') ? 'grade-D' : 'grade-unknown';
    const status = st.status || 'idle';
    const dur = st.duration_ms ? (st.duration_ms / 1000).toFixed(1) + 's' : '--';
    const ts = st.timestamp ? new Date(st.timestamp).toLocaleTimeString() : '--';
    const statusDot = status === 'running' ? '<span class="sb-dot sb-dot-running"></span> Running' :
                      status === 'passed'  ? '<span class="sb-dot sb-dot-passed"></span> Passed' :
                      status === 'failed'  ? '<span class="sb-dot sb-dot-failed"></span> Failed' : '';

    hdr.innerHTML = `
        <div class="hdr-left">
            <svg class="hdr-logo" viewBox="0 0 28 28"><circle cx="14" cy="14" r="12" fill="none" stroke="var(--accent)" stroke-width="2"/><path d="M9 14l3 3 7-7" stroke="var(--accent)" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <span class="hdr-repo">${{REPO_NAME}}</span>
            <span class="hdr-branch">${{BRANCH}}</span>
            <span style="font-size:12px;color:var(--text-muted)">${{statusDot}}</span>
        </div>
        <div class="hdr-center">
            <span class="grade-badge ${{gradeClass}}">${{grade}}</span>
            <span class="hdr-score">${{sc.score}}/${{sc.total}} checks</span>
        </div>
        <div class="hdr-right">
            <span>${{ts}} &middot; ${{dur}}</span>
            <button class="theme-btn" onclick="toggleTheme()">&#9681; Theme</button>
        </div>
    `;
}}

function renderTabs() {{
    const nav = document.getElementById('tabs');
    const tabs = [
        {{ id: 'pipeline', label: '&#9672; Pipeline' }},
        {{ id: 'gates',    label: '&#8862; Gates' }},
        {{ id: 'agents',   label: '&#9776; Agents' }},
        {{ id: 'history',  label: '&#9638; History' }},
    ];
    nav.innerHTML = tabs.map(t =>
        `<div class="tab ${{t.id === activeTab ? 'active' : ''}}" onclick="switchTab('${{t.id}}')">${{t.label}}</div>`
    ).join('');
}}

function renderRunSelector() {{
    const total = historyData.length;
    const isLive = !isViewingHistory();
    const run = isLive ? currentState : getViewedRun();
    const runId = run ? (run.run_id || '?') : '?';
    const ts = run && run.timestamp ? new Date(run.timestamp).toLocaleTimeString() : '';
    const status = isLive ? (currentState ? currentState.status : 'idle') : (run ? (run.failed > 0 ? 'failed' : 'passed') : '');
    const dur = run ? ((run.duration_ms || 0) / 1000).toFixed(1) + 's' : '';
    const passed = isLive ? '' : (run ? run.passed + ' passed, ' + run.failed + ' failed' : '');

    const canPrev = isLive ? total > 0 : selectedRunIndex > 0;
    const canNext = isViewingHistory() && selectedRunIndex < total - 1;

    let statusBadge = '';
    if (isLive) {{
        statusBadge = '<span class="run-live-badge">&#9679; LIVE</span>';
    }} else if (status === 'passed') {{
        statusBadge = '<span class="run-status-badge run-status-passed">\\u2713 Passed</span>';
    }} else if (status === 'failed') {{
        statusBadge = '<span class="run-status-badge run-status-failed">\\u2717 Failed</span>';
    }}

    return `<div class="run-selector">
        <button class="run-nav-btn" onclick="navRun('prev')" ${{canPrev ? '' : 'disabled'}}>&#9664;</button>
        <button class="run-nav-btn" onclick="navRun('next')" ${{canNext ? '' : 'disabled'}}>&#9654;</button>
        <span class="run-label">Run #${{runId}}</span>
        ${{statusBadge}}
        <span class="run-meta">${{ts}} ${{dur ? '&middot; ' + dur : ''}} ${{passed ? '&middot; ' + passed : ''}}</span>
        ${{isViewingHistory() ? '<button class="run-nav-btn" onclick="navRun(\\x27live\\x27)" style="margin-left:auto;">&#9679; Back to Live</button>' : ''}}
    </div>`;
}}

function navRun(dir) {{
    const total = historyData.length;
    if (dir === 'live') {{
        selectedRunIndex = -1;
    }} else if (dir === 'prev') {{
        if (selectedRunIndex < 0) {{
            // From live, go to last historical run
            selectedRunIndex = total - 1;
        }} else if (selectedRunIndex > 0) {{
            selectedRunIndex--;
        }}
    }} else if (dir === 'next') {{
        if (selectedRunIndex >= 0 && selectedRunIndex < total - 1) {{
            selectedRunIndex++;
        }} else if (selectedRunIndex >= total - 1) {{
            selectedRunIndex = -1; // Back to live
        }}
    }}
    renderView();
    renderDetailPanel();
}}

function selectRun(index) {{
    selectedRunIndex = index;
    activeTab = 'gates';
    renderTabs();
    renderView();
    renderDetailPanel();
}}

function renderGatesView() {{
    const container = document.getElementById('dag-container');
    const {{ positions, totalW, totalH }} = computeGatePositions();
    const edges = computeEdges();
    const padLeft = 120; // Room for layer labels like "PRD Enforcement"
    const padRight = 40;
    const padTop = 20;
    const padBottom = 40;
    const svgW = totalW + padLeft + padRight;
    const svgH = totalH + padTop + padBottom;

    // Run selector bar + SVG
    let html = renderRunSelector();
    let svg = `<svg id="dag-canvas" viewBox="0 0 ${{svgW}} ${{svgH}}" width="${{svgW}}" height="${{svgH}}">`
    + '<defs><marker id="arrow" viewBox="0 0 10 7" refX="10" refY="3.5" markerWidth="8" markerHeight="6" orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="var(--border)"/></marker></defs>';

    // Layer labels
    const layerYs = {{}};
    for (const [id, pos] of Object.entries(positions)) {{
        if (!layerYs[pos.layer] || pos.y < layerYs[pos.layer]) layerYs[pos.layer] = pos.y;
    }}
    for (const [layer, y] of Object.entries(layerYs)) {{
        const name = LAYERS[layer] || 'Layer ' + layer;
        svg += `<text x="${{padLeft - 8}}" y="${{padTop + y + NODE_H/2}}" font-size="10" fill="var(--text-muted)" text-anchor="end" dominant-baseline="middle" font-weight="600">${{name}}</text>`;
    }}

    // Edges (layer-to-layer center connections)
    for (const edge of edges) {{
        const fromGates = edge.from;
        const toGates = edge.to;
        // Center of from layer bottom
        const fromXs = fromGates.map(id => positions[id].x + NODE_W/2);
        const fromY = positions[fromGates[0]].y + NODE_H;
        const fromCx = fromXs.reduce((a,b)=>a+b,0) / fromXs.length;
        // Center of to layer top
        const toXs = toGates.map(id => positions[id].x + NODE_W/2);
        const toY = positions[toGates[0]].y;
        const toCx = toXs.reduce((a,b)=>a+b,0) / toXs.length;

        const midY = (fromY + toY) / 2;
        // Determine edge status from target layer gates
        let edgeClass = '';
        const anyRunning = toGates.some(id => getGateStatus(id) === 'running');
        const anyFailed = toGates.some(id => getGateStatus(id) === 'failed');
        let edgeColor = 'var(--border)';
        if (anyRunning) {{ edgeColor = '#06b6d4'; edgeClass = 'edge-animated'; }}
        else if (anyFailed) {{ edgeColor = '#ef4444'; }}

        svg += `<path d="M${{padLeft+fromCx}},${{padTop+fromY}} C${{padLeft+fromCx}},${{padTop+midY}} ${{padLeft+toCx}},${{padTop+midY}} ${{padLeft+toCx}},${{padTop+toY}}" stroke="${{edgeColor}}" stroke-width="1.5" fill="none" class="${{edgeClass}}" marker-end="url(#arrow)"/>`;
    }}

    // Nodes
    for (const [id, pos] of Object.entries(positions)) {{
        const status = getGateStatus(id);
        const info = getGateInfo(id);
        const sc = STATUS_COLORS[status] || STATUS_COLORS.pending;
        const gate = GATES[id];
        const dur = info && info.duration_ms != null ? (info.duration_ms/1000).toFixed(1)+'s' : '';
        const findings = info && info.findings != null && info.findings > 0 ? info.findings + ' issues' : '';
        const meta = [dur, findings].filter(Boolean).join(' \\u00B7 ');
        const isSelected = selectedGate === id;
        const runClass = status === 'running' ? 'gate-running' : '';
        const selClass = isSelected ? 'selected' : '';

        svg += `<g class="gate-node ${{runClass}} ${{selClass}}" transform="translate(${{padLeft+pos.x}},${{padTop+pos.y}})" onclick="selectGate('${{id}}')" data-gate="${{id}}">`;
        svg += `<rect width="${{NODE_W}}" height="${{NODE_H}}" rx="6" fill="${{sc.bg}}" stroke="${{isSelected ? 'var(--accent)' : sc.border}}" stroke-width="${{isSelected ? 3 : 2}}"/>`;
        svg += `<rect width="4" height="${{NODE_H}}" rx="2" fill="${{sc.border}}"/>`;
        svg += `<text x="14" y="20" font-size="11" font-weight="700" fill="var(--text)">${{id}}</text>`;
        svg += `<text x="42" y="20" font-size="11" fill="var(--text)">${{gate.name}}</text>`;
        // Status badge
        svg += `<rect x="${{NODE_W-34}}" y="8" width="26" height="17" rx="8" fill="${{sc.badge}}"/>`;
        svg += `<text x="${{NODE_W-21}}" y="20" font-size="10" fill="#fff" text-anchor="middle">${{sc.icon}}</text>`;
        // Duration/findings
        if (meta) {{
            svg += `<text x="14" y="42" font-size="9" fill="var(--text-muted)">${{meta}}</text>`;
        }}
        svg += `</g>`;
    }}

    svg += '</svg>';
    container.innerHTML = html + svg;
}}

function renderPipelineView() {{
    const container = document.getElementById('dag-container');
    const nodeW = 160, nodeH = 64, gap = 40;
    const totalW = PIPELINE_STAGES.length * (nodeW + gap) - gap + 80;
    const totalH = nodeH + 80;

    let svg = `<svg id="dag-canvas" viewBox="0 0 ${{totalW}} ${{totalH}}" width="${{totalW}}" height="${{totalH}}">`;

    for (let i = 0; i < PIPELINE_STAGES.length; i++) {{
        const stage = PIPELINE_STAGES[i];
        const x = 40 + i * (nodeW + gap);
        const y = 20;
        const pipeState = currentState && currentState.pipeline && currentState.pipeline[stage.id];
        const status = pipeState ? pipeState.status : 'pending';
        const label = pipeState ? pipeState.label : '';
        const sc = STATUS_COLORS[status === 'completed' ? 'passed' : status] || STATUS_COLORS.pending;

        // Edge to next
        if (i < PIPELINE_STAGES.length - 1) {{
            const nx = 40 + (i+1) * (nodeW + gap);
            svg += `<line x1="${{x+nodeW}}" y1="${{y+nodeH/2}}" x2="${{nx}}" y2="${{y+nodeH/2}}" stroke="var(--border)" stroke-width="1.5" marker-end="url(#arrow)"/>`;
        }}

        const runClass = status === 'running' ? 'gate-running' : '';
        svg += `<g class="pipeline-node ${{runClass}}" transform="translate(${{x}},${{y}})">`;
        svg += `<rect width="${{nodeW}}" height="${{nodeH}}" rx="8" fill="${{sc.bg}}" stroke="${{sc.border}}" stroke-width="2"/>`;
        svg += `<text x="${{nodeW/2}}" y="24" font-size="13" font-weight="700" fill="var(--text)" text-anchor="middle">${{stage.icon}} ${{stage.name}}</text>`;
        svg += `<text x="${{nodeW/2}}" y="44" font-size="10" fill="var(--text-muted)" text-anchor="middle">${{label || status}}</text>`;
        svg += `</g>`;
    }}

    svg += '</svg>';
    container.innerHTML = svg;
}}

function renderAgentsView() {{
    const container = document.getElementById('dag-container');
    const nodeW = 170, nodeH = 56, gap = 24;
    const cols = 4;
    const rows = Math.ceil(AGENTS.length / cols);
    const totalW = cols * (nodeW + gap) - gap + 80;
    const totalH = rows * (nodeH + gap) - gap + 80;

    let svg = `<svg id="dag-canvas" viewBox="0 0 ${{totalW}} ${{totalH}}" width="${{totalW}}" height="${{totalH}}">`;

    for (let i = 0; i < AGENTS.length; i++) {{
        const agent = AGENTS[i];
        const col = i % cols;
        const row = Math.floor(i / cols);
        const x = 40 + col * (nodeW + gap);
        const y = 20 + row * (nodeH + gap);

        const agentState = currentState && currentState.agents && currentState.agents.agents && currentState.agents.agents[agent.id];
        const status = agentState && agentState.status === 'active' ? 'running' : 'pending';
        const task = agentState && agentState.task ? agentState.task : 'idle';
        const sc = STATUS_COLORS[status] || STATUS_COLORS.pending;

        svg += `<g class="agent-node" transform="translate(${{x}},${{y}})">`;
        svg += `<rect width="${{nodeW}}" height="${{nodeH}}" rx="6" fill="${{sc.bg}}" stroke="${{sc.border}}" stroke-width="2"/>`;
        svg += `<rect width="4" height="${{nodeH}}" rx="2" fill="${{sc.border}}"/>`;
        svg += `<text x="14" y="22" font-size="12" font-weight="600" fill="var(--text)">${{agent.name}}</text>`;
        svg += `<text x="14" y="40" font-size="10" fill="var(--text-muted)">${{task.substring(0,22)}}</text>`;
        svg += `<rect x="${{nodeW-34}}" y="8" width="26" height="17" rx="8" fill="${{sc.badge}}"/>`;
        svg += `<text x="${{nodeW-21}}" y="20" font-size="10" fill="#fff" text-anchor="middle">${{sc.icon}}</text>`;
        svg += `</g>`;
    }}

    svg += '</svg>';
    container.innerHTML = svg;
}}

function renderHistoryView() {{
    const container = document.getElementById('dag-container');
    if (!historyData || historyData.length === 0) {{
        container.innerHTML = '<div class="waiting-msg"><h2>No history yet</h2><p>Run <code>bash scripts/validate.sh</code> to record your first run.</p></div>';
        return;
    }}

    // Build Airflow-style Grid View
    const runs = historyData.slice(-30); // Show last 30 runs
    const allGateIds = Object.keys(GATES);
    const maxDur = Math.max(...runs.map(r => r.duration_ms || 1));

    // Compute actual indices in historyData for each displayed run
    const startIdx = Math.max(0, historyData.length - 30);
    let html = '<div class="grid-container"><p style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">Click a run column to view that run&#39;s gate DAG.</p><table class="grid-table"><thead><tr><th class="grid-gate-label"></th>';
    // Duration bar headers (clickable)
    for (let ri = 0; ri < runs.length; ri++) {{
        const run = runs[ri];
        const realIdx = startIdx + ri;
        html += '<th class="grid-header-cell clickable" onclick="selectRun(' + realIdx + ')" title="Run #' + run.run_id + ' — click to view"><div class="grid-duration-bar" style="height:' +
            Math.max(4, (run.duration_ms||0)/maxDur * 50) + 'px;background:' +
            (run.failed > 0 ? 'var(--failed-badge)' : 'var(--passed-badge)') + '"></div></th>';
    }}
    html += '</tr><tr><th class="grid-gate-label" style="font-size:10px;color:var(--text-muted)"></th>';
    for (let ri = 0; ri < runs.length; ri++) {{
        const run = runs[ri];
        const realIdx = startIdx + ri;
        html += '<th class="grid-header-cell clickable" onclick="selectRun(' + realIdx + ')" style="font-size:9px;color:var(--text-muted);cursor:pointer">' + run.run_id + '</th>';
    }}
    html += '</tr></thead><tbody>';

    // Group by layer
    let currentLayer = 0;
    for (const gateId of allGateIds) {{
        const gate = GATES[gateId];
        if (gate.layer !== currentLayer) {{
            currentLayer = gate.layer;
            const layerName = LAYERS[currentLayer] || 'Layer ' + currentLayer;
            html += '<tr><td class="grid-layer-header" colspan="' + (runs.length+1) + '">&#9660; ' + layerName + '</td></tr>';
        }}
        html += '<tr><td class="grid-gate-label">' + gateId + ' ' + gate.name + '</td>';
        for (const run of runs) {{
            const gateStatus = run.gates && run.gates[gateId] ? run.gates[gateId] : 'pending';
            const icon = gateStatus === 'passed' ? '\\u2713' : gateStatus === 'failed' ? '\\u2717' :
                         gateStatus === 'skipped' ? '\\u2014' : '\\u25CB';
            html += '<td class="grid-cell"><span class="grid-badge grid-badge-' + gateStatus + '">' + icon + '</span></td>';
        }}
        html += '</tr>';
    }}

    html += '</tbody></table></div>';
    container.innerHTML = html;
}}

function renderDetailPanel() {{
    const panel = document.getElementById('detail-panel');
    if (!selectedGate) {{
        panel.classList.add('hidden');
        return;
    }}
    panel.classList.remove('hidden');
    const gate = GATES[selectedGate];
    const info = getGateInfo(selectedGate);
    const status = getGateStatus(selectedGate);
    const sc = STATUS_COLORS[status] || STATUS_COLORS.pending;
    const dur = info && info.duration_ms != null ? (info.duration_ms/1000).toFixed(1)+'s' : '--';
    const findings = info && info.findings != null ? info.findings : 0;
    const details = info && info.details ? info.details : [];

    let html = `
        <div class="dp-header">
            <span class="dp-title">${{selectedGate}} &mdash; ${{gate.name}}</span>
            <button class="dp-close" onclick="selectGate(null)">&times;</button>
        </div>
        <span class="dp-badge" style="background:${{sc.badge}}">${{sc.icon}} ${{status}}</span>
        <div class="dp-stat">Duration: ${{dur}}</div>
        <div class="dp-stat">Findings: ${{findings}}</div>
    `;

    if (details.length > 0) {{
        html += '<div class="dp-section"><div class="dp-section-title">Findings</div>';
        for (const d of details) {{
            html += '<div class="dp-finding">' + d + '</div>';
        }}
        html += '</div>';
    }}

    // History sparkline for this gate
    if (historyData.length > 1) {{
        html += '<div class="dp-section"><div class="dp-section-title">Recent History</div><div style="display:flex;gap:2px;align-items:flex-end;height:24px;">';
        const recent = historyData.slice(-20);
        for (const run of recent) {{
            const gs = run.gates && run.gates[selectedGate] ? run.gates[selectedGate] : 'pending';
            const color = gs === 'passed' ? 'var(--passed-badge)' : gs === 'failed' ? 'var(--failed-badge)' : 'var(--skipped-badge)';
            html += '<div style="width:6px;height:' + (gs === 'passed' ? '20' : gs === 'failed' ? '20' : '8') + 'px;background:' + color + ';border-radius:1px;" title="Run ' + run.run_id + ': ' + gs + '"></div>';
        }}
        html += '</div></div>';
    }}

    panel.innerHTML = html;
}}

function renderStatusBar() {{
    const footer = document.querySelector('footer');
    if (!currentState && !isViewingHistory()) {{
        footer.innerHTML = '<span>Waiting for first validation run...</span>';
        return;
    }}
    // Count statuses across all known gates using the view-aware getGateStatus
    const allGateIds = Object.keys(GATES);
    let passed=0, failed=0, skipped=0, running=0, pending=0;
    let dots = '';
    for (const id of allGateIds) {{
        const status = getGateStatus(id);
        if (status==='passed') passed++;
        else if (status==='failed') failed++;
        else if (status==='skipped') skipped++;
        else if (status==='running') running++;
        else pending++;
        const cls = 'sb-dot sb-dot-' + status;
        dots += '<span class="' + cls + '" title="' + id + ': ' + status + '"></span>';
    }}
    const total = passed + failed;
    footer.innerHTML = `
        <div class="sb-gates">${{dots}}</div>
        <span>${{passed}} passed, ${{failed}} failed, ${{skipped}} skipped, ${{running}} running &mdash; ${{total}} total</span>
    `;
}}

// ── Interaction ──

function switchTab(tab) {{
    activeTab = tab;
    selectedGate = null;
    if (tab !== 'gates') selectedRunIndex = -1; // Reset to live when leaving gates
    renderTabs();
    renderView();
    renderDetailPanel();
}}

function selectGate(id) {{
    selectedGate = selectedGate === id ? null : id;
    renderView();
    renderDetailPanel();
}}

function renderView() {{
    if (activeTab === 'gates') renderGatesView();
    else if (activeTab === 'pipeline') renderPipelineView();
    else if (activeTab === 'agents') renderAgentsView();
    else if (activeTab === 'history') renderHistoryView();
}}

function toggleTheme() {{
    const html = document.documentElement;
    const current = html.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('harness-theme', next);
}}

// ── Polling ──

async function poll() {{
    try {{
        const resp = await fetch('dashboard_state.json?t=' + Date.now());
        if (resp.ok) {{
            const newState = await resp.json();
            const changed = JSON.stringify(newState) !== JSON.stringify(currentState);
            currentState = newState;
            if (changed) {{
                renderHeader();
                renderView();
                renderStatusBar();
                renderDetailPanel();
            }}
        }}
    }} catch (e) {{
        // State file not ready yet
    }}

    try {{
        const resp = await fetch('history/runs.json?t=' + Date.now());
        if (resp.ok) {{
            historyData = await resp.json();
        }}
    }} catch (e) {{
        // History not available yet
    }}
}}

// ── Init ──

(function init() {{
    // Apply saved theme
    const saved = localStorage.getItem('harness-theme');
    if (saved) document.documentElement.setAttribute('data-theme', saved);

    renderHeader();
    renderTabs();
    renderView();
    renderStatusBar();

    // Show waiting message if no state
    if (!currentState) {{
        document.getElementById('dag-container').innerHTML =
            '<div class="waiting-msg"><h2>Harness Dashboard</h2>' +
            '<p>Run <code>bash scripts/validate.sh</code> in another terminal to see gates light up.</p></div>';
    }}

    // Keyboard navigation (left/right arrows for run history)
    document.addEventListener('keydown', (e) => {{
        if (activeTab === 'gates') {{
            if (e.key === 'ArrowLeft') {{ navRun('prev'); e.preventDefault(); }}
            if (e.key === 'ArrowRight') {{ navRun('next'); e.preventDefault(); }}
            if (e.key === 'Escape' && isViewingHistory()) {{ navRun('live'); e.preventDefault(); }}
        }}
    }});

    // Start polling
    poll();
    setInterval(poll, POLL_MS);
}})();
"""


def generate_html():
    repo_name, branch = get_repo_info()
    gates_json = json.dumps(GATES)
    layers_json = json.dumps({str(k): v for k, v in LAYER_NAMES.items()})
    pipeline_json = json.dumps(PIPELINE_STAGES)
    agents_json = json.dumps(AGENTS)

    css = generate_css()
    js = generate_js(gates_json, layers_json, pipeline_json, agents_json, repo_name, branch)

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Harness Dashboard — {repo_name}</title>
    <style>{css}</style>
</head>
<body>
    <div id="app">
        <header id="header"></header>
        <nav id="tabs"></nav>
        <main>
            <div id="dag-container"></div>
            <aside id="detail-panel" class="hidden"></aside>
        </main>
        <footer></footer>
    </div>
    <script>{js}</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Generate Harness DAG Dashboard")
    parser.add_argument("--open", action="store_true", help="Open in browser")
    parser.add_argument("--serve", action="store_true", help="Start HTTP server")
    parser.add_argument("--port", type=int, default=8099, help="Port (default: 8099)")
    args = parser.parse_args()

    HARNESS_DIR.mkdir(parents=True, exist_ok=True)
    (HARNESS_DIR / "history").mkdir(parents=True, exist_ok=True)

    html = generate_html()
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    size = len(html)
    lines = html.count("\n")
    print(f"Dashboard generated: {OUTPUT_FILE} ({size:,} bytes, {lines} lines)")

    if args.serve or args.open:
        os.chdir(str(HARNESS_DIR))

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *a):
                pass  # Suppress request logs

        server = http.server.HTTPServer(("", args.port), QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://localhost:{args.port}/dashboard.html"
        print(f"Serving at {url}")

        pid_file = HARNESS_DIR / "dashboard.pid"
        pid_file.write_text(str(os.getpid()))

        if args.open:
            webbrowser.open(url)

        try:
            print("Press Ctrl+C to stop")
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping dashboard server")
            server.shutdown()


if __name__ == "__main__":
    main()
