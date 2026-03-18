#!/usr/bin/env python3
"""Feature list gate — enforces PRD completion.

Reads .harness/feature_list.json and reports on feature verification status.
This script is a READ-ONLY gate. It never modifies the feature list.
Only the implementing agent may flip passes: false -> true after verification.

Based on: Anthropic's "Effective harnesses for long-running agents" (Nov 2025)
"""

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Feature list gate — PRD completion check")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Concise one-line output (for CI/validate.sh)",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Check only features in this category (e.g. functional, ui, security)",
    )
    args = parser.parse_args()

    # Find repo root (walk up from script location)
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    feature_file = repo_root / ".harness" / "feature_list.json"

    if not feature_file.exists():
        print("SKIP: No .harness/feature_list.json found")
        return 0

    with open(feature_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    features = data.get("features", [])

    # Filter by category if requested
    if args.category:
        features = [ft for ft in features if ft.get("category") == args.category]
        if not features:
            print(f"No features found in category '{args.category}'")
            return 0

    total = len(features)
    passing = sum(1 for ft in features if ft.get("passes"))
    failing = total - passing

    if args.summary:
        status = "PASS" if failing == 0 else "FAIL"
        category_label = f" [{args.category}]" if args.category else ""
        print(f"Features{category_label}: {passing}/{total} passing — {status}")
        return 0 if failing == 0 else 1

    # Detailed output
    print(f"Feature List Gate — {passing}/{total} passing")
    print("=" * 60)

    if failing == 0:
        print("All features verified. Gate passes.")
        return 0

    print(f"\n{failing} feature(s) NOT yet verified:\n")

    for ft in features:
        if ft.get("passes"):
            continue
        fid = ft.get("id", "???")
        desc = ft.get("description", "(no description)")
        cat = ft.get("category", "unknown")
        pri = ft.get("priority", "?")
        steps = ft.get("steps", [])

        print(f"  [{fid}] (priority {pri}, {cat})")
        print(f"    {desc}")
        for i, step in enumerate(steps, 1):
            print(f"      {i}. {step}")
        print()

    print(f"RESULT: {failing} failing — gate does NOT pass.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
