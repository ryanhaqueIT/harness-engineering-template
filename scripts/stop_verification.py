#!/usr/bin/env python3
"""Stop hook: workflow-aware session exit control.

Behavior depends on workflow state (.harness/workflow.json):
  - researching/planning/none → allow exit freely
  - building → warn but allow (work in progress)
  - verifying → block if features unverified
  - shipping → block if gates failing

Falls back to strict enforcement if no workflow state exists.

Based on: ClaudeFast Stop Hook pattern + BSWEN "Demo Statements" research.
"""

import json
import sys
from pathlib import Path


def get_workflow_status(repo_root: Path) -> str:
    """Read workflow state. Returns 'none' if no state file."""
    workflow_file = repo_root / ".harness" / "workflow.json"
    if not workflow_file.exists():
        return "none"
    try:
        data = json.loads(workflow_file.read_text(encoding="utf-8"))
        return data.get("status", "none")
    except (json.JSONDecodeError, OSError):
        return "none"


def main() -> int:
    input_data = json.load(sys.stdin)

    # CRITICAL: prevent infinite loops.
    if input_data.get("stop_hook_active", False):
        sys.exit(0)

    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    feature_file = repo_root / ".harness" / "feature_list.json"

    # Check workflow state first
    status = get_workflow_status(repo_root)

    # Research and planning sessions exit freely
    if status in ("researching", "planning"):
        sys.exit(0)

    # No feature list = nothing to verify, allow stop
    if not feature_file.exists():
        sys.exit(0)

    try:
        data = json.loads(feature_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        sys.exit(0)

    features = data.get("features", [])
    if not features:
        sys.exit(0)

    passing = sum(1 for f in features if f.get("passes"))
    total = len(features)

    if passing < total:
        failing = [f for f in features if not f.get("passes")]
        names = ", ".join(f.get("id", "?") for f in failing[:5])
        extra = f" and {len(failing) - 5} more" if len(failing) > 5 else ""

        # Building state: warn but allow
        if status == "building":
            print(
                f"WARNING: {passing}/{total} features verified. "
                f"Unverified: {names}{extra}. "
                f"You're in 'building' state — exit allowed, but features need verification before shipping.",
                file=sys.stderr,
            )
            sys.exit(0)

        # Verifying/shipping/none: enforce
        print(json.dumps({
            "decision": "block",
            "reason": (
                f"STOP BLOCKED: {passing}/{total} features verified. "
                f"Failing: {names}{extra}. "
                f"You must: (1) start the app with boot_worktree.sh, "
                f"(2) run each feature's verification steps, "
                f"(3) flip passes:true ONLY after real verification. "
                f"Do NOT claim completion without evidence. "
                f"(Set workflow to 'researching' with: python scripts/workflow.py set researching)"
            )
        }))

    sys.exit(0)


if __name__ == "__main__":
    main()
