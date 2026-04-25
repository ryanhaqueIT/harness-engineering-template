#!/usr/bin/env python3
"""gate_calibration.py — Record and analyze gate calibration data.

After each validation run, records per-gate results (verdict, finding count,
false positives, false negatives). Over time, learns which gates are
over-sensitive and suggests threshold adjustments.

Usage:
  python scripts/gate_calibration.py record --gate B8 --verdict FAIL --findings 11
  python scripts/gate_calibration.py record --gate B8 --verdict FAIL --findings 11 --false-positives 2
  python scripts/gate_calibration.py report
  python scripts/gate_calibration.py suggest

State stored in .harness/gate_calibration.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CALIBRATION_FILE = REPO_ROOT / ".harness" / "gate_calibration.json"


def load_calibration() -> dict:
    if CALIBRATION_FILE.exists():
        try:
            return json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"version": 1, "gates": {}, "runs": []}


def save_calibration(data: dict) -> None:
    CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CALIBRATION_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(CALIBRATION_FILE)


def cmd_record(args: argparse.Namespace) -> int:
    """Record a gate result after a validation run."""
    data = load_calibration()

    gate = args.gate
    if gate not in data["gates"]:
        data["gates"][gate] = {
            "total_runs": 0,
            "pass_count": 0,
            "fail_count": 0,
            "total_findings": 0,
            "total_false_positives": 0,
            "total_false_negatives": 0,
            "history": [],
        }

    g = data["gates"][gate]
    g["total_runs"] += 1
    if args.verdict.upper() == "PASS":
        g["pass_count"] += 1
    else:
        g["fail_count"] += 1
    g["total_findings"] += args.findings
    g["total_false_positives"] += args.false_positives
    g["total_false_negatives"] += args.false_negatives

    # Keep last 20 runs per gate
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "verdict": args.verdict.upper(),
        "findings": args.findings,
        "false_positives": args.false_positives,
        "false_negatives": args.false_negatives,
    }
    g["history"].append(entry)
    if len(g["history"]) > 20:
        g["history"] = g["history"][-20:]

    # Also append to global run log
    data["runs"].append({
        "timestamp": entry["timestamp"],
        "gate": gate,
        **entry,
    })
    if len(data["runs"]) > 100:
        data["runs"] = data["runs"][-100:]

    save_calibration(data)
    print(f"Recorded: {gate} = {args.verdict.upper()} ({args.findings} findings, {args.false_positives} FP, {args.false_negatives} FN)")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Display calibration report for all gates."""
    data = load_calibration()

    if not data["gates"]:
        print("No calibration data yet. Run 'gate_calibration.py record' after validation.")
        return 0

    print("GATE CALIBRATION REPORT")
    print("=" * 80)
    print(f"{'Gate':<8} {'Runs':<6} {'Pass':<6} {'Fail':<6} {'Findings':<10} {'FP':<6} {'FN':<6} {'FP Rate':<8} {'Signal'}")
    print("-" * 80)

    for gate, g in sorted(data["gates"].items()):
        runs = g["total_runs"]
        fp_rate = (g["total_false_positives"] / g["total_findings"] * 100) if g["total_findings"] > 0 else 0
        true_findings = g["total_findings"] - g["total_false_positives"]
        signal = "HIGH" if fp_rate < 20 else "MEDIUM" if fp_rate < 50 else "LOW (needs tuning)"

        print(
            f"{gate:<8} {runs:<6} {g['pass_count']:<6} {g['fail_count']:<6} "
            f"{g['total_findings']:<10} {g['total_false_positives']:<6} "
            f"{g['total_false_negatives']:<6} {fp_rate:>5.1f}%  {signal}"
        )

    print("=" * 80)
    print(f"\nTotal runs recorded: {len(data['runs'])}")
    return 0


def cmd_suggest(args: argparse.Namespace) -> int:
    """Suggest gate adjustments based on calibration data."""
    data = load_calibration()

    if not data["gates"]:
        print("No calibration data yet.")
        return 0

    print("GATE TUNING SUGGESTIONS")
    print("=" * 60)

    suggestions = []
    for gate, g in sorted(data["gates"].items()):
        if g["total_findings"] == 0:
            continue

        fp_rate = g["total_false_positives"] / g["total_findings"] * 100
        fn_count = g["total_false_negatives"]

        if fp_rate > 50:
            suggestions.append(
                f"  {gate}: {fp_rate:.0f}% false positive rate — "
                f"gate is too sensitive. Add exclusion rules or "
                f"raise thresholds to reduce noise."
            )
        elif fp_rate > 20:
            suggestions.append(
                f"  {gate}: {fp_rate:.0f}% false positive rate — "
                f"moderate noise. Review recent false positives "
                f"for patterns to exclude."
            )

        if fn_count > 0:
            suggestions.append(
                f"  {gate}: {fn_count} false negatives recorded — "
                f"gate is missing real issues. Consider adding "
                f"new check patterns."
            )

        # Check for all-pass gates (might be too lenient)
        if g["total_runs"] >= 5 and g["fail_count"] == 0:
            suggestions.append(
                f"  {gate}: Passed all {g['total_runs']} runs — "
                f"verify gate is actually checking something. "
                f"May be too lenient or misconfigured."
            )

    if suggestions:
        for s in suggestions:
            print(s)
    else:
        print("  All gates performing well. No adjustments needed.")

    print("=" * 60)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gate calibration tracker")
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record", help="Record a gate result")
    record.add_argument("--gate", required=True, help="Gate ID (e.g., B8, X7)")
    record.add_argument("--verdict", required=True, choices=["PASS", "FAIL", "SKIP"])
    record.add_argument("--findings", type=int, default=0, help="Number of findings")
    record.add_argument("--false-positives", type=int, default=0, help="Known false positives")
    record.add_argument("--false-negatives", type=int, default=0, help="Known false negatives")
    record.set_defaults(func=cmd_record)

    report = sub.add_parser("report", help="Show calibration report")
    report.set_defaults(func=cmd_report)

    suggest = sub.add_parser("suggest", help="Suggest gate tuning adjustments")
    suggest.set_defaults(func=cmd_suggest)

    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))
