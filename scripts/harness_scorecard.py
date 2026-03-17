#!/usr/bin/env python3
"""harness_scorecard.py — Grade a repo's harness engineering maturity.

Inspired by Alchemist Studios' HES v1 spec and markmishaev76/ai-harness-scorecard.

31 checks across 5 categories:
  1. Context Engineering (7 checks)
  2. Mechanical Enforcement (8 checks)
  3. Testing (6 checks)
  4. Application Legibility (5 checks)
  5. Entropy Management (5 checks)

Grading:
  A+ = 29-31   A = 26-28   B = 21-25   C = 16-20   D = 11-15   F = 0-10

Usage:
  python scripts/harness_scorecard.py

Exit code: always 0 (informational — this is a diagnostic, not a gate).
"""

from __future__ import annotations

import json
import os
import re
import stat
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
WHITE_ON_GREEN = "\033[97;42m"
WHITE_ON_RED = "\033[97;41m"
WHITE_ON_YELLOW = "\033[97;43m"
WHITE_ON_BLUE = "\033[97;44m"


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


# ═══════════════════════════════════════════════════
# Check helpers
# ═══════════════════════════════════════════════════

def file_exists(rel_path: str) -> bool:
    """Check if a file exists relative to repo root."""
    return (REPO_ROOT / rel_path).exists()


def dir_exists(rel_path: str) -> bool:
    """Check if a directory exists relative to repo root."""
    return (REPO_ROOT / rel_path).is_dir()


def file_under_lines(rel_path: str, max_lines: int) -> bool:
    """Check if a file exists and is under max_lines."""
    p = REPO_ROOT / rel_path
    if not p.exists():
        return False
    try:
        line_count = len(p.read_text(encoding="utf-8", errors="replace").splitlines())
        return line_count <= max_lines
    except OSError:
        return False


def file_is_executable(rel_path: str) -> bool:
    """Check if a file exists and is executable (or .sh on Windows)."""
    p = REPO_ROOT / rel_path
    if not p.exists():
        return False
    # On Windows, .sh files are not marked executable in the traditional sense
    if sys.platform == "win32":
        return True  # If file exists and is .sh, consider it executable on Windows
    try:
        return bool(p.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    except OSError:
        return False


def file_contains_pattern(rel_path: str, pattern: str) -> bool:
    """Check if a file contains a regex pattern."""
    p = REPO_ROOT / rel_path
    if not p.exists():
        return False
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        return bool(re.search(pattern, content))
    except OSError:
        return False


def count_files(directory: str, pattern: str = "*.py") -> int:
    """Count files matching a glob pattern in a directory."""
    d = REPO_ROOT / directory
    if not d.is_dir():
        return 0
    return len(list(d.rglob(pattern)))


def count_test_files() -> int:
    """Count test files across common test directories."""
    count = 0
    for test_dir in ["backend/tests", "tests", "frontend/__tests__", "test"]:
        d = REPO_ROOT / test_dir
        if d.is_dir():
            for ext in ["*.py", "*.ts", "*.tsx", "*.js", "*.jsx"]:
                count += len([f for f in d.rglob(ext) if "test" in f.name.lower() or f.name.startswith("test_")])
    # Also count files named *_test.py or test_*.py anywhere in backend/
    backend = REPO_ROOT / "backend"
    if backend.is_dir():
        for f in backend.rglob("*.py"):
            if "test" in f.parent.name and f.name != "__init__.py":
                count += 1
    return count


def count_source_files() -> int:
    """Count source files (non-test Python files in backend/)."""
    backend = REPO_ROOT / "backend"
    if not backend.is_dir():
        return 0
    count = 0
    for f in backend.rglob("*.py"):
        if ("__pycache__" not in str(f) and ".venv" not in str(f)
                and "site-packages" not in str(f) and "test" not in str(f)
                and f.name != "__init__.py"):
            count += 1
    return count


def has_progressive_disclosure_table(rel_path: str) -> bool:
    """Check if AGENTS.md contains a progressive disclosure table (markdown table with | )."""
    p = REPO_ROOT / rel_path
    if not p.exists():
        return False
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        # Look for a markdown table (lines with | ... | pattern)
        table_lines = [l for l in content.splitlines() if re.match(r"\s*\|.*\|.*\|", l)]
        return len(table_lines) >= 3  # header + separator + at least one row
    except OSError:
        return False


# ═══════════════════════════════════════════════════
# Check definitions
# ═══════════════════════════════════════════════════

CheckResult = tuple[bool, str]


def run_all_checks() -> dict[str, list[CheckResult]]:
    """Run all 31 checks and return results grouped by category."""
    results: dict[str, list[CheckResult]] = {}

    # ─── Category 1: Context Engineering (7 checks) ─────
    cat1: list[CheckResult] = []
    cat1.append((
        file_exists("AGENTS.md") and file_under_lines("AGENTS.md", 200),
        "AGENTS.md exists and is under 200 lines"
    ))
    cat1.append((
        has_progressive_disclosure_table("AGENTS.md"),
        "Progressive disclosure table in AGENTS.md"
    ))
    cat1.append((
        dir_exists("docs") and any(
            (REPO_ROOT / "docs").iterdir()
        ) if dir_exists("docs") else False,
        "docs/ directory with structured subdirectories"
    ))
    cat1.append((
        file_exists("PLANS.md"),
        "ExecPlan template (PLANS.md) exists"
    ))
    cat1.append((
        dir_exists("docs/design-docs"),
        "Design docs directory exists"
    ))
    cat1.append((
        dir_exists("docs/product-specs") or dir_exists("docs/specs"),
        "Product specs directory exists"
    ))
    cat1.append((
        dir_exists("docs/references"),
        "Reference docs directory exists"
    ))
    results["Context Engineering"] = cat1

    # ─── Category 2: Mechanical Enforcement (8 checks) ──
    cat2: list[CheckResult] = []
    cat2.append((
        file_exists("scripts/validate.sh") and file_is_executable("scripts/validate.sh"),
        "validate.sh exists and is executable"
    ))
    cat2.append((
        file_contains_pattern("scripts/validate.sh", r"ruff check|eslint|clippy"),
        "Lint gate exists (ruff/eslint/clippy)"
    ))
    cat2.append((
        file_contains_pattern("scripts/validate.sh", r"ruff format|prettier|black|rustfmt"),
        "Format gate exists"
    ))
    cat2.append((
        file_exists("scripts/check_imports.py"),
        "Import boundary checker exists"
    ))
    cat2.append((
        file_exists("scripts/check_golden_principles.py"),
        "Golden principles checker exists"
    ))
    cat2.append((
        file_exists("scripts/check_architecture.py"),
        "Architecture checker exists"
    ))
    cat2.append((
        dir_exists(".github/workflows"),
        "CI workflow exists (.github/workflows/)"
    ))
    cat2.append((
        _check_ci_blocks_merge(),
        "CI blocks merge (required status checks)"
    ))
    results["Mechanical Enforcement"] = cat2

    # ─── Category 3: Testing (6 checks) ─────────────────
    cat3: list[CheckResult] = []

    test_dir_found = any(
        dir_exists(d) for d in ["backend/tests", "tests", "frontend/__tests__", "test"]
    )
    cat3.append((test_dir_found, "Test directory exists"))

    test_count = count_test_files()
    cat3.append((test_count >= 10, f"At least 10 test files (found {test_count})"))

    source_count = count_source_files()
    ratio = round(test_count / source_count, 2) if source_count > 0 else 0.0
    cat3.append((ratio >= 0.5, f"Test-to-source ratio >= 0.5 (current: {ratio})"))

    cat3.append((
        file_exists("backend/pyproject.toml") and file_contains_pattern("backend/pyproject.toml", r"pytest")
        or file_exists("backend/setup.cfg") and file_contains_pattern("backend/setup.cfg", r"pytest")
        or file_exists("pytest.ini")
        or file_exists("package.json") and file_contains_pattern("package.json", r"jest|vitest")
        or file_contains_pattern("scripts/validate.sh", r"pytest|jest|cargo.test"),
        "pytest/jest/cargo-test configured"
    ))

    cat3.append((
        any(file_exists(f) for f in [
            "scripts/validate_e2e.sh", "scripts/e2e_test.py",
            "scripts/e2e_real_test.py", "scripts/e2e_real_call_test.py",
        ]),
        "E2E test script exists"
    ))

    cat3.append((
        any(file_exists(f) for f in [
            "scripts/check_ui_legibility.sh", "scripts/check_frontend.sh",
        ]),
        "UI validation script exists"
    ))
    results["Testing"] = cat3

    # ─── Category 4: Application Legibility (5 checks) ──
    cat4: list[CheckResult] = []
    cat4.append((
        any(file_exists(f) for f in [
            "scripts/check_frontend.sh", "scripts/check_ui_legibility.sh",
        ]),
        "Frontend UI check script exists"
    ))
    cat4.append((
        file_exists("scripts/boot_worktree.sh"),
        "Per-worktree boot script exists"
    ))
    cat4.append((
        file_exists("scripts/check_e2e_deployed.sh"),
        "E2E deployed check script exists"
    ))
    cat4.append((
        any(file_exists(f) for f in [
            "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
            "docker-compose.observability.yml",
            "terraform/main.tf", "infrastructure/main.tf",
        ]),
        "Dockerfile or deployment config exists"
    ))
    cat4.append((
        file_contains_pattern("scripts/validate.sh", r"/health")
        or file_contains_pattern("scripts/check_e2e_deployed.sh", r"/health")
        or any(
            file_contains_pattern(f, r"['\"]/?health['\"]")
            for f in ["backend/main.py", "backend/app.py"]
            if file_exists(f)
        ),
        "Health check endpoint defined"
    ))
    results["Application Legibility"] = cat4

    # ─── Category 5: Entropy Management (5 checks) ──────
    cat5: list[CheckResult] = []
    cat5.append((
        file_exists(".github/workflows/doc-gardening.yml"),
        "Doc-gardening workflow exists"
    ))
    cat5.append((
        file_exists(".github/workflows/quality-scan.yml"),
        "Quality scan workflow exists"
    ))
    cat5.append((
        any(file_exists(f) for f in [
            "docs/TECH_DEBT.md", "TECH_DEBT.md",
            "docs/QUALITY_SCORE.md", "QUALITY_SCORE.md",
        ]),
        "Tech debt tracker exists"
    ))
    cat5.append((
        file_exists(".harness/baseline.json"),
        "Ratchet baseline exists (.harness/baseline.json)"
    ))
    cat5.append((
        any(file_exists(f) for f in [
            "docs/QUALITY_SCORE.md", "QUALITY_SCORE.md",
        ]),
        "QUALITY_SCORE.md or equivalent exists"
    ))
    results["Entropy Management"] = cat5

    return results


def _check_ci_blocks_merge() -> bool:
    """Check if CI is configured to block merges (look for required checks in workflow)."""
    workflows_dir = REPO_ROOT / ".github" / "workflows"
    if not workflows_dir.is_dir():
        return False
    for wf in workflows_dir.glob("*.yml"):
        try:
            content = wf.read_text(encoding="utf-8", errors="replace")
            # Look for patterns that indicate CI blocks merge:
            # - 'on: pull_request' or 'on: push' with branches
            # - status checks, branch protection references
            if re.search(r"pull_request|push:.*branches", content):
                return True
        except OSError:
            continue
    return False


# ═══════════════════════════════════════════════════
# Grading
# ═══════════════════════════════════════════════════

def compute_grade(total_passed: int) -> str:
    """Convert total checks passed to a letter grade."""
    if total_passed >= 29:
        return "A+"
    elif total_passed >= 26:
        return "A"
    elif total_passed >= 21:
        return "B"
    elif total_passed >= 16:
        return "C"
    elif total_passed >= 11:
        return "D"
    else:
        return "F"


def grade_color(grade: str) -> str:
    """Get the color code for a grade."""
    if grade.startswith("A"):
        return WHITE_ON_GREEN
    elif grade == "B":
        return WHITE_ON_BLUE
    elif grade == "C":
        return WHITE_ON_YELLOW
    else:
        return WHITE_ON_RED


# ═══════════════════════════════════════════════════
# Display
# ═══════════════════════════════════════════════════

def print_scorecard(results: dict[str, list[CheckResult]]) -> None:
    """Print the full scorecard with grade and detailed results."""
    total_passed = sum(
        1 for checks in results.values() for passed, _ in checks if passed
    )
    total_checks = sum(len(checks) for checks in results.values())
    grade = compute_grade(total_passed)

    # Header
    print()
    print(c(BOLD, "=" * 64))
    print(c(BOLD, " HARNESS ENGINEERING SCORECARD"))
    print(c(BOLD, "=" * 64))
    print()

    # Big grade display
    gc = grade_color(grade)
    print(f"  Grade: {c(gc, f'  {grade}  ')}   ({total_passed}/{total_checks} checks passed)")
    print()

    # Category breakdown
    for category, checks in results.items():
        cat_passed = sum(1 for passed, _ in checks if passed)
        cat_total = len(checks)

        if cat_passed == cat_total:
            cat_status = c(GREEN, f"{cat_passed}/{cat_total}")
        elif cat_passed >= cat_total // 2:
            cat_status = c(YELLOW, f"{cat_passed}/{cat_total}")
        else:
            cat_status = c(RED, f"{cat_passed}/{cat_total}")

        print(c(BOLD, f"  {category} [{cat_status}{c(BOLD, ']')}"))

        for passed, description in checks:
            if passed:
                mark = c(GREEN, "[PASS]")
            else:
                mark = c(RED, "[FAIL]")
            print(f"    {mark} {description}")

        print()

    # Footer
    print(c(DIM, "-" * 64))
    print(c(DIM, f"  Repo: {REPO_ROOT.name}"))
    print(c(DIM, f"  31 checks across 5 categories"))
    print()

    # Actionable next steps for failures
    failures = [
        (cat, desc)
        for cat, checks in results.items()
        for passed, desc in checks
        if not passed
    ]
    if failures:
        print(c(YELLOW, "  Next steps to improve your grade:"))
        for cat, desc in failures[:5]:  # Show top 5
            print(c(DIM, f"    - [{cat}] {desc}"))
        if len(failures) > 5:
            print(c(DIM, f"    ... and {len(failures) - 5} more"))
        print()


# ═══════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════

def main() -> int:
    """Entry point."""
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return 0

    results = run_all_checks()
    print_scorecard(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
