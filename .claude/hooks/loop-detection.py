#!/usr/bin/env python3
"""PostToolUse hook: detect and break repetitive tool call loops.

Algorithm (adapted from DeerFlow's LoopDetectionMiddleware):
1. Hash each tool call: MD5(tool_name + sorted(args))
2. Track hashes in a sliding window (last 20 calls)
3. Warn at 3 identical calls — suggest different approach
4. Hard-stop at 5 identical calls — block and force re-evaluation

State persisted in .harness/loop_state.json between invocations.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

# ═══════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════

WARN_THRESHOLD = 3      # Warn after this many identical calls
HARD_LIMIT = 5          # Block after this many identical calls
WINDOW_SIZE = 20        # Sliding window of recent calls to track

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_FILE = REPO_ROOT / ".harness" / "loop_state.json"


def compute_hash(tool_name: str, tool_input: dict) -> str:
    """Order-independent hash of a tool call."""
    normalized = json.dumps(
        {"name": tool_name, "args": tool_input},
        sort_keys=True,
        default=str,
    )
    return hashlib.md5(normalized.encode()).hexdigest()[:12]


def load_state() -> dict:
    """Load loop detection state from disk."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"history": [], "warned": []}


def save_state(state: dict) -> None:
    """Persist loop detection state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)  # Atomic rename


def main() -> int:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return 0

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # Skip loop detection for read-only tools — they don't cause loops
    readonly_tools = {"Read", "Glob", "Grep", "WebSearch", "WebFetch"}
    if tool_name in readonly_tools:
        return 0

    call_hash = compute_hash(tool_name, tool_input)
    state = load_state()
    history = state.get("history", [])
    warned = state.get("warned", [])

    # Append to sliding window
    history.append(call_hash)
    if len(history) > WINDOW_SIZE:
        history = history[-WINDOW_SIZE:]

    # Count identical calls in window
    count = history.count(call_hash)

    if count >= HARD_LIMIT:
        # Hard stop — block and force re-evaluation
        print(
            json.dumps({
                "decision": "block",
                "reason": (
                    f"LOOP HARD-STOP: You have run the exact same {tool_name} command "
                    f"{count} times in the last {WINDOW_SIZE} calls. This is an infinite loop. "
                    f"You MUST try a completely different approach:\n"
                    f"  1. Re-read the error message carefully\n"
                    f"  2. Search the codebase for similar patterns that work\n"
                    f"  3. Try a different fix strategy\n"
                    f"  4. If stuck, explain the problem and ask for help\n"
                    f"DO NOT run this same command again."
                ),
            })
        )
        # Save state before exiting
        state["history"] = history
        save_state(state)
        return 0

    if count >= WARN_THRESHOLD and call_hash not in warned:
        # Warn once per unique loop
        warned.append(call_hash)
        print(
            f"⚠ LOOP DETECTED: You've run this exact {tool_name} call {count} times. "
            f"Try a DIFFERENT approach — read the error more carefully, "
            f"check a different file, or rethink your fix strategy. "
            f"({HARD_LIMIT - count} more identical calls will be blocked.)",
            file=sys.stderr,
        )

    # Persist state
    state["history"] = history
    state["warned"] = warned
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
