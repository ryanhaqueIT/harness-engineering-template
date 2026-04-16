#!/usr/bin/env bash
# dashboard_hooks.sh — Emit gate status to .harness/dashboard_state.json
# Sourced by validate.sh. If this file doesn't exist, validate.sh works unchanged.
# Zero external dependencies — uses only python3 stdlib.

DASHBOARD_STATE_FILE="${REPO_ROOT:-.}/.harness/dashboard_state.json"
DASHBOARD_HISTORY_FILE="${REPO_ROOT:-.}/.harness/history/runs.json"
_DASHBOARD_RUN_START=""

# Skip all gates in a section at once (when the section is entirely absent)
emit_section_skip() {
    local reason="$1"
    shift
    # Remaining args are gate_id:name:layer triples
    for entry in "$@"; do
        local gate_id="${entry%%:*}"
        local rest="${entry#*:}"
        local gate_name="${rest%%:*}"
        local layer="${rest##*:}"
        emit_gate_skip "$gate_id" "$gate_name" "$layer" "$reason"
    done
}

init_dashboard_state() {
    mkdir -p "$(dirname "$DASHBOARD_STATE_FILE")"
    mkdir -p "$(dirname "$DASHBOARD_HISTORY_FILE")"
    _DASHBOARD_RUN_START=$(python3 -c "import time; print(int(time.time()*1000))")

    python3 -c "
import json, datetime, pathlib
state_path = pathlib.Path('${DASHBOARD_STATE_FILE}')
history_path = pathlib.Path('${DASHBOARD_HISTORY_FILE}')
run_id = 1
if history_path.exists():
    try:
        runs = json.loads(history_path.read_text())
        if runs:
            run_id = runs[-1].get('run_id', 0) + 1
    except (json.JSONDecodeError, KeyError):
        run_id = 1
state = {
    'version': 1,
    'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z'),
    'run_id': run_id,
    'status': 'running',
    'duration_ms': 0,
    'gates': {},
    'scorecard': {'grade': '?', 'score': 0, 'total': 31},
    'ratchet': {}
}
state_path.parent.mkdir(parents=True, exist_ok=True)
state_path.write_text(json.dumps(state, indent=2))
"
}

emit_gate_start() {
    local gate_id="$1"
    # Strip leading whitespace and [XX] prefix from gate name
    local gate_name="${2:-$gate_id}"
    gate_name="${gate_name#"${gate_name%%[![:space:]]*}"}"  # ltrim
    gate_name="${gate_name#\[*\] }"  # remove [XX] prefix
    local layer="${3:-0}"

    python3 -c "
import json, datetime, pathlib
p = pathlib.Path('${DASHBOARD_STATE_FILE}')
try:
    state = json.loads(p.read_text())
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
state['timestamp'] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')
p.write_text(json.dumps(state, indent=2))
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
import json, datetime, pathlib
p = pathlib.Path('${DASHBOARD_STATE_FILE}')
try:
    state = json.loads(p.read_text())
except (FileNotFoundError, json.JSONDecodeError):
    state = {'version': 1, 'gates': {}}
g = state.setdefault('gates', {}).setdefault('${gate_id}', {})
g['status'] = '${status}'
g['duration_ms'] = ${duration_ms}
g['findings'] = ${findings}
state['timestamp'] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')
p.write_text(json.dumps(state, indent=2))
"
}

emit_gate_skip() {
    local gate_id="$1"
    local gate_name="${2:-$gate_id}"
    gate_name="${gate_name#"${gate_name%%[![:space:]]*}"}"  # ltrim
    gate_name="${gate_name#\[*\] }"  # remove [XX] prefix
    local layer="${3:-0}"
    local reason="${4:-skipped}"

    python3 -c "
import json, datetime, pathlib
p = pathlib.Path('${DASHBOARD_STATE_FILE}')
try:
    state = json.loads(p.read_text())
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
state['timestamp'] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')
p.write_text(json.dumps(state, indent=2))
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

state_path = pathlib.Path('${DASHBOARD_STATE_FILE}')
history_path = pathlib.Path('${DASHBOARD_HISTORY_FILE}')

# Update state
try:
    state = json.loads(state_path.read_text())
except (FileNotFoundError, json.JSONDecodeError):
    state = {'version': 1, 'gates': {}, 'run_id': 1}

state['status'] = '${final_status}'
state['duration_ms'] = ${duration_ms}
state['timestamp'] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')
state_path.write_text(json.dumps(state, indent=2))

# Append to history
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
