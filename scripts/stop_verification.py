#!/usr/bin/env python3
"""Stop hook: blocks agent from stopping until features are verified.

Fires every time the agent finishes a response. If features exist but
aren't all verified, the agent is forced to continue working.

Based on: ClaudeFast Stop Hook pattern + BSWEN "Demo Statements" research.
"""

import json
import sys
from pathlib import Path


def main() -> int:
    input_data = json.load(sys.stdin)

    # CRITICAL: prevent infinite loops.
    # When stop_hook_active is True, the agent is already in a forced-continuation
    # state from a previous block. Let it stop to break the cycle.
    if input_data.get("stop_hook_active", False):
        sys.exit(0)

    # Find repo root
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    feature_file = repo_root / ".harness" / "feature_list.json"

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

        print(json.dumps({
            "decision": "block",
            "reason": (
                f"STOP BLOCKED: {passing}/{total} features verified. "
                f"Failing: {names}{extra}. "
                f"You must: (1) start the app with boot_worktree.sh, "
                f"(2) run each feature's verification steps, "
                f"(3) flip passes:true ONLY after real verification. "
                f"Do NOT claim completion without evidence."
            )
        }))

    sys.exit(0)


if __name__ == "__main__":
    main()
