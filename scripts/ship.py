#!/usr/bin/env python3
"""ship.py — End-to-end autonomous build orchestrator.

This is the CONDUCTOR that chains every other piece of the harness into a
single pipeline. Given a PRD (or natural-language goal), it walks the full
PRD-to-shipped-code workflow without human intervention:

  intake → spec_qa → planning → seeding → building → validating
         → fixing → (rescuing) → post_review → committing → done

The state machine is persisted to .harness/ship_state.json after every
transition, so a build can survive context compaction or a process
restart — the orchestrator picks up exactly where it left off.

ship.py itself is deterministic. It does NOT call the LLM. Instead it
tells the *caller* (the LLM running /ship.md, or a CI script) what
action to take next based on current state. This keeps the heavy
intelligence work outside the script and makes the orchestrator
inspectable and replayable.

Usage:
  python scripts/ship.py start --prd docs/product-specs/foo.md
  python scripts/ship.py start --prompt "Add OAuth login"
  python scripts/ship.py status                 # Show current state + next action
  python scripts/ship.py advance <state>        # Transition to next state
  python scripts/ship.py mark-feature F001 pass # Record feature outcome
  python scripts/ship.py abort                  # Cancel current build
  python scripts/ship.py next-action            # Tell caller what to do next

State stored in .harness/ship_state.json. Loop guard, spec quality,
feature list, and ratchet baseline are all consulted along the way.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = REPO_ROOT / ".harness" / "ship_state.json"
FEATURE_LIST = REPO_ROOT / ".harness" / "feature_list.json"
SHIP_LOG = REPO_ROOT / ".harness" / "ship_log.md"

# ─── State machine ───────────────────────────────────────────────────

STATES = [
    "init",                 # Nothing in flight
    "intake",               # PRD identified, loading
    "spec_qa",              # Running check_spec_quality
    "needs_spec_fix",       # Spec failed quality gate; awaiting revision
    "planning",             # Generating ExecPlan via planner agent
    "seeding",              # Translating ExecPlan into feature_list entries
    "building",             # Picking next feature, spawning tester→executor
    "validating",           # Running validate.sh
    "fixing",               # build-fixer working on failing gates
    "rescuing",             # Loop detected, researcher+codex digging in
    "post_review",          # post-build-reviewer producing compliance matrix
    "adversarial_review",   # codex-reviewer attempts to find a bug tests miss
    "committing",           # Creating commit + (optional) PR
    "done",                 # All features pass + clean review + committed
    "escalated",            # Autonomous loop gave up; human needed
    "aborted",              # User cancelled
]

# Permitted transitions. We're strict so a misbehaving caller can't put
# the state machine into an impossible position.
TRANSITIONS: dict[str, set[str]] = {
    "init":                {"intake", "aborted"},
    "intake":              {"spec_qa", "aborted"},
    "spec_qa":             {"planning", "needs_spec_fix", "aborted"},
    "needs_spec_fix":      {"spec_qa", "aborted"},
    "planning":            {"seeding", "aborted"},
    "seeding":             {"building", "aborted"},
    "building":            {"validating", "post_review", "aborted"},
    "validating":          {"building", "fixing", "post_review", "aborted"},
    "fixing":              {"validating", "rescuing", "escalated", "aborted"},
    "rescuing":            {"validating", "escalated", "aborted"},
    "post_review":         {"adversarial_review", "fixing", "aborted"},
    "adversarial_review":  {"committing", "fixing", "aborted"},
    "committing":          {"done", "aborted"},
    "done":                set(),
    "escalated":           {"intake", "aborted"},
    "aborted":             {"intake"},
}

# Per-state guidance — one paragraph, no jargon. Surfaced by `ship.py
# next-action` so the LLM running /ship.md knows exactly what to do.
NEXT_ACTION: dict[str, str] = {
    "init": (
        "No build in progress. Start one with `ship.py start --prd <path>` or "
        "`ship.py start --prompt '<goal>'`."
    ),
    "intake": (
        "PRD identified. Verify it exists, then advance to `spec_qa`."
    ),
    "spec_qa": (
        "Run `python scripts/check_spec_quality.py <spec_path>`. "
        "If exit 0, advance to `planning`. If exit 1, advance to `needs_spec_fix` "
        "with the report text in state.notes."
    ),
    "needs_spec_fix": (
        "Spec failed quality checks. Either revise the spec to address the "
        "blockers reported in state.notes, then advance to `spec_qa`; "
        "or `abort` and ask the user for input."
    ),
    "planning": (
        "Spawn the planner agent (agents/planner.md). Pass the spec text and "
        "the harness conventions from AGENTS.md. The planner writes "
        "docs/exec-plans/active/<slug>.md. Once that file exists, advance to "
        "`seeding`."
    ),
    "seeding": (
        "Read the generated ExecPlan, extract each milestone's Demo statement "
        "into a feature entry, and write to .harness/feature_list.json with "
        "passes:false. Advance to `building`."
    ),
    "building": (
        "Pick the next feature where passes:false. Spawn the tester agent "
        "(agents/tester.md) to write failing tests, then the executor agent "
        "(agents/executor.md) to implement. After implementation, advance to "
        "`validating`. If no unfinished features remain, advance to `post_review`."
    ),
    "validating": (
        "Run `bash scripts/validate.sh`. If FAIL==0, mark the current feature "
        "passing (`ship.py mark-feature <id> pass`) and advance to `building`. "
        "If FAIL>0, advance to `fixing`."
    ),
    "fixing": (
        "Spawn build-fixer (agents/build-fixer.md) with the failing gate output. "
        "After at most 2 fix attempts, advance to `validating`. Before doing "
        "more fix attempts, run `python scripts/loop_guard.py check` — if it "
        "exits 2, advance to `rescuing` instead."
    ),
    "rescuing": (
        "Loop detected. Run `python scripts/loop_guard.py rescue-request` to "
        "write .harness/rescue_request.md. Spawn TWO agents in parallel: "
        "(1) `researcher` (agents/researcher.md) for web-sourced diagnosis, "
        "(2) `codex-reviewer` (agents/codex-reviewer.md) for an independent "
        "second-opinion via the codex plugin. Compare both analyses, prefer "
        "the higher-confidence one (or merge if they agree). Apply the targeted "
        "fix. Advance to `validating`. If the same fingerprint repeats after "
        "one full rescue cycle, advance to `escalated`."
    ),
    "post_review": (
        "Spawn the post-build-reviewer (agents/post-build-reviewer.md). "
        "Run `python scripts/check_spec_compliance.py`. If both report clean, "
        "advance to `adversarial_review`. If issues found, advance to `fixing`."
    ),
    "adversarial_review": (
        "Spawn the codex-reviewer agent (agents/codex-reviewer.md). It invokes "
        "the codex plugin to do an independent adversarial pass on the diff: "
        "try to find a defect the tests would miss. If codex returns "
        "`NO DEFECT FOUND`, advance to `committing`. If codex returns "
        "`DEFECT: ... SEVERITY: blocker`, advance to `fixing` with codex's "
        "report attached as context. SEVERITY: warning defects are recorded "
        "but do not block — advance to `committing` and note the warning."
    ),
    "committing": (
        "Create a single commit with all changes and the evidence summary. "
        "Format: `feat(<area>): <one-liner>` with body including verified "
        "feature IDs and a 'Generated by ship.py' footer. After commit, "
        "advance to `done`."
    ),
    "done": (
        "Build complete. All features verified, gates green, committed. "
        "Run `ship.py start` to begin a new build."
    ),
    "escalated": (
        "Autonomous loop gave up after rescue. A human is needed to break the "
        "deadlock. See .harness/rescue_request.md for diagnostic context. "
        "Once unblocked, advance back to `intake` to restart."
    ),
    "aborted": (
        "Build cancelled. `ship.py start` begins a new one."
    ),
}


@dataclass
class FeatureProgress:
    id: str
    description: str
    attempts: int = 0
    last_outcome: str | None = None  # "pass" | "fail" | None
    fix_attempts: int = 0
    rescues: int = 0


@dataclass
class ShipState:
    version: int = 2
    status: str = "init"
    started_at: str | None = None
    last_updated: str | None = None
    spec_path: str | None = None
    prompt: str | None = None
    plan_path: str | None = None
    current_feature_id: str | None = None
    features: dict[str, FeatureProgress] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    rescue_count: int = 0
    fix_count: int = 0


# ─── State I/O ───────────────────────────────────────────────────────


def load_state() -> ShipState:
    if not STATE_FILE.exists():
        return ShipState()
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ShipState()
    feats = {fid: FeatureProgress(**v) for fid, v in raw.get("features", {}).items()}
    raw["features"] = feats
    return ShipState(**raw)


def save_state(state: ShipState) -> None:
    state.last_updated = datetime.now(timezone.utc).isoformat()
    data = asdict(state)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(STATE_FILE)


def append_log(state: ShipState, message: str) -> None:
    line = f"[{datetime.now(timezone.utc).isoformat()}] [{state.status}] {message}"
    state.history.append({"at": state.last_updated, "status": state.status, "msg": message})
    SHIP_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SHIP_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


# ─── Helpers used by individual commands ─────────────────────────────


def _load_features() -> list[dict]:
    if not FEATURE_LIST.exists():
        return []
    try:
        return json.loads(FEATURE_LIST.read_text(encoding="utf-8")).get("features", [])
    except (json.JSONDecodeError, OSError):
        return []


def _next_unfinished_feature() -> dict | None:
    for f in _load_features():
        if not f.get("passes"):
            return f
    return None


def _transition(state: ShipState, target: str, note: str | None = None) -> bool:
    if target not in TRANSITIONS.get(state.status, set()):
        print(
            f"Invalid transition: {state.status} → {target}. "
            f"Allowed from '{state.status}': {sorted(TRANSITIONS.get(state.status, set()))}",
            file=sys.stderr,
        )
        return False
    prev = state.status
    state.status = target
    append_log(state, f"{prev} → {target}" + (f" — {note}" if note else ""))
    save_state(state)
    return True


# ─── Commands ────────────────────────────────────────────────────────


def cmd_start(args: argparse.Namespace) -> int:
    state = load_state()
    if state.status not in ("init", "done", "aborted"):
        print(
            f"Cannot start a new build while status is '{state.status}'. "
            f"Run `ship.py abort` first if you want to discard the in-flight build.",
            file=sys.stderr,
        )
        return 1

    state = ShipState()  # fresh slate
    state.started_at = datetime.now(timezone.utc).isoformat()

    if args.prd:
        prd_path = Path(args.prd)
        if not prd_path.is_absolute():
            prd_path = REPO_ROOT / prd_path
        if not prd_path.exists():
            print(f"PRD file not found: {prd_path}", file=sys.stderr)
            return 1
        state.spec_path = str(prd_path.relative_to(REPO_ROOT))
    elif args.prompt:
        state.prompt = args.prompt
    else:
        print("Pass --prd <path> or --prompt '<goal>' to start a build.", file=sys.stderr)
        return 1

    _transition(state, "intake", note=f"spec={state.spec_path or state.prompt!r}")
    print(f"Build started. Status: {state.status}")
    print(NEXT_ACTION[state.status])
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    state = load_state()
    if args.json:
        print(json.dumps(asdict(state), indent=2, default=str))
        return 0
    print(f"Ship Status: {state.status}")
    if state.spec_path:
        print(f"  Spec:           {state.spec_path}")
    if state.prompt:
        print(f"  Prompt:         {state.prompt[:80]}")
    if state.plan_path:
        print(f"  Plan:           {state.plan_path}")
    if state.current_feature_id:
        print(f"  Current feature:{state.current_feature_id}")
    if state.features:
        passing = sum(1 for f in state.features.values() if f.last_outcome == "pass")
        print(f"  Feature progress:{passing}/{len(state.features)}")
    print(f"  Fix attempts:   {state.fix_count}")
    print(f"  Rescues:        {state.rescue_count}")
    if state.notes:
        print("  Notes:")
        for n in state.notes[-3:]:
            print(f"    - {n}")
    print()
    print(f"Next action:")
    print(f"  {NEXT_ACTION[state.status]}")
    return 0


def cmd_advance(args: argparse.Namespace) -> int:
    state = load_state()
    if not _transition(state, args.target, note=args.note):
        return 1
    print(f"Advanced to '{state.status}'.")
    print(NEXT_ACTION[state.status])
    return 0


def cmd_mark_feature(args: argparse.Namespace) -> int:
    state = load_state()
    fid = args.feature_id
    outcome = args.outcome.lower()
    if outcome not in {"pass", "fail"}:
        print("Outcome must be 'pass' or 'fail'.", file=sys.stderr)
        return 1
    if fid not in state.features:
        feats = _load_features()
        desc = next((f.get("description", "") for f in feats if f.get("id") == fid), "")
        state.features[fid] = FeatureProgress(id=fid, description=desc)
    fp = state.features[fid]
    fp.attempts += 1
    fp.last_outcome = outcome
    state.current_feature_id = fid if outcome == "fail" else None
    save_state(state)
    print(f"Feature {fid} → {outcome} (attempt {fp.attempts})")
    return 0


def cmd_record_fix_attempt(args: argparse.Namespace) -> int:
    state = load_state()
    state.fix_count += 1
    if state.current_feature_id and state.current_feature_id in state.features:
        state.features[state.current_feature_id].fix_attempts += 1
    save_state(state)
    print(f"Fix attempts now: {state.fix_count}")
    return 0


def cmd_record_rescue(args: argparse.Namespace) -> int:
    state = load_state()
    state.rescue_count += 1
    if state.current_feature_id and state.current_feature_id in state.features:
        state.features[state.current_feature_id].rescues += 1
    save_state(state)
    print(f"Rescue events now: {state.rescue_count}")
    return 0


def cmd_add_note(args: argparse.Namespace) -> int:
    state = load_state()
    state.notes.append(args.text)
    # keep last 10
    state.notes = state.notes[-10:]
    save_state(state)
    return 0


def cmd_abort(args: argparse.Namespace) -> int:
    state = load_state()
    if state.status in ("init", "done", "aborted"):
        print(f"Nothing to abort (status: {state.status}).")
        return 0
    prev = state.status
    state.status = "aborted"
    append_log(state, f"{prev} → aborted")
    save_state(state)
    print(f"Build aborted from '{prev}'.")
    return 0


def cmd_next_action(args: argparse.Namespace) -> int:
    state = load_state()
    if args.json:
        feature = _next_unfinished_feature()
        loop_status = None
        if state.status in ("fixing", "validating"):
            try:
                proc = subprocess.run(
                    [sys.executable, str(REPO_ROOT / "scripts" / "loop_guard.py"), "check", "--json"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if proc.returncode in (0, 2) and proc.stdout.strip():
                    loop_status = json.loads(proc.stdout.strip().splitlines()[-1])
            except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
                pass
        payload = {
            "status": state.status,
            "next_action": NEXT_ACTION[state.status],
            "next_feature": feature,
            "loop_status": loop_status,
            "fix_count": state.fix_count,
            "rescue_count": state.rescue_count,
        }
        print(json.dumps(payload, indent=2))
        return 0
    print(NEXT_ACTION[state.status])
    return 0


def cmd_set_plan(args: argparse.Namespace) -> int:
    state = load_state()
    p = Path(args.path)
    if not p.is_absolute():
        p = REPO_ROOT / p
    if not p.exists():
        print(f"Plan file not found: {p}", file=sys.stderr)
        return 1
    state.plan_path = str(p.relative_to(REPO_ROOT))
    save_state(state)
    print(f"Plan path recorded: {state.plan_path}")
    return 0


# ─── Parser ──────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="End-to-end ship orchestrator")
    sub = p.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Begin a new autonomous build")
    start.add_argument("--prd", help="Path to product spec / PRD")
    start.add_argument("--prompt", help="Inline goal description")
    start.set_defaults(func=cmd_start)

    status = sub.add_parser("status", help="Show current orchestrator state")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    advance = sub.add_parser("advance", help="Transition to a new state")
    advance.add_argument("target", choices=STATES)
    advance.add_argument("--note", help="Optional transition note")
    advance.set_defaults(func=cmd_advance)

    mark = sub.add_parser("mark-feature", help="Record outcome of the current feature")
    mark.add_argument("feature_id")
    mark.add_argument("outcome", choices=["pass", "fail"])
    mark.set_defaults(func=cmd_mark_feature)

    fix = sub.add_parser("record-fix", help="Increment fix-attempt counter")
    fix.set_defaults(func=cmd_record_fix_attempt)

    rescue = sub.add_parser("record-rescue", help="Increment rescue counter")
    rescue.set_defaults(func=cmd_record_rescue)

    note = sub.add_parser("note", help="Append a free-form note to state")
    note.add_argument("text")
    note.set_defaults(func=cmd_add_note)

    plan = sub.add_parser("set-plan", help="Record the generated ExecPlan path")
    plan.add_argument("path")
    plan.set_defaults(func=cmd_set_plan)

    abort = sub.add_parser("abort", help="Cancel the in-flight build")
    abort.set_defaults(func=cmd_abort)

    nxt = sub.add_parser("next-action", help="Print the LLM-facing next-action prompt")
    nxt.add_argument("--json", action="store_true")
    nxt.set_defaults(func=cmd_next_action)

    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    sys.exit(args.func(args))
