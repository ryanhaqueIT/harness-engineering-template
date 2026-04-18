#!/usr/bin/env python3
"""pipeline-tracker.py — Updates dashboard pipeline stage from PostToolUse events.

Reads JSON on stdin (Claude Code hook format), detects which pipeline stage
is affected by the tool use, and updates .harness/dashboard_state.json.

Pipeline stages:
    spec      — docs/product-specs/*.md written
    plan      — docs/exec-plans/active/*.md written
    features  — .harness/feature_list.json written
    implement — any file in backend/, frontend/, src/, lib/, app/ written
    validate  — validate.sh runs (handled by validate.sh itself)
    ship      — git commit succeeds

Silent by design — never fails, never blocks, never outputs to stdout.
"""
import json
import sys
import pathlib
import datetime
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
STATE_FILE = REPO_ROOT / ".harness" / "dashboard_state.json"


def load_state():
    if not STATE_FILE.exists():
        return None
    try:
        return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def save_state(state):
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except OSError:
        pass


def set_stage(state, stage_id, status, label):
    if "pipeline" not in state:
        state["pipeline"] = {}
    state["pipeline"][stage_id] = {"status": status, "label": label}
    state["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def detect_stage(tool_name, tool_input, tool_response):
    """Return (stage_id, status, label) or None."""
    # Bash commands
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        # Git commit
        if re.search(r"\bgit commit\b", cmd) and tool_response and "error" not in str(tool_response).lower()[:200]:
            return ("ship", "completed", "Committed to git")
        # Validate.sh
        if "validate.sh" in cmd:
            return ("validate", "running", "Running validate.sh")
        return None

    # File writes
    if tool_name in ("Write", "Edit", "NotebookEdit"):
        path = tool_input.get("file_path", "")
        path_lower = path.replace("\\", "/").lower()

        if "/docs/product-specs/" in path_lower and path_lower.endswith(".md"):
            return ("spec", "completed", "Product spec written")
        if "/docs/exec-plans/active/" in path_lower and path_lower.endswith(".md"):
            return ("plan", "completed", "ExecPlan created")
        if path_lower.endswith("/.harness/feature_list.json") or path_lower.endswith("\\.harness\\feature_list.json"):
            return ("features", "completed", "Feature list seeded")
        # Implementation code paths
        for src_dir in ("/backend/", "/frontend/", "/src/", "/lib/", "/app/"):
            if src_dir in path_lower:
                return ("implement", "running", "Implementation in progress")

    return None


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    tool_response = payload.get("tool_response", {}) or {}

    detected = detect_stage(tool_name, tool_input, tool_response)
    if detected is None:
        sys.exit(0)

    stage_id, status, label = detected

    state = load_state()
    if state is None:
        # Initialize minimal state so the dashboard can pick it up even before validate.sh runs
        state = {
            "version": 1,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
            "run_id": 0,
            "status": "idle",
            "duration_ms": 0,
            "gates": {},
            "pipeline": {},
            "scorecard": {"grade": "?", "score": 0, "total": 31},
            "ratchet": {}
        }

    set_stage(state, stage_id, status, label)
    save_state(state)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never block tool use from a tracker failure
        sys.exit(0)
