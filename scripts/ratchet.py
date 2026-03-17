#!/usr/bin/env python3
"""ratchet.py — Quality ratchet: violations can only go down, never up.

Inspired by Alchemist Studios' HES v1 spec and ai-harness-scorecard.

How it works:
  First run (--init): scan codebase, count violations per category,
                      save as .harness/baseline.json
  Subsequent runs:    scan again, compare to baseline
    - NEW violations > baseline  -> FAIL (you made it worse)
    - violations <= baseline     -> PASS (you didn't regress)
    - violations < baseline      -> UPDATE baseline (lock in improvement)

Usage:
  python scripts/ratchet.py          # compare against baseline
  python scripts/ratchet.py --init   # force-create baseline
  python scripts/ratchet.py --show   # display current baseline

Exit code 0 = pass, 1 = regression detected or error.
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
    """Check if terminal supports color."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


USE_COLOR = color_supported()


def c(code: str, text: str) -> str:
    """Apply color code if supported."""
    if not USE_COLOR:
        return text
    return f"{code}{text}{NC}"


# ═══════════════════════════════════════════════════
# Paths
# ═══════════════════════════════════════════════════

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS_DIR = REPO_ROOT / ".harness"
BASELINE_FILE = HARNESS_DIR / "baseline.json"
BACKEND_DIR = REPO_ROOT / "backend"
SCRIPTS_DIR = REPO_ROOT / "scripts"


# ═══════════════════════════════════════════════════
# Violation counters
# ═══════════════════════════════════════════════════

def _run_cmd(cmd: list[str], cwd: Path | None = None) -> str:
    """Run a command and return stdout+stderr. Never raises."""
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
    """Count lint errors from ruff check."""
    output = _run_cmd(["ruff", "check", "."], cwd=BACKEND_DIR)
    if not output.strip():
        return 0
    # ruff outputs one violation per line, with a summary like "Found X errors"
    match = re.search(r"Found (\d+) error", output)
    if match:
        return int(match.group(1))
    # Fallback: count non-empty lines that look like violations (file:line:col)
    lines = [l for l in output.strip().splitlines() if re.match(r".*:\d+:\d+:", l)]
    return len(lines)


def count_format_errors() -> int:
    """Count format errors from ruff format --check."""
    output = _run_cmd(["ruff", "format", "--check", "."], cwd=BACKEND_DIR)
    if not output.strip():
        return 0
    # ruff format --check outputs "Would reformat: <file>" for each file
    lines = [l for l in output.strip().splitlines()
             if l.strip() and not l.startswith("All checks") and not l.startswith("0 files")]
    # Also check: "X files would be reformatted"
    match = re.search(r"(\d+) file", output)
    if match and "would be reformatted" in output:
        return int(match.group(1))
    return len(lines)


def count_import_violations() -> int:
    """Count import boundary violations."""
    script = SCRIPTS_DIR / "check_imports.py"
    if not script.exists():
        return 0
    output = _run_cmd([sys.executable, str(script)])
    match = re.search(r"violations? \((\d+)\)", output)
    if match:
        return int(match.group(1))
    return 0


def count_architecture_violations() -> int:
    """Count architecture violations."""
    script = SCRIPTS_DIR / "check_architecture.py"
    if not script.exists():
        return 0
    output = _run_cmd([sys.executable, str(script)])
    match = re.search(r"violations? \((\d+)\)", output)
    if match:
        return int(match.group(1))
    return 0


def count_golden_principle_violations() -> int:
    """Count golden principle violations."""
    script = SCRIPTS_DIR / "check_golden_principles.py"
    if not script.exists():
        return 0
    output = _run_cmd([sys.executable, str(script)])
    match = re.search(r"violations? \((\d+)\)", output)
    if match:
        return int(match.group(1))
    return 0


def count_todo_fixme() -> int:
    """Count TODO/FIXME/HACK comments in Python files."""
    count = 0
    if not BACKEND_DIR.exists():
        return 0
    for f in BACKEND_DIR.rglob("*.py"):
        if "__pycache__" in str(f) or ".venv" in str(f) or "site-packages" in str(f):
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            count += len(re.findall(r"\b(TODO|FIXME|HACK|XXX)\b", content))
        except OSError:
            continue
    return count


def count_god_files() -> int:
    """Count files over 300 lines."""
    count = 0
    if not BACKEND_DIR.exists():
        return 0
    for f in BACKEND_DIR.rglob("*.py"):
        if "__pycache__" in str(f) or ".venv" in str(f) or "site-packages" in str(f):
            continue
        if f.name == "__init__.py":
            continue
        try:
            lines = len(f.read_text(encoding="utf-8", errors="replace").splitlines())
            if lines > 300:
                count += 1
        except OSError:
            continue
    return count


def compute_test_coverage_ratio() -> float:
    """Compute test files / source files ratio."""
    if not BACKEND_DIR.exists():
        return 0.0
    source_files = []
    test_files = []
    for f in BACKEND_DIR.rglob("*.py"):
        if "__pycache__" in str(f) or ".venv" in str(f) or "site-packages" in str(f):
            continue
        if f.name == "__init__.py":
            continue
        if "test" in f.name or "test" in str(f.parent):
            test_files.append(f)
        else:
            source_files.append(f)
    if not source_files:
        return 0.0
    return round(len(test_files) / len(source_files), 3)


# ═══════════════════════════════════════════════════
# Scan all categories
# ═══════════════════════════════════════════════════

def scan_all() -> dict[str, int | float]:
    """Run all checks and return violation counts."""
    return {
        "lint_errors": count_lint_errors(),
        "format_errors": count_format_errors(),
        "import_violations": count_import_violations(),
        "architecture_violations": count_architecture_violations(),
        "golden_principle_violations": count_golden_principle_violations(),
        "todo_fixme_count": count_todo_fixme(),
        "god_files": count_god_files(),
        "test_coverage_ratio": compute_test_coverage_ratio(),
    }


# ═══════════════════════════════════════════════════
# Baseline I/O
# ═══════════════════════════════════════════════════

def load_baseline() -> dict[str, int | float] | None:
    """Load baseline from disk. Returns None if missing."""
    if not BASELINE_FILE.exists():
        return None
    try:
        data = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
        return data.get("violations", data)
    except (json.JSONDecodeError, OSError):
        return None


def save_baseline(violations: dict[str, int | float]) -> None:
    """Save baseline to disk."""
    HARNESS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "description": "Ratchet baseline — violations can only go down, never up.",
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
    """Print a prominent header."""
    width = 60
    print()
    print(c(BOLD, "=" * width))
    print(c(BOLD, f" {title}"))
    print(c(BOLD, "=" * width))


def print_comparison(baseline: dict, current: dict) -> None:
    """Print side-by-side comparison table."""
    print()
    header = f"  {'Category':<32} {'Baseline':>10} {'Current':>10} {'Delta':>8}  Status"
    print(c(BOLD, header))
    print(c(DIM, "  " + "-" * 78))

    for key in current:
        base_val = baseline.get(key, "N/A")
        curr_val = current[key]

        if base_val == "N/A":
            delta_str = "new"
            status = c(YELLOW, "NEW")
        else:
            # For test_coverage_ratio, higher is better (invert the logic)
            if key == "test_coverage_ratio":
                if curr_val > base_val:
                    delta = curr_val - base_val
                    delta_str = f"+{delta:.3f}"
                    status = c(GREEN, "IMPROVED")
                elif curr_val < base_val:
                    delta = base_val - curr_val
                    delta_str = f"-{delta:.3f}"
                    status = c(RED, "REGRESSED")
                else:
                    delta_str = "0"
                    status = c(GREEN, "OK")
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

        base_display = f"{base_val}" if base_val != "N/A" else "N/A"
        curr_display = f"{curr_val}"
        print(f"  {key:<32} {base_display:>10} {curr_display:>10} {delta_str:>8}  {status}")

    print()


def show_baseline() -> None:
    """Display current baseline without running checks."""
    print_header("Ratchet Baseline")
    baseline = load_baseline()
    if baseline is None:
        print(c(YELLOW, "\n  No baseline found. Run with --init to create one.\n"))
        return
    print()
    for key, val in baseline.items():
        print(f"  {key:<32} {val}")
    print()
    print(c(DIM, f"  Source: {BASELINE_FILE}"))
    print()


# ═══════════════════════════════════════════════════
# Main logic
# ═══════════════════════════════════════════════════

def init_baseline() -> int:
    """Force-create baseline from current state."""
    print_header("Ratchet: Initializing Baseline")
    print(c(CYAN, "\n  Scanning codebase...\n"))

    current = scan_all()
    save_baseline(current)

    print(c(GREEN, "  Baseline created:"))
    print()
    for key, val in current.items():
        print(f"    {key:<32} {val}")
    print()
    print(c(DIM, f"  Saved to: {BASELINE_FILE}"))
    print(c(GREEN, "\n  Ratchet initialized. Future runs will prevent regressions.\n"))
    return 0


def run_ratchet() -> int:
    """Compare current state against baseline."""
    print_header("Ratchet: Quality Gate")

    baseline = load_baseline()
    if baseline is None:
        print(c(YELLOW, "\n  No baseline found. Creating initial baseline...\n"))
        return init_baseline()

    print(c(CYAN, "\n  Scanning codebase...\n"))
    current = scan_all()

    print_comparison(baseline, current)

    # Check for regressions
    regressions = []
    improvements = []

    for key in current:
        if key not in baseline:
            continue
        base_val = baseline[key]
        curr_val = current[key]

        if key == "test_coverage_ratio":
            # Higher is better for test coverage
            if curr_val < base_val:
                regressions.append(key)
            elif curr_val > base_val:
                improvements.append(key)
        else:
            # Lower is better for violations
            if curr_val > base_val:
                regressions.append(key)
            elif curr_val < base_val:
                improvements.append(key)

    if regressions:
        print(c(RED, f"  RATCHET FAILED: {len(regressions)} category(ies) regressed:"))
        for r in regressions:
            base_val = baseline[r]
            curr_val = current[r]
            print(c(RED, f"    - {r}: was {base_val}, now {curr_val}"))
        print()
        print(c(RED, "  You made it worse. Fix the regressions before committing."))
        print(c(DIM, "  The ratchet only turns one way: toward better code.\n"))
        return 1

    if improvements:
        # Lock in improvements by updating baseline
        save_baseline(current)
        print(c(GREEN, f"  RATCHET IMPROVED: {len(improvements)} category(ies) got better:"))
        for imp in improvements:
            base_val = baseline[imp]
            curr_val = current[imp]
            print(c(GREEN, f"    - {imp}: was {base_val}, now {curr_val}"))
        print()
        print(c(GREEN, "  Baseline updated. Improvement locked in."))
        print(c(DIM, f"  Saved to: {BASELINE_FILE}\n"))
    else:
        print(c(GREEN, "  RATCHET PASSED: No regressions detected."))
        print(c(DIM, "  All categories at or better than baseline.\n"))

    return 0


def main() -> int:
    """Entry point."""
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(__doc__)
        return 0

    if "--show" in args:
        show_baseline()
        return 0

    if "--init" in args:
        return init_baseline()

    return run_ratchet()


if __name__ == "__main__":
    sys.exit(main())
