#!/usr/bin/env python3
"""agent-tracker.py — Updates dashboard agent status from Task tool invocations.

Runs on:
    PreToolUse  (matcher: Task)  — marks an agent as "active"
    SubagentStop                 — marks the active agent as "idle"

Maps subagent names/types to the 8 harness agents:
    planner, tester, executor, build-fixer, reviewer,
    entropy-cleaner, bootstrapper, post-build-reviewer

Reads JSON on stdin. Silent — never fails, never blocks.
"""
import json
import sys
import pathlib
import datetime

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
STATE_FILE = REPO_ROOT / ".harness" / "dashboard_state.json"

HARNESS_AGENTS = {
    "planner", "tester", "executor", "build-fixer", "reviewer",
    "entropy-cleaner", "bootstrapper", "post-build-reviewer",
}

# Map common subagent names/descriptions to harness agent roles
AGENT_KEYWORDS = {
    "planner": ["plan", "planner", "writing-plans"],
    "tester": ["test", "tester", "tdd"],
    "executor": ["execut", "implement", "build"],
    "build-fixer": ["fix", "build-fixer", "debug"],
    "reviewer": ["review", "reviewer", "code-review"],
    "entropy-cleaner": ["entropy", "cleanup", "refactor"],
    "bootstrapper": ["bootstrap", "setup", "init"],
    "post-build-reviewer": ["post-build", "compliance", "verification"],
}


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


def ensure_agents_section(state):
    if "agents" not in state or not isinstance(state["agents"], dict):
        state["agents"] = {"active": None, "task": "", "agents": {}}
    if "agents" not in state["agents"]:
        state["agents"]["agents"] = {}
    for a in HARNESS_AGENTS:
        if a not in state["agents"]["agents"]:
            state["agents"]["agents"][a] = {"status": "idle"}


def map_to_harness_agent(subagent_type, description):
    """Find which harness agent this subagent belongs to."""
    if not subagent_type and not description:
        return None
    candidates = f"{subagent_type or ''} {description or ''}".lower()
    for agent_id, keywords in AGENT_KEYWORDS.items():
        for kw in keywords:
            if kw in candidates:
                return agent_id
    return None


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def mark_active(agent_id, task):
    state = load_state() or _new_state()
    ensure_agents_section(state)
    state["agents"]["active"] = agent_id
    state["agents"]["task"] = task[:120] if task else ""
    state["agents"]["agents"][agent_id] = {
        "status": "active",
        "task": task[:120] if task else "",
        "last_active": now_iso(),
    }
    state["timestamp"] = now_iso()
    save_state(state)


def mark_all_idle():
    state = load_state()
    if state is None:
        return
    ensure_agents_section(state)
    active = state["agents"].get("active")
    if active and active in state["agents"]["agents"]:
        state["agents"]["agents"][active] = {
            "status": "idle",
            "last_active": now_iso(),
        }
    state["agents"]["active"] = None
    state["agents"]["task"] = ""
    state["timestamp"] = now_iso()
    save_state(state)


def _new_state():
    return {
        "version": 1,
        "timestamp": now_iso(),
        "run_id": 0,
        "status": "idle",
        "duration_ms": 0,
        "gates": {},
        "pipeline": {},
        "agents": {"active": None, "task": "", "agents": {}},
        "scorecard": {"grade": "?", "score": 0, "total": 31},
        "ratchet": {},
    }


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    hook_event = payload.get("hook_event_name", "")
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    # SubagentStop — clear active agent
    if hook_event == "SubagentStop":
        mark_all_idle()
        sys.exit(0)

    # PreToolUse on Task — mark subagent as active
    if tool_name == "Task":
        subagent_type = tool_input.get("subagent_type", "")
        description = tool_input.get("description", "")
        prompt = tool_input.get("prompt", "")
        harness_agent = map_to_harness_agent(subagent_type, description) or "executor"
        task = description or prompt[:100]
        mark_active(harness_agent, task)

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
