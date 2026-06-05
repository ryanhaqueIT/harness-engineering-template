#!/usr/bin/env python3
"""Stop hook: workflow-aware, re-derivation Stop gate.

This gate does NOT trust the agent's `passes:true` flag. For every feature
claiming to pass, it RE-DERIVES truth by re-running the feature's declared
verification command and checking the result itself.

Contract for a "truly verified" feature:
  - feature["passes"] is true, AND
  - feature["verify"] is an object {"cmd": str, "expect": str}, AND
  - running cmd (cwd=repo root, ~120s timeout) exits 0, AND
  - the "expect" substring appears in the combined stdout+stderr.

A feature with passes:true but NO verify block, or whose re-run disagrees,
is an UNVERIFIED CLAIM → the stop is blocked.

Behavior depends on workflow state (.harness/workflow.json):
  - researching/planning/none-with-no-features → allow exit freely
  - building → warn but allow (work in progress)
  - verifying/shipping/none → enforce (block on any unverified claim)

Preserves the stop_hook_active loop-guard and the
{"decision":"block","reason":...} stdout contract.

Based on: ClaudeFast Stop Hook pattern + BSWEN "Demo Statements" research.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

VERIFY_TIMEOUT_SECONDS = 120


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


def _run_verify_cmd(cmd: str, cwd: Path | None = None) -> tuple[int, str]:
    """Run a verification command, returning (exit_code, combined_output).

    Isolated so tests can monkeypatch it instead of spawning subprocesses.
    A timeout or spawn failure is treated as a non-zero (failed) result.
    """
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(cwd) if cwd else str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=VERIFY_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return (124, "verification command timed out")
    except OSError as e:
        return (1, f"failed to run verification command: {e}")
    return (proc.returncode, (proc.stdout or "") + (proc.stderr or ""))


def verify_feature(feature: dict) -> bool:
    """Re-derive whether a feature is truly verified.

    Returns True ONLY when the feature claims passes:true, declares a valid
    verify block, and re-running it exits 0 with the expected substring in
    the output. Everything else (no claim, missing evidence, disagreement)
    returns False — an unverified claim.
    """
    if not feature.get("passes"):
        return False

    verify = feature.get("verify")
    if not isinstance(verify, dict):
        return False

    cmd = verify.get("cmd")
    expect = verify.get("expect")
    if not isinstance(cmd, str) or not cmd.strip():
        return False
    if not isinstance(expect, str):
        return False

    exit_code, output = _run_verify_cmd(cmd, cwd=REPO_ROOT)
    return exit_code == 0 and expect in output


@dataclass
class StopDecision:
    """Outcome of evaluating the feature list against the workflow state."""

    allow: bool
    block_payload: dict | None = None
    warning: str | None = None


def evaluate_features(features: list[dict], status: str) -> StopDecision:
    """Pure decision: should the stop be allowed, warned, or blocked?

    Re-derives truth via verify_feature for each feature, then applies the
    workflow-state policy:
      - researching/planning → always allow
      - no features → allow
      - building → warn but allow if any unverified
      - verifying/shipping/none → block if any unverified
    """
    # Research and planning sessions exit freely.
    if status in ("researching", "planning"):
        return StopDecision(allow=True)

    if not features:
        return StopDecision(allow=True)

    verified = [f for f in features if verify_feature(f)]
    unverified = [f for f in features if f not in verified]
    total = len(features)
    n_verified = len(verified)

    if not unverified:
        return StopDecision(allow=True)

    names = ", ".join(f.get("id", "?") for f in unverified[:5])
    extra = f" and {len(unverified) - 5} more" if len(unverified) > 5 else ""

    # Building state: warn but allow (work in progress).
    if status == "building":
        warning = (
            f"WARNING: {n_verified}/{total} features RE-VERIFIED. "
            f"Unverified claims: {names}{extra}. "
            f"You're in 'building' state — exit allowed, but every feature must "
            f"re-derive (verify.cmd exits 0 and verify.expect appears in output) "
            f"before shipping."
        )
        return StopDecision(allow=True, warning=warning)

    # Verifying/shipping/none: enforce.
    payload = {
        "decision": "block",
        "reason": (
            f"STOP BLOCKED: only {n_verified}/{total} features RE-VERIFIED by "
            f"re-running their evidence. Unverified claims (passes:true but the "
            f"re-run disagreed or no verify block): {names}{extra}. "
            f"This gate does NOT trust passes:true. Each feature needs a "
            f'"verify": {{"cmd": ..., "expect": ...}} block whose cmd exits 0 '
            f"and whose expect substring appears in the output. You must: "
            f"(1) start the app with boot_worktree.sh, (2) run each feature's "
            f"verification command, (3) record a real verify block — do NOT "
            f"flip passes:true without reproducible evidence. "
            f"(Set workflow to 'researching' with: python scripts/workflow.py set researching)"
        ),
    }
    return StopDecision(allow=False, block_payload=payload)


def main() -> int:
    input_data = json.load(sys.stdin)

    # CRITICAL: prevent infinite loops.
    if input_data.get("stop_hook_active", False):
        sys.exit(0)

    repo_root = REPO_ROOT
    feature_file = repo_root / ".harness" / "feature_list.json"

    status = get_workflow_status(repo_root)

    # Research and planning sessions exit freely (short-circuit before file read).
    if status in ("researching", "planning"):
        sys.exit(0)

    # No feature list = nothing to verify, allow stop.
    if not feature_file.exists():
        sys.exit(0)

    try:
        data = json.loads(feature_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        sys.exit(0)

    features = data.get("features", [])

    decision = evaluate_features(features, status)

    if decision.warning is not None:
        print(decision.warning, file=sys.stderr)

    if not decision.allow and decision.block_payload is not None:
        print(json.dumps(decision.block_payload))

    sys.exit(0)


if __name__ == "__main__":
    main()
