#!/usr/bin/env python3
"""ratchet-t1.py — Tier 1 quality ratchet: violations only go down.

4 categories: lint_errors, format_errors, type_errors, test_failures

First run:  auto-creates baseline from current state
Later runs: compare to baseline, fail on regressions, lock in improvements

Usage:
  python3 .harness/ratchet-t1.py          # compare against baseline
  python3 .harness/ratchet-t1.py --show   # display current baseline
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ═══════════════════════════════════════════════════
# Color output
# ═══════════════════════════════════════════════════

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
DIM = "\033[2m"
NC = "\033[0m"


def color_supported() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


USE_COLOR = color_supported()


def c(code: str, text: str) -> str:
    if not USE_COLOR:
        return text
    return f"{code}{text}{NC}"


# ═══════════════════════════════════════════════════
# Paths
# ═══════════════════════════════════════════════════

REPO_ROOT = (
    Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
        ).stdout.strip()
    )
    if not os.environ.get("REPO_ROOT")
    else Path(os.environ["REPO_ROOT"])
)

HARNESS_DIR = REPO_ROOT / ".harness"
BASELINE_FILE = HARNESS_DIR / "t1-baseline.json"


# ═══════════════════════════════════════════════════
# Stack detection
# ═══════════════════════════════════════════════════


def has_python() -> bool:
    return (
        (REPO_ROOT / "pyproject.toml").exists()
        or (REPO_ROOT / "setup.py").exists()
        or any(REPO_ROOT.glob("**/*.py"))
    )


def has_nextjs() -> bool:
    return (REPO_ROOT / "package.json").exists()


# ═══════════════════════════════════════════════════
# Tool runners
# ═══════════════════════════════════════════════════


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.stdout + result.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""


def count_lint_errors() -> int:
    count = 0
    if has_python():
        output = _run(["ruff", "check", "."])
        match = re.search(r"Found (\d+) error", output)
        if match:
            count += int(match.group(1))
        elif output.strip():
            lines = output.strip().splitlines()
            count += len([line for line in lines if re.match(r".*:\d+:\d+:", line)])
    if has_nextjs() and (REPO_ROOT / "node_modules").exists():
        output = _run(
            [
                "npx",
                "eslint",
                ".",
                "--no-error-on-unmatched-pattern",
                "--format",
                "compact",
            ]
        )
        count += len(
            [line for line in output.strip().splitlines() if ": line " in line]
        )
    return count


def count_format_errors() -> int:
    count = 0
    if has_python():
        output = _run(["ruff", "format", "--check", "."])
        match = re.search(r"(\d+) file", output)
        if match and "would be reformatted" in output:
            count += int(match.group(1))
        elif output.strip():
            count += len(
                [
                    line
                    for line in output.strip().splitlines()
                    if line.strip()
                    and "All checks" not in line
                    and "0 files" not in line
                ]
            )
    if has_nextjs() and (REPO_ROOT / "node_modules").exists():
        output = _run(
            [
                "npx",
                "prettier",
                "--check",
                ".",
                "--ignore-unknown",
            ]
        )
        lines = [
            line
            for line in output.strip().splitlines()
            if line.strip() and "Checking" not in line and "All matched" not in line
        ]
        count += len(lines)
    return count


def count_type_errors() -> int:
    count = 0
    if has_python():
        output = _run(["pyright", "."])
        match = re.search(r"(\d+) error", output)
        if match:
            count += int(match.group(1))
    if has_nextjs() and (REPO_ROOT / "tsconfig.json").exists():
        output = _run(["npx", "tsc", "--noEmit"])
        # tsc outputs "error TS" for each error
        count += len(re.findall(r"error TS\d+", output))
    return count


def count_test_failures() -> int:
    count = 0
    if has_python():
        output = _run(["python3", "-m", "pytest", "--tb=no", "-q"])
        match = re.search(r"(\d+) failed", output)
        if match:
            count += int(match.group(1))
    if has_nextjs() and (REPO_ROOT / "package.json").exists():
        try:
            pkg = json.loads((REPO_ROOT / "package.json").read_text())
            test_script = pkg.get("scripts", {}).get("test", "")
            if test_script and "no test specified" not in test_script:
                output = _run(["npm", "test", "--", "--passWithNoTests"])
                match = re.search(r"(\d+) failed", output)
                if match:
                    count += int(match.group(1))
        except (json.JSONDecodeError, OSError):
            pass
    return count


# ═══════════════════════════════════════════════════
# Scan
# ═══════════════════════════════════════════════════


def scan_all() -> dict[str, int]:
    return {
        "lint_errors": count_lint_errors(),
        "format_errors": count_format_errors(),
        "type_errors": count_type_errors(),
        "test_failures": count_test_failures(),
    }


# ═══════════════════════════════════════════════════
# Baseline I/O
# ═══════════════════════════════════════════════════


def load_baseline() -> dict[str, int] | None:
    if not BASELINE_FILE.exists():
        return None
    try:
        data = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
        return data.get("violations", data)
    except (json.JSONDecodeError, OSError):
        return None


def save_baseline(violations: dict[str, int]) -> None:
    HARNESS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "tier": "t1-code-quality",
        "description": "T1 ratchet baseline — violations can only go down.",
        "violations": violations,
    }
    BASELINE_FILE.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


# ═══════════════════════════════════════════════════
# Display
# ═══════════════════════════════════════════════════


def print_header(title: str) -> None:
    width = 55
    print()
    print(c(BOLD, "=" * width))
    print(c(BOLD, f" {title}"))
    print(c(BOLD, "=" * width))


def print_comparison(baseline: dict, current: dict) -> None:
    print()
    header = f"  {'Category':<20} {'Baseline':>10} {'Current':>10} {'Delta':>8}  Status"
    print(c(BOLD, header))
    print(c(DIM, "  " + "-" * 62))

    for key in current:
        base_val = baseline.get(key, "N/A")
        curr_val = current[key]

        if base_val == "N/A":
            delta_str = "new"
            status = c(YELLOW, "NEW")
        else:
            delta = curr_val - base_val
            if delta > 0:
                delta_str = f"+{delta}"
                status = c(RED, "REGRESSED")
            elif delta < 0:
                delta_str = str(delta)
                status = c(GREEN, "IMPROVED")
            else:
                delta_str = "0"
                status = c(GREEN, "OK")

        base_display = str(base_val)
        print(f"  {key:<20} {base_display:>10} {curr_val:>10} {delta_str:>8}  {status}")
    print()


def show_baseline() -> None:
    print_header("T1 Ratchet Baseline")
    baseline = load_baseline()
    if baseline is None:
        msg = "\n  No baseline found. Run ratchet-t1.py to create.\n"
        print(c(YELLOW, msg))
        return
    print()
    for key, val in baseline.items():
        print(f"  {key:<20} {val}")
    print()
    print(c(DIM, f"  Source: {BASELINE_FILE}"))
    print()


# ═══════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════


def create_baseline() -> int:
    print_header("T1 Ratchet: Creating Baseline")
    print(c(CYAN, "\n  Scanning codebase...\n"))

    current = scan_all()
    save_baseline(current)

    print(c(GREEN, "  Baseline created:"))
    print()
    for key, val in current.items():
        print(f"    {key:<20} {val}")
    print()
    print(c(DIM, f"  Saved to: {BASELINE_FILE}"))
    print(c(GREEN, "\n  Ratchet initialized. Future runs will prevent regressions.\n"))
    return 0


def run_ratchet() -> int:
    baseline = load_baseline()
    if baseline is None:
        print(c(YELLOW, "\n  No baseline found. Auto-creating...\n"))
        return create_baseline()

    print_header("T1 Ratchet: Quality Gate")
    print(c(CYAN, "\n  Scanning codebase...\n"))
    current = scan_all()
    print_comparison(baseline, current)

    regressions = []
    improvements = []

    for key in current:
        if key not in baseline:
            continue
        if current[key] > baseline[key]:
            regressions.append(key)
        elif current[key] < baseline[key]:
            improvements.append(key)

    if regressions:
        print(c(RED, f"  RATCHET FAILED: {len(regressions)} category(ies) regressed:"))
        for r in regressions:
            print(c(RED, f"    - {r}: was {baseline[r]}, now {current[r]}"))
        print()
        print(c(RED, "  Fix regressions before committing.\n"))
        return 1

    if improvements:
        save_baseline(current)
        n = len(improvements)
        print(c(GREEN, f"  RATCHET IMPROVED: {n} category(ies) got better:"))
        for imp in improvements:
            print(c(GREEN, f"    - {imp}: was {baseline[imp]}, now {current[imp]}"))
        print(c(GREEN, "\n  Baseline updated. Improvement locked in.\n"))
    else:
        print(c(GREEN, "  RATCHET PASSED: No regressions.\n"))

    return 0


def main() -> int:
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return 0
    if "--show" in sys.argv:
        show_baseline()
        return 0
    return run_ratchet()


if __name__ == "__main__":
    sys.exit(main())
