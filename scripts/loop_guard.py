#!/usr/bin/env python3
"""loop_guard.py — Detect when the validate→fix loop is stuck.

The autonomous build loop runs validate.sh after every implementation change.
When a gate fails, build-fixer applies a fix and re-validates. Normally this
converges in a few iterations.

But agents can get stuck: same gate failing with the same error N times in a
row, each "fix" identical to the last. Without intervention, this burns
budget and never converges. This module is the watchdog.

It reads run history from .harness/history/runs.json (already written by
validate.sh via dashboard_hooks.sh) and the richer per-gate detail from
.harness/dashboard_state.json. For each failing run it produces a
*fingerprint*. If the last N runs share a fingerprint, it raises a rescue
signal — at which point the orchestrator (ship.py) spawns a researcher
agent or escalates to a human.

This is the DeerFlow "loop detection" capability adapted to our harness.

Usage:
  python scripts/loop_guard.py check                  # Inspect recent runs
  python scripts/loop_guard.py check --window 3       # Custom window
  python scripts/loop_guard.py rescue-request         # Write rescue prompt
  python scripts/loop_guard.py status --json          # Machine-readable

Exit codes:
  0 = no loop detected (or insufficient history)
  2 = loop detected — orchestrator should branch to rescue
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_FILE = REPO_ROOT / ".harness" / "history" / "runs.json"
DASHBOARD_STATE = REPO_ROOT / ".harness" / "dashboard_state.json"
LOOP_STATE = REPO_ROOT / ".harness" / "loop_guard_state.json"
RESCUE_REQUEST = REPO_ROOT / ".harness" / "rescue_request.md"

DEFAULT_WINDOW = 3


# ─── Data model ──────────────────────────────────────────────────────


@dataclass
class FailingGate:
    """One failing gate within a single validate.sh run."""

    gate_id: str
    name: str
    layer: int
    details: list[str]


@dataclass
class RunSummary:
    """One validate.sh run, post-filtered to its failures."""

    run_id: int
    timestamp: str
    failing_gates: list[FailingGate]
    fingerprint: str

    @property
    def is_failure(self) -> bool:
        return bool(self.failing_gates)


# ─── Fingerprint: the heart of loop detection ────────────────────────
#
# A fingerprint is a deterministic string derived from a failing run.
# Two runs with the same fingerprint are considered "the same failure"
# for the purposes of loop detection. The choice of algorithm has
# direct tradeoffs:
#
#   STRICT  → match the entire error verbatim → fewer false positives
#             (missed loops) but more false negatives (treats real
#             progress as a stuck loop because a line number changed)
#   LOOSE   → match only on which gates failed → catches loops earlier
#             but flags as stuck when the agent is actually iterating
#             through different errors in the same gate
#   NORMALIZED → strip volatile content (line numbers, hashes, paths,
#                timestamps) before hashing → best of both, but
#                normalization rules need tuning
#
# This is a design decision worth thinking through carefully.


def _normalize_error_text(text: str) -> str:
    """Reduce a raw error string to its semantic shape.

    Strips: ANSI escapes, ISO timestamps, hex addresses, line numbers,
    tempfile suffixes. Lowercases. Collapses whitespace.
    """
    # Strip ANSI
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    # ISO timestamps
    text = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?", "<ts>", text)
    # File:line refs (keep file, drop line)
    text = re.sub(r"(\.[a-z]+):\d+(?::\d+)?", r"\1:<line>", text)
    # Hex addresses
    text = re.sub(r"0x[0-9a-fA-F]+", "<addr>", text)
    # Tempfile suffixes like tmp1234abcd
    text = re.sub(r"tmp[a-zA-Z0-9]{4,}", "<tmp>", text)
    # Long numeric IDs
    text = re.sub(r"\b\d{6,}\b", "<num>", text)
    return " ".join(text.lower().split())


def fingerprint_failure(failing_gates: list[FailingGate]) -> str:
    """Produce a deterministic fingerprint for a set of failing gates.

    Two runs producing the SAME fingerprint will be considered "the same
    failure" by the loop detector. Two runs producing different fingerprints
    will be considered "different failures" (and therefore real progress).

    Input shape: a list of FailingGate, each with .gate_id, .name, .layer,
    and .details (a list of raw error strings from dashboard_state.json).

    Trade-off you are choosing:
      • Too strict → loops go undetected, agent spins forever
      • Too loose → real progress flagged as a loop, rescue triggers early

    Return: a short, stable string. Examples we could imagine:
      "B5+B7|missing-import:requests"
      "X6=2|live-feature:F002:assert-status-201"
      "B8|orphan:backend/services/foo.py"
    """
    if not failing_gates:
        return "no-fail"

    by_layer = sorted(failing_gates, key=lambda g: (g.layer, g.gate_id))

    tokens: list[str] = []
    for gate in by_layer:
        sig = _signature_for_gate(gate)
        tokens.append(f"{gate.gate_id}={sig}" if sig else gate.gate_id)

    fp = "|".join(tokens)
    return fp[:120]


_SYMBOL_PATTERNS = [
    re.compile(r"no module named ['\"]?([\w.]+)['\"]?", re.IGNORECASE),
    re.compile(r"name ['\"]?([\w.]+)['\"]? is not defined", re.IGNORECASE),
    re.compile(r"cannot import name ['\"]?([\w.]+)['\"]?", re.IGNORECASE),
    re.compile(r"unresolved reference ['\"]?([\w.]+)['\"]?", re.IGNORECASE),
    re.compile(r"\b(ORPHAN|UNUSED|CYCLE|UNWIRED|SECRET FOUND|BROKEN)\b"),
    re.compile(r"assertionerror[: ]+(.{1,40})", re.IGNORECASE),
    re.compile(r"http\s+(\d{3})\s+!=\s+(\d{3})", re.IGNORECASE),
    re.compile(r"response\.([\w.]+)\s+=\s+\S+\s+!=", re.IGNORECASE),
    re.compile(r"\bfeature\s+([F]\d{3,4})\b", re.IGNORECASE),
]


def _signature_for_gate(gate: FailingGate) -> str:
    """Extract a short, stable token from a gate's error details.

    Prefers a structured symbol (missing module name, error code, feature
    ID) when the patterns match. Otherwise falls back to the normalized
    first non-empty error line, truncated.
    """
    text = " ".join(d for d in gate.details if d).strip()
    if not text:
        return ""
    for rx in _SYMBOL_PATTERNS:
        m = rx.search(text)
        if m:
            return ":".join(g for g in m.groups() if g)[:40]
    norm = _normalize_error_text(text)
    return norm[:40]


# ─── State I/O ───────────────────────────────────────────────────────


def load_runs() -> list[dict]:
    if not RUNS_FILE.exists():
        return []
    try:
        return json.loads(RUNS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def load_dashboard_state() -> dict:
    if not DASHBOARD_STATE.exists():
        return {}
    try:
        return json.loads(DASHBOARD_STATE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_loop_state() -> dict:
    if LOOP_STATE.exists():
        try:
            return json.loads(LOOP_STATE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"version": 1, "fingerprints": [], "rescues_triggered": 0}


def save_loop_state(state: dict) -> None:
    state["lastUpdated"] = datetime.now(timezone.utc).isoformat()
    LOOP_STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOOP_STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(LOOP_STATE)


# ─── Building RunSummary objects ─────────────────────────────────────


def extract_failing_gates_from_dashboard() -> list[FailingGate]:
    """Pull rich gate details (including error text) from dashboard_state.json.

    The dashboard_state.json file is rewritten by validate.sh on every run,
    so it represents the MOST RECENT run only. For historical context we
    rely on runs.json (which has gate verdicts but not error details).
    """
    state = load_dashboard_state()
    gates = state.get("gates", {})
    failing: list[FailingGate] = []
    for gate_id, info in gates.items():
        if info.get("status") != "failed":
            continue
        failing.append(
            FailingGate(
                gate_id=gate_id,
                name=info.get("name", ""),
                layer=info.get("layer", 0),
                details=list(info.get("details", []) or []),
            )
        )
    return failing


def build_recent_run_summaries(window: int) -> list[RunSummary]:
    """Build a summary of the last `window` runs, fingerprinting each.

    For the most recent run we have rich error detail (dashboard_state.json).
    For older runs we only know which gates failed (runs.json), so the
    fingerprint of those is necessarily looser.
    """
    runs = load_runs()
    if not runs:
        return []

    recent = runs[-window:]
    dashboard_failing = extract_failing_gates_from_dashboard()
    dashboard_run_id = load_dashboard_state().get("run_id")

    summaries: list[RunSummary] = []
    for entry in recent:
        run_id = entry.get("run_id", -1)
        ts = entry.get("timestamp", "")
        gates = entry.get("gates", {})
        # Build FailingGate stubs from runs.json (no error detail available)
        failing: list[FailingGate] = [
            FailingGate(gate_id=gid, name="", layer=0, details=[])
            for gid, verdict in gates.items()
            if verdict == "failed"
        ]
        # If this is the run that matches dashboard_state.json, swap in rich data
        if run_id == dashboard_run_id and dashboard_failing:
            failing = dashboard_failing

        try:
            fp = fingerprint_failure(failing)
        except NotImplementedError:
            # If the human hasn't implemented yet, fall back to the
            # simplest fingerprint (just gate IDs) so the rest of the
            # module can still be tested in isolation.
            fp = "|".join(sorted(g.gate_id for g in failing)) or "no-fail"

        summaries.append(
            RunSummary(run_id=run_id, timestamp=ts, failing_gates=failing, fingerprint=fp)
        )
    return summaries


# ─── Loop detection ──────────────────────────────────────────────────


def detect_loop(summaries: list[RunSummary], window: int) -> tuple[bool, str | None]:
    """A loop is detected if the last `window` runs all share a fingerprint
    AND every one of those runs is a failure (not a pass).
    """
    if len(summaries) < window:
        return False, None
    last = summaries[-window:]
    if any(not s.is_failure for s in last):
        return False, None
    fps = {s.fingerprint for s in last}
    if len(fps) == 1:
        return True, next(iter(fps))
    return False, None


# ─── Rescue request ──────────────────────────────────────────────────


def write_rescue_request(summaries: list[RunSummary], fingerprint: str, window: int) -> None:
    """Write a structured rescue-request file for the orchestrator to act on."""
    failing = summaries[-1].failing_gates
    lines = [
        "# Rescue Request — loop guard triggered",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Window: last {window} validate.sh runs",
        f"Shared fingerprint: `{fingerprint}`",
        "",
        "## Why this fired",
        "",
        f"The same failure fingerprint repeated across the last {window} runs.",
        "build-fixer's incremental approach is not converging.",
        "",
        "## Failing gates on most recent run",
        "",
    ]
    if not failing:
        lines.append("_No detailed failure info — older runs only have gate IDs._")
    for g in failing:
        lines.append(f"- **{g.gate_id}** ({g.name}, layer {g.layer})")
        for d in g.details[:5]:
            lines.append(f"  - `{d}`")
    lines.extend(
        [
            "",
            "## Recommended next move",
            "",
            "1. Spawn the `researcher` agent with the failing gate output above.",
            "2. The researcher should web-search the exact error, link sources,",
            "   and write a 3-bullet root cause analysis.",
            "3. ONLY after the analysis arrives, apply a fix.",
            "4. If a single research+fix cycle still leaves the fingerprint",
            "   unchanged, escalate to a human via stop hook.",
            "",
        ]
    )
    RESCUE_REQUEST.parent.mkdir(parents=True, exist_ok=True)
    RESCUE_REQUEST.write_text("\n".join(lines), encoding="utf-8")


# ─── CLI ─────────────────────────────────────────────────────────────


def cmd_check(args: argparse.Namespace) -> int:
    summaries = build_recent_run_summaries(args.window)
    if not summaries:
        if args.json:
            print(json.dumps({"loop": False, "reason": "no-runs"}))
        else:
            print("No validate.sh runs recorded yet.")
        return 0

    looped, fp = detect_loop(summaries, args.window)
    state = load_loop_state()
    state["fingerprints"] = [s.fingerprint for s in summaries]
    state["last_check"] = datetime.now(timezone.utc).isoformat()
    state["loop_detected"] = looped
    save_loop_state(state)

    if args.json:
        print(
            json.dumps(
                {
                    "loop": looped,
                    "fingerprint": fp,
                    "window": args.window,
                    "fingerprints": [s.fingerprint for s in summaries],
                }
            )
        )
        return 2 if looped else 0

    if looped:
        print(f"LOOP DETECTED — last {args.window} runs share fingerprint:")
        print(f"  {fp}")
        print(f"Run 'python scripts/loop_guard.py rescue-request' to draft a rescue prompt.")
        return 2

    print(f"No loop in last {len(summaries)} run(s). Recent fingerprints:")
    for s in summaries:
        print(f"  run {s.run_id}: {s.fingerprint}")
    return 0


def cmd_rescue_request(args: argparse.Namespace) -> int:
    summaries = build_recent_run_summaries(args.window)
    looped, fp = detect_loop(summaries, args.window)
    if not looped:
        print("No loop detected — rescue not needed.")
        return 0
    write_rescue_request(summaries, fp or "<none>", args.window)
    state = load_loop_state()
    state["rescues_triggered"] = state.get("rescues_triggered", 0) + 1
    state["last_rescue"] = datetime.now(timezone.utc).isoformat()
    save_loop_state(state)
    print(f"Rescue request written to {RESCUE_REQUEST.relative_to(REPO_ROOT)}")
    return 2


def cmd_status(args: argparse.Namespace) -> int:
    state = load_loop_state()
    if args.json:
        print(json.dumps(state, indent=2))
        return 0
    print("Loop Guard Status")
    print("=" * 40)
    for k, v in state.items():
        print(f"  {k}: {v}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Validate.sh loop guard")
    sub = p.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="Inspect recent runs for a loop")
    check.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    check.add_argument("--json", action="store_true")
    check.set_defaults(func=cmd_check)

    rescue = sub.add_parser("rescue-request", help="Write rescue request if looping")
    rescue.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    rescue.set_defaults(func=cmd_rescue_request)

    status = sub.add_parser("status", help="Show loop guard state")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    return p


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))
