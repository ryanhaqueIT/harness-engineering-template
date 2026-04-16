# Harness DAG Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an Airflow-inspired DAG dashboard that visualizes all 25 validation gates in real-time as a self-contained HTML file with zero dependencies.

**Architecture:** A Python script generates a single HTML file (~1000 lines) with inline CSS/JS/SVG. validate.sh writes gate status to a JSON file after each gate. The HTML polls the JSON every 2 seconds and re-renders the DAG. A bash launcher starts a local HTTP server and opens the browser.

**Tech Stack:** Python 3.7+ stdlib only (json, pathlib, http.server, webbrowser), inline dagre.js for graph layout, SVG for rendering, CSS for Airflow-style theming.

**Spec:** `docs/superpowers/specs/2026-04-16-harness-dag-dashboard-design.md`

---

## File Structure

```
scripts/
  harness_dashboard.py    # NEW — Generates .harness/dashboard.html
  dashboard_hooks.sh      # NEW — Bash functions for validate.sh state emission
  dashboard.sh            # NEW — Launcher: generate + serve + open browser
  validate.sh             # MODIFY — Source dashboard_hooks.sh, emit state per gate
```

---

### Task 1: Create `dashboard_hooks.sh` — State Emission Functions

**Files:**
- Create: `scripts/dashboard_hooks.sh`

This is the bridge between validate.sh and the dashboard. It writes JSON state after each gate runs.

- [ ] **Step 1: Create the state emission script**

```bash
#!/usr/bin/env bash
# dashboard_hooks.sh — Emit gate status to .harness/dashboard_state.json
# Sourced by validate.sh. If this file doesn't exist, validate.sh works unchanged.

DASHBOARD_STATE_FILE="${REPO_ROOT:-.}/.harness/dashboard_state.json"
DASHBOARD_HISTORY_FILE="${REPO_ROOT:-.}/.harness/history/runs.json"
_DASHBOARD_RUN_START=""

init_dashboard_state() {
    mkdir -p "$(dirname "$DASHBOARD_STATE_FILE")"
    mkdir -p "$(dirname "$DASHBOARD_HISTORY_FILE")"
    _DASHBOARD_RUN_START=$(python3 -c "import time; print(int(time.time()*1000))")

    python3 -c "
import json, datetime, pathlib

state = {
    'version': 1,
    'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
    'run_id': 0,
    'status': 'running',
    'duration_ms': 0,
    'gates': {},
    'scorecard': {'grade': '?', 'score': 0, 'total': 31},
    'ratchet': {}
}

# Read previous run_id to increment
history_path = pathlib.Path('${DASHBOARD_HISTORY_FILE}')
if history_path.exists():
    try:
        runs = json.loads(history_path.read_text())
        if runs:
            state['run_id'] = runs[-1].get('run_id', 0) + 1
    except (json.JSONDecodeError, KeyError):
        state['run_id'] = 1
else:
    state['run_id'] = 1

json.dump(state, open('${DASHBOARD_STATE_FILE}', 'w'), indent=2)
"
}

emit_gate_start() {
    local gate_id="$1"
    local gate_name="${2:-$gate_id}"
    local layer="${3:-0}"

    python3 -c "
import json, datetime
try:
    state = json.load(open('${DASHBOARD_STATE_FILE}'))
except (FileNotFoundError, json.JSONDecodeError):
    state = {'version': 1, 'gates': {}}
state['gates']['${gate_id}'] = {
    'status': 'running',
    'name': '${gate_name}',
    'layer': ${layer},
    'duration_ms': None,
    'findings': None,
    'details': []
}
state['timestamp'] = datetime.datetime.utcnow().isoformat() + 'Z'
json.dump(state, open('${DASHBOARD_STATE_FILE}', 'w'), indent=2)
"
}

emit_gate_end() {
    local gate_id="$1"
    local exit_code="$2"
    local duration_ms="${3:-0}"
    local findings="${4:-0}"
    local status="passed"

    if [ "$exit_code" -ne 0 ]; then
        status="failed"
    fi

    python3 -c "
import json, datetime
try:
    state = json.load(open('${DASHBOARD_STATE_FILE}'))
except (FileNotFoundError, json.JSONDecodeError):
    state = {'version': 1, 'gates': {}}
if '${gate_id}' not in state.get('gates', {}):
    state.setdefault('gates', {})['${gate_id}'] = {}
state['gates']['${gate_id}']['status'] = '${status}'
state['gates']['${gate_id}']['duration_ms'] = ${duration_ms}
state['gates']['${gate_id}']['findings'] = ${findings}
state['timestamp'] = datetime.datetime.utcnow().isoformat() + 'Z'
json.dump(state, open('${DASHBOARD_STATE_FILE}', 'w'), indent=2)
"
}

emit_gate_skip() {
    local gate_id="$1"
    local gate_name="${2:-$gate_id}"
    local layer="${3:-0}"
    local reason="${4:-skipped}"

    python3 -c "
import json, datetime
try:
    state = json.load(open('${DASHBOARD_STATE_FILE}'))
except (FileNotFoundError, json.JSONDecodeError):
    state = {'version': 1, 'gates': {}}
state.setdefault('gates', {})['${gate_id}'] = {
    'status': 'skipped',
    'name': '${gate_name}',
    'layer': ${layer},
    'duration_ms': 0,
    'findings': 0,
    'details': ['${reason}']
}
state['timestamp'] = datetime.datetime.utcnow().isoformat() + 'Z'
json.dump(state, open('${DASHBOARD_STATE_FILE}', 'w'), indent=2)
"
}

finalize_dashboard_run() {
    local pass_count="$1"
    local fail_count="$2"
    local skip_count="$3"

    local end_time
    end_time=$(python3 -c "import time; print(int(time.time()*1000))")
    local duration_ms=$((end_time - ${_DASHBOARD_RUN_START:-$end_time}))

    local final_status="passed"
    if [ "$fail_count" -gt 0 ]; then
        final_status="failed"
    fi

    python3 -c "
import json, datetime, pathlib

# Update state file
state_path = pathlib.Path('${DASHBOARD_STATE_FILE}')
try:
    state = json.loads(state_path.read_text())
except (FileNotFoundError, json.JSONDecodeError):
    state = {'version': 1, 'gates': {}, 'run_id': 1}

state['status'] = '${final_status}'
state['duration_ms'] = ${duration_ms}
state['timestamp'] = datetime.datetime.utcnow().isoformat() + 'Z'
state_path.write_text(json.dumps(state, indent=2))

# Append to history
history_path = pathlib.Path('${DASHBOARD_HISTORY_FILE}')
try:
    runs = json.loads(history_path.read_text()) if history_path.exists() else []
except json.JSONDecodeError:
    runs = []

gate_statuses = {gid: g.get('status', 'pending') for gid, g in state.get('gates', {}).items()}
runs.append({
    'run_id': state.get('run_id', len(runs) + 1),
    'timestamp': state['timestamp'],
    'duration_ms': ${duration_ms},
    'passed': ${pass_count},
    'failed': ${fail_count},
    'skipped': ${skip_count},
    'total_gates': ${pass_count} + ${fail_count},
    'gates': gate_statuses
})

# Keep max 100 runs
if len(runs) > 100:
    runs = runs[-100:]

history_path.parent.mkdir(parents=True, exist_ok=True)
history_path.write_text(json.dumps(runs, indent=2))
"
}
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x scripts/dashboard_hooks.sh`

- [ ] **Step 3: Commit**

```bash
git add scripts/dashboard_hooks.sh
git commit -m "feat(dashboard): add state emission hooks for validate.sh"
```

---

### Task 2: Modify `validate.sh` — Hook In Dashboard State Emission

**Files:**
- Modify: `scripts/validate.sh`

Wire validate.sh to emit state. The approach: source `dashboard_hooks.sh` with `|| true` so validate.sh works unchanged if the hooks file is missing. Wrap the existing `check()` and `skip()` functions to also emit dashboard state.

- [ ] **Step 1: Add dashboard hook sourcing after the REPO_ROOT line (line 29)**

After `REPO_ROOT="$(git rev-parse --show-toplevel)"` add:

```bash
# Dashboard state emission (optional — works without it)
_DASHBOARD_HOOKS="${REPO_ROOT}/scripts/dashboard_hooks.sh"
if [ -f "$_DASHBOARD_HOOKS" ]; then
    source "$_DASHBOARD_HOOKS"
    _DASHBOARD_ACTIVE=true
else
    _DASHBOARD_ACTIVE=false
fi
```

- [ ] **Step 2: Replace the `check()` function to also emit state**

Replace the existing `check()` function (lines 31-42) with:

```bash
# Gate metadata for dashboard (gate_id -> name, layer)
declare -A GATE_META

check() {
    local name="$1"
    shift
    # Extract gate ID from name like "  [B1] Ruff lint" -> "B1"
    local gate_id=""
    if [[ "$name" =~ \[([A-Z][0-9]+)\] ]]; then
        gate_id="${BASH_REMATCH[1]}"
    fi
    local gate_layer="${GATE_META[$gate_id]+${GATE_META[$gate_id]}}"

    if [ "$_DASHBOARD_ACTIVE" = true ] && [ -n "$gate_id" ]; then
        emit_gate_start "$gate_id" "$name" "${gate_layer:-0}"
    fi

    local start_ms
    start_ms=$(python3 -c "import time; print(int(time.time()*1000))" 2>/dev/null || echo "0")

    echo "── $name"
    local output exit_code
    output=$("$@" 2>&1) && exit_code=0 || exit_code=$?

    local end_ms
    end_ms=$(python3 -c "import time; print(int(time.time()*1000))" 2>/dev/null || echo "0")
    local duration_ms=$((end_ms - start_ms))

    if [ "$exit_code" -eq 0 ]; then
        echo -e "   ${GREEN}✓ PASS${NC}"
        ((PASS++))
        if [ "$_DASHBOARD_ACTIVE" = true ] && [ -n "$gate_id" ]; then
            emit_gate_end "$gate_id" 0 "$duration_ms" 0
        fi
    else
        echo "$output"
        echo -e "   ${RED}✗ FAIL${NC}"
        ((FAIL++))
        # Count findings (non-empty lines in output)
        local findings
        findings=$(echo "$output" | grep -c '.' 2>/dev/null || echo "0")
        if [ "$_DASHBOARD_ACTIVE" = true ] && [ -n "$gate_id" ]; then
            emit_gate_end "$gate_id" 1 "$duration_ms" "$findings"
        fi
    fi
}
```

- [ ] **Step 3: Replace the `skip()` function to also emit state**

Replace the existing `skip()` function (lines 44-47) with:

```bash
skip() {
    local name="$1"
    local reason="$2"
    local gate_id=""
    if [[ "$name" =~ \[([A-Z][0-9]+)\] ]]; then
        gate_id="${BASH_REMATCH[1]}"
    fi

    echo -e "── $name ${YELLOW}(skipped — $reason)${NC}"
    ((SKIP++))

    if [ "$_DASHBOARD_ACTIVE" = true ] && [ -n "$gate_id" ]; then
        local gate_layer="${GATE_META[$gate_id]+${GATE_META[$gate_id]}}"
        emit_gate_skip "$gate_id" "$name" "${gate_layer:-0}" "$reason"
    fi
}
```

- [ ] **Step 4: Add gate layer metadata after the function definitions**

After the `skip()` function, before `echo "═══..."`, add:

```bash
# Gate layer metadata for dashboard visualization
GATE_META=( [B1]=1 [B2]=1 [B3]=3 [B4]=2 [B5]=2 [B6]=2 [B7]=2 [B8]=2
            [F1]=4 [F2]=4 [F3]=4 [F4]=4 [F5]=4 [F6]=5 [F7]=5
            [I1]=5 [I2]=5 [O1]=6
            [X1]=7 [X2]=7 [X3]=7 [X4]=7 [X5]=7 [X6]=7 [X7]=7 [R1]=7 )
```

- [ ] **Step 5: Add init_dashboard_state call before the first gate**

After the header echo block (`echo "═══..."`) add:

```bash
# Initialize dashboard state for this run
if [ "$_DASHBOARD_ACTIVE" = true ]; then
    init_dashboard_state
fi
```

- [ ] **Step 6: Add finalize call at the end before the exit**

Replace the RESULTS section (lines 396-411) with:

```bash
TOTAL=$((PASS + FAIL))
echo "═══════════════════════════════════════════════════"
echo " Results: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped (${TOTAL} total)"
echo "═══════════════════════════════════════════════════"

# Finalize dashboard state
if [ "$_DASHBOARD_ACTIVE" = true ]; then
    finalize_dashboard_run "$PASS" "$FAIL" "$SKIP"
fi

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}VALIDATION FAILED — fix errors above before committing${NC}"
    echo ""
    echo "RULE: Nothing gets committed until this script exits 0."
    echo "      No exceptions. No shortcuts. Run this again after fixing."
    exit 1
else
    echo -e "${GREEN}ALL GATES PASSED — ready to commit${NC}"
    exit 0
fi
```

- [ ] **Step 7: Test the modified validate.sh**

Run: `bash scripts/validate.sh`
Expected: Same gate output as before, PLUS `.harness/dashboard_state.json` is created with gate results.

Run: `cat .harness/dashboard_state.json | python3 -m json.tool`
Expected: Valid JSON with gates and their statuses.

Run: `cat .harness/history/runs.json | python3 -m json.tool`
Expected: Array with one run entry.

- [ ] **Step 8: Commit**

```bash
git add scripts/validate.sh
git commit -m "feat(dashboard): wire validate.sh to emit gate state for live dashboard"
```

---

### Task 3: Create `harness_dashboard.py` — HTML Generator

**Files:**
- Create: `scripts/harness_dashboard.py`

This is the main script. It generates a self-contained HTML file with inline CSS, inline JS (including dagre), and SVG rendering. The HTML polls `dashboard_state.json` every 2 seconds.

This is a large file (~600 lines of Python generating ~1000 lines of HTML). The approach: Python string templates with f-strings, no external template engine.

- [ ] **Step 1: Create the generator script**

Create `scripts/harness_dashboard.py` with the full implementation. The file structure is:

```python
#!/usr/bin/env python3
"""Generate the Harness DAG Dashboard — a self-contained HTML file."""

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

# === DAGRE.JS MINIFIED ===
# Inline dagre.js (~30KB) for graph layout
# Source: https://github.com/dagrejs/dagre (MIT license)
DAGRE_JS = """... (inline minified dagre.js) ..."""

# === GATE DEFINITIONS ===
GATES = {
    "B1": {"name": "Lint", "layer": 1},
    "B2": {"name": "Format", "layer": 1},
    "B3": {"name": "Tests", "layer": 3},
    "B4": {"name": "Import Boundaries", "layer": 2},
    "B5": {"name": "Golden Principles", "layer": 2},
    "B6": {"name": "Architecture", "layer": 2},
    "B7": {"name": "Type Check", "layer": 2},
    "B8": {"name": "Wiring", "layer": 2},
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

# Layer edges: each layer flows into the next
LAYER_EDGES = [
    (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7)
]


def get_repo_info():
    """Get repo name and branch from git."""
    try:
        name = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(REPO_ROOT), stderr=subprocess.DEVNULL
        ).decode().strip().split("/")[-1].split("\\")[-1]
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
    """Return the full inline CSS string."""
    return """
/* ... Full CSS with Airflow color tokens, layout, dark mode ... */
/* See Step 2 for the complete CSS */
"""


def generate_js(gates_json, repo_name, branch):
    """Return the full inline JS string including dagre and rendering."""
    return f"""
/* ... Full JS with dagre, SVG rendering, polling, tabs, interactions ... */
/* See Step 3 for the complete JS */
"""


def generate_html():
    """Generate the complete dashboard HTML."""
    repo_name, branch = get_repo_info()
    gates_json = json.dumps(GATES)

    html = f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Harness Dashboard — {repo_name}</title>
    <style>{generate_css()}</style>
</head>
<body>
    <div id="app">
        <header id="header"></header>
        <nav id="tabs"></nav>
        <main id="main">
            <div id="dag-container">
                <svg id="dag-canvas"></svg>
            </div>
            <aside id="detail-panel" class="hidden"></aside>
        </main>
        <footer id="status-bar"></footer>
    </div>
    <script>{DAGRE_JS}</script>
    <script>{generate_js(gates_json, repo_name, branch)}</script>
</body>
</html>"""
    return html


def main():
    parser = argparse.ArgumentParser(description="Generate Harness DAG Dashboard")
    parser.add_argument("--open", action="store_true", help="Open in browser after generating")
    parser.add_argument("--serve", action="store_true", help="Start HTTP server")
    parser.add_argument("--port", type=int, default=8099, help="HTTP server port (default: 8099)")
    args = parser.parse_args()

    HARNESS_DIR.mkdir(parents=True, exist_ok=True)

    html = generate_html()
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"Dashboard generated: {OUTPUT_FILE}")

    if args.serve or args.open:
        # Start HTTP server in background
        os.chdir(str(HARNESS_DIR))
        handler = http.server.SimpleHTTPRequestHandler
        server = http.server.HTTPServer(("", args.port), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"Serving at http://localhost:{args.port}/dashboard.html")

        # Write PID for cleanup
        pid_file = HARNESS_DIR / "dashboard.pid"
        pid_file.write_text(str(os.getpid()))

        if args.open:
            webbrowser.open(f"http://localhost:{args.port}/dashboard.html")

        try:
            print("Press Ctrl+C to stop")
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down")
            server.shutdown()
    

if __name__ == "__main__":
    main()
```

This is the skeleton. The actual CSS and JS are large. They will be implemented in Steps 2 and 3 below.

- [ ] **Step 2: Implement the full CSS (generate_css function)**

The CSS implements Airflow's color system, layout grid, node styles, edge animations, dark/light themes, Grid View, and detail panel. ~250 lines. Key sections:

- CSS custom properties for theme colors (light + dark)
- `.node` styling with state-colored borders
- `.node-running` with glow animation
- `.edge` and `.edge-animated` with dash animation
- `#header` flex layout
- `#tabs` horizontal tab bar with active bottom border
- `#dag-container` with overflow scroll
- `#detail-panel` slide-in from right
- `.grid-cell` for 14x14px colored badges
- `@media` queries for responsive behavior
- Grade badge colors (A=green, B=blue, C=yellow, D/F=red)

- [ ] **Step 3: Implement the full JS (generate_js function)**

The JS handles: dagre layout, SVG node/edge rendering, polling, tab switching, click interactions, Grid View, detail panel, theme toggle. ~500 lines. Key sections:

- `GATES` constant (injected from Python)
- `layoutDAG(gates)` — creates dagre graph, computes positions
- `renderNodes(g, gatesState)` — SVG rect + text + badge per gate
- `renderEdges(g, gatesState)` — SVG path with smoothstep curves per edge
- `renderHeader(state)` — grade badge, ratchet, timestamp
- `renderStatusBar(state)` — bottom bar with pass/fail summary
- `renderGridView(runs)` — Airflow Grid View with 14x14 cells
- `renderDetailPanel(gateId, state)` — right panel with findings
- `poll()` — fetch dashboard_state.json, diff and re-render
- `switchTab(tab)` — Pipeline/Gates/Agents/History view switching
- Theme toggle with localStorage persistence
- Pan/zoom on SVG canvas via mouse events

- [ ] **Step 4: Inline dagre.js**

Download dagre.js minified and embed it as the DAGRE_JS constant. The minified bundle is ~30KB. It includes dagre + graphlib.

Source: `https://unpkg.com/@dagrejs/dagre@1.1.4/dist/dagre.min.js` (MIT license)

For the implementation, we'll fetch it once and inline it as a Python string constant.

- [ ] **Step 5: Test generation**

Run: `python3 scripts/harness_dashboard.py`
Expected: `.harness/dashboard.html` is created, ~1000 lines.

Run: `python3 -c "html = open('.harness/dashboard.html').read(); print(f'Size: {len(html)} bytes, Lines: {html.count(chr(10))}')" `
Expected: Size > 30000 bytes, Lines > 500.

- [ ] **Step 6: Test in browser**

Run: `python3 scripts/harness_dashboard.py --serve --open`
Expected: Browser opens, shows dashboard with all gates in "pending" state (gray).

Run (in another terminal): `bash scripts/validate.sh`
Expected: Gates in browser update from gray to green/red/yellow within 2 seconds of each gate completing.

- [ ] **Step 7: Commit**

```bash
git add scripts/harness_dashboard.py
git commit -m "feat(dashboard): add Airflow-inspired DAG dashboard generator"
```

---

### Task 4: Create `dashboard.sh` — One-Command Launcher

**Files:**
- Create: `scripts/dashboard.sh`

- [ ] **Step 1: Create the launcher script**

```bash
#!/usr/bin/env bash
# dashboard.sh — Launch the Harness DAG Dashboard
# Usage: bash scripts/dashboard.sh
#
# Opens an Airflow-inspired DAG visualization in your browser.
# Run validate.sh in another terminal to see gates light up in real-time.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HARNESS_DIR="${REPO_ROOT}/.harness"
PORT="${HARNESS_PORT:-8099}"
PID_FILE="${HARNESS_DIR}/dashboard.pid"

# Kill existing server if running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || echo "")
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        kill "$OLD_PID" 2>/dev/null || true
        sleep 0.5
    fi
    rm -f "$PID_FILE"
fi

# Generate dashboard HTML
echo "Generating dashboard..."
python3 "${SCRIPT_DIR}/harness_dashboard.py"

# Start HTTP server in background
cd "$HARNESS_DIR"
python3 -m http.server "$PORT" &>/dev/null &
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

# Open browser (cross-platform)
URL="http://localhost:${PORT}/dashboard.html"
if command -v open &>/dev/null; then
    open "$URL"
elif command -v xdg-open &>/dev/null; then
    xdg-open "$URL"
elif command -v start &>/dev/null; then
    start "$URL"
else
    echo "Open $URL in your browser"
fi

echo ""
echo "═══════════════════════════════════════════════════"
echo " Harness Dashboard running at $URL"
echo " PID: $SERVER_PID"
echo "═══════════════════════════════════════════════════"
echo ""
echo " Now run in another terminal:"
echo "   bash scripts/validate.sh"
echo ""
echo " Watch the gates light up in real-time!"
echo ""
echo " To stop: kill $SERVER_PID"
echo "═══════════════════════════════════════════════════"

# Wait for server (so Ctrl+C stops it)
wait "$SERVER_PID" 2>/dev/null || true
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x scripts/dashboard.sh`

- [ ] **Step 3: Test it**

Run: `bash scripts/dashboard.sh`
Expected: Browser opens with dashboard. Terminal shows server PID and instructions.

Press Ctrl+C in the terminal.
Expected: Server stops. No orphan processes.

- [ ] **Step 4: Commit**

```bash
git add scripts/dashboard.sh
git commit -m "feat(dashboard): add one-command dashboard launcher"
```

---

### Task 5: Integration Test — Full End-to-End

**Files:**
- No new files — testing the integration

- [ ] **Step 1: Start the dashboard**

Run: `bash scripts/dashboard.sh &`
Expected: Browser opens with dashboard, all gates pending/gray.

- [ ] **Step 2: Run validation and watch the dashboard**

Run: `bash scripts/validate.sh`
Expected:
1. In the browser, gates turn from gray to green/red one by one
2. The header updates with pass/fail counts
3. The status bar shows final results
4. Dashboard state JSON is populated

- [ ] **Step 3: Run validation again to populate history**

Run: `bash scripts/validate.sh` (second time)
Expected: `.harness/history/runs.json` now has 2 entries. Click "History" tab in dashboard to see Grid View with 2 columns.

- [ ] **Step 4: Test dark/light mode toggle**

Click the theme toggle button in the header.
Expected: Colors flip between light and dark. All nodes, edges, and text remain readable.

- [ ] **Step 5: Test detail panel**

Click any gate node in the Gates tab.
Expected: Right panel slides in showing gate name, status, duration, findings.

- [ ] **Step 6: Clean up**

Run: `kill $(cat .harness/dashboard.pid)` to stop the server.

- [ ] **Step 7: Verify no regressions in validate.sh**

Run: `bash scripts/validate.sh`
Expected: Same pass/fail/skip counts as before the dashboard changes. The dashboard hooks should not affect gate results.

- [ ] **Step 8: Commit all remaining changes**

```bash
git add -A
git commit -m "feat(dashboard): complete Airflow-inspired DAG dashboard with live gate visualization"
```

---

## Summary

| Task | What | Files | Effort |
|------|------|-------|--------|
| 1 | Dashboard hooks (state emission) | `scripts/dashboard_hooks.sh` (new) | 15 min |
| 2 | Wire validate.sh to emit state | `scripts/validate.sh` (modify) | 20 min |
| 3 | HTML generator (the big one) | `scripts/harness_dashboard.py` (new) | 2-3 hours |
| 4 | One-command launcher | `scripts/dashboard.sh` (new) | 10 min |
| 5 | Integration test | No new files | 20 min |

**Total estimated effort: 3-4 hours**

Task 3 is the bulk of the work — generating ~1000 lines of HTML with inline CSS, JS, SVG, and dagre. Tasks 1, 2, 4 are straightforward bash/Python.
