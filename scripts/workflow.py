#!/usr/bin/env python3
"""workflow.py — Workflow state machine for harness-aware session management.

Tracks what phase of development the session is in (planning, building,
verifying, shipping, researching) so hooks can behave context-appropriately.

The stop hook uses this to decide whether to block or allow exit:
  - researching/planning → allow exit freely
  - building → warn but allow
  - verifying → block if features unverified
  - shipping → block if gates failing

Usage:
  python scripts/workflow.py status          # Show current state
  python scripts/workflow.py set building    # Set state
  python scripts/workflow.py set researching # Mark as research session
  python scripts/workflow.py lock sw-build   # Acquire lock
  python scripts/workflow.py unlock          # Release lock

State stored in .harness/workflow.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_FILE = REPO_ROOT / ".harness" / "workflow.json"

# Valid state transitions
VALID_TRANSITIONS: dict[str, set[str]] = {
    "none": {"planning", "building", "verifying", "researching"},
    "researching": {"none", "planning", "building"},
    "planning": {"none", "building", "researching"},
    "building": {"none", "verifying", "planning", "researching"},
    "verifying": {"none", "building", "shipping", "researching"},
    "shipping": {"none", "building", "researching"},
}

# How the stop hook should behave per state
STOP_BEHAVIOR: dict[str, str] = {
    "none": "allow",
    "researching": "allow",
    "planning": "allow",
    "building": "warn",       # Warn but allow — work in progress
    "verifying": "enforce",   # Block if features unverified
    "shipping": "enforce",    # Block if gates failing
}

STALE_LOCK_MINUTES = 30


def load_workflow() -> dict:
    if WORKFLOW_FILE.exists():
        try:
            return json.loads(WORKFLOW_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "version": 1,
        "status": "none",
        "currentPhase": None,
        "description": None,
        "tasksTotal": 0,
        "tasksCompleted": 0,
        "lastUpdated": None,
        "lock": None,
    }


def save_workflow(data: dict) -> None:
    WORKFLOW_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["lastUpdated"] = datetime.now(timezone.utc).isoformat()
    tmp = WORKFLOW_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(WORKFLOW_FILE)


def cmd_status(args: argparse.Namespace) -> int:
    data = load_workflow()
    status = data.get("status", "none")
    behavior = STOP_BEHAVIOR.get(status, "allow")

    print(f"Workflow State: {status}")
    print(f"Stop Behavior:  {behavior}")
    if data.get("description"):
        print(f"Description:    {data['description']}")
    if data.get("tasksTotal", 0) > 0:
        print(f"Progress:       {data.get('tasksCompleted', 0)}/{data['tasksTotal']}")
    if data.get("lock"):
        lock = data["lock"]
        print(f"Lock:           held by '{lock['skill']}' since {lock['since']}")
    if data.get("lastUpdated"):
        print(f"Last Updated:   {data['lastUpdated']}")
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    data = load_workflow()
    current = data.get("status", "none")
    target = args.state

    if target not in VALID_TRANSITIONS.get(current, set()):
        valid = ", ".join(sorted(VALID_TRANSITIONS.get(current, set())))
        print(f"Invalid transition: {current} -> {target}")
        print(f"Valid transitions from '{current}': {valid}")
        return 1

    data["status"] = target
    if args.description:
        data["description"] = args.description
    save_workflow(data)
    print(f"Workflow: {current} -> {target}")
    print(f"Stop behavior: {STOP_BEHAVIOR.get(target, 'allow')}")
    return 0


def cmd_lock(args: argparse.Namespace) -> int:
    data = load_workflow()

    # Check for existing lock
    if data.get("lock"):
        lock = data["lock"]
        lock_time = datetime.fromisoformat(lock["since"])
        age_min = (datetime.now(timezone.utc) - lock_time).total_seconds() / 60

        if age_min < STALE_LOCK_MINUTES:
            print(f"Lock held by '{lock['skill']}' ({age_min:.0f}m ago). Cannot acquire.")
            return 1
        else:
            print(f"Clearing stale lock from '{lock['skill']}' ({age_min:.0f}m ago)")

    data["lock"] = {
        "skill": args.skill,
        "since": datetime.now(timezone.utc).isoformat(),
    }
    save_workflow(data)
    print(f"Lock acquired by '{args.skill}'")
    return 0


def cmd_unlock(args: argparse.Namespace) -> int:
    data = load_workflow()
    if data.get("lock"):
        skill = data["lock"]["skill"]
        data["lock"] = None
        save_workflow(data)
        print(f"Lock released (was held by '{skill}')")
    else:
        print("No lock held")
    return 0


def cmd_get_stop_behavior(args: argparse.Namespace) -> int:
    """Used by the stop hook to determine behavior."""
    data = load_workflow()
    status = data.get("status", "none")
    behavior = STOP_BEHAVIOR.get(status, "allow")
    print(behavior)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Workflow state machine")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="Show current workflow state")
    status.set_defaults(func=cmd_status)

    set_cmd = sub.add_parser("set", help="Set workflow state")
    set_cmd.add_argument("state", choices=["none", "researching", "planning", "building", "verifying", "shipping"])
    set_cmd.add_argument("--description", help="Optional description of current work")
    set_cmd.set_defaults(func=cmd_set)

    lock = sub.add_parser("lock", help="Acquire workflow lock")
    lock.add_argument("skill", help="Name of the skill acquiring the lock")
    lock.set_defaults(func=cmd_lock)

    unlock = sub.add_parser("unlock", help="Release workflow lock")
    unlock.set_defaults(func=cmd_unlock)

    stop = sub.add_parser("stop-behavior", help="Get stop hook behavior for current state")
    stop.set_defaults(func=cmd_get_stop_behavior)

    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))
