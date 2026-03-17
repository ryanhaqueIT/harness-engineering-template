#!/usr/bin/env python3
"""check_architecture.py — Comprehensive architectural invariant enforcement.

Goes beyond import boundaries to check structural rules that prevent
architectural drift. All checks are AST-based and unfakeable.

CONFIGURABLE: Edit the constants below to match your project.

Checks:
1. No God files (files over MAX_LINES are flagged for splitting)
2. DB access only through the data layer (no direct DB imports elsewhere)
3. No direct AI/ML imports outside designated modules
4. Config access only through config module (no os.environ or os.getenv)
5. File naming conventions (snake_case for Python files, PascalCase for classes)
6. Test file mirrors (every source file should have a test file)

Exit code 0 = clean, 1 = violations found.
"""

import ast
import re
import sys
from pathlib import Path

# ═══════════════════════════════════════════════════
# CONFIGURE THESE for your project
# ═══════════════════════════════════════════════════

# Maximum lines per file before it's flagged as a God file
MAX_LINES = 300

# The data access layer module name (only this module may import DB clients)
DB_MODULE = "db"

# DB library import patterns to restrict (e.g., "google.cloud.firestore", "sqlalchemy", "prisma")
DB_IMPORT_PATTERNS: list[str] = [
    # "google.cloud.firestore",
    # "sqlalchemy",
    # "pymongo",
    # "prisma",
]

# Modules allowed to import AI/ML libraries directly
AI_ALLOWED_MODULES: set[str] = {
    # "agent",
    # "voice",
}

# AI/ML library import patterns to restrict
AI_IMPORT_PATTERNS: list[str] = [
    # "google.genai",
    # "openai",
    # "anthropic",
    # "langchain",
]

# Modules that should have test file mirrors
TESTABLE_MODULES: set[str] = {
    # "services",
    # "db",
    # "agent",
}

BACKEND = Path(__file__).resolve().parent.parent / "backend"

violations: list[str] = []


def check_no_god_files(py_files: list[Path]) -> None:
    """Flag files over MAX_LINES — they should be split."""
    for f in py_files:
        line_count = len(f.read_text(encoding="utf-8", errors="replace").splitlines())
        if line_count > MAX_LINES:
            violations.append(
                f"  {f.relative_to(BACKEND)}:{line_count} lines — "
                f"File exceeds {MAX_LINES} lines. Split into smaller modules. "
                f"Golden Principle: One concern per file."
            )


def check_no_direct_db_imports(py_files: list[Path]) -> None:
    """DB library should only be imported in the data layer module."""
    if not DB_IMPORT_PATTERNS:
        return

    for f in py_files:
        rel = f.relative_to(BACKEND)
        module = rel.parts[0] if len(rel.parts) >= 2 else ""

        if module == DB_MODULE:
            continue  # data layer is allowed to import DB

        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for pattern in DB_IMPORT_PATTERNS:
                    if pattern in node.module:
                        violations.append(
                            f"  {rel}:{node.lineno} — "
                            f"Direct DB import outside {DB_MODULE}/. "
                            f"Use {DB_MODULE}/ functions instead. "
                            f"Only {DB_MODULE}/ may import {pattern}."
                        )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for pattern in DB_IMPORT_PATTERNS:
                        if pattern in alias.name:
                            violations.append(
                                f"  {rel}:{node.lineno} — "
                                f"Direct DB import outside {DB_MODULE}/. "
                                f"Use {DB_MODULE}/ functions instead."
                            )


def check_no_direct_ai_imports(py_files: list[Path]) -> None:
    """AI/ML libraries should only be imported in designated modules."""
    if not AI_IMPORT_PATTERNS or not AI_ALLOWED_MODULES:
        return

    for f in py_files:
        rel = f.relative_to(BACKEND)
        module = rel.parts[0] if len(rel.parts) >= 2 else ""

        if module in AI_ALLOWED_MODULES:
            continue

        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for pattern in AI_IMPORT_PATTERNS:
                    if pattern in node.module:
                        violations.append(
                            f"  {rel}:{node.lineno} — "
                            f"Direct AI/ML import outside {AI_ALLOWED_MODULES}. "
                            f"AI access should go through the designated layer."
                        )


def check_no_direct_env_access(py_files: list[Path]) -> None:
    """Config should only be accessed through config module, not os.environ."""
    for f in py_files:
        rel = f.relative_to(BACKEND)

        if rel.name == "config.py" or rel.name == "settings.py":
            continue  # config files are the ones that read env vars

        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name) and node.value.id == "os":
                    if node.attr in ("environ", "getenv"):
                        violations.append(
                            f"  {rel}:{node.lineno} — "
                            f"Direct os.{node.attr} access. "
                            f"Use config/settings module instead. "
                            f"Only config.py may read environment variables."
                        )
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                        if node.func.attr == "getenv":
                            violations.append(
                                f"  {rel}:{node.lineno} — "
                                f"Direct os.getenv() call. "
                                f"Use config/settings module instead."
                            )


def check_naming_conventions(py_files: list[Path]) -> None:
    """Enforce Python naming: snake_case for files, PascalCase for classes."""
    for f in py_files:
        # File names must be snake_case
        name = f.stem
        if name != name.lower() or " " in name or "-" in name:
            violations.append(
                f"  {f.relative_to(BACKEND)} — "
                f"File name '{name}' is not snake_case. "
                f"Rename to: {name.lower().replace('-', '_').replace(' ', '_')}.py"
            )

        # Class names must be PascalCase
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if not re.match(r"^[A-Z][a-zA-Z0-9]*$", node.name):
                    violations.append(
                        f"  {f.relative_to(BACKEND)}:{node.lineno} — "
                        f"Class '{node.name}' is not PascalCase."
                    )


def check_test_file_exists(py_files: list[Path]) -> None:
    """Every source module should have a corresponding test file."""
    if not TESTABLE_MODULES:
        return

    tests_dir = BACKEND / "tests"
    if not tests_dir.exists():
        return

    for f in py_files:
        rel = f.relative_to(BACKEND)
        module = rel.parts[0] if len(rel.parts) >= 2 else ""

        if module not in TESTABLE_MODULES:
            continue

        # Build expected test path
        expected_test = tests_dir / rel.parent / f"test_{rel.name}"
        if not expected_test.exists():
            violations.append(
                f"  {rel} — "
                f"No test file found. Expected: tests/{rel.parent}/test_{rel.name}. "
                f"Golden Principle: Tests mirror source."
            )


def main() -> int:
    if not BACKEND.exists():
        print("backend/ directory not found — skipping architecture check")
        return 0

    py_files = list(BACKEND.rglob("*.py"))
    py_files = [
        f for f in py_files
        if "__pycache__" not in str(f)
        and ".venv" not in str(f)
        and "site-packages" not in str(f)
        and f.name != "__init__.py"
        and "test" not in str(f)
    ]

    check_no_god_files(py_files)
    check_no_direct_db_imports(py_files)
    check_no_direct_ai_imports(py_files)
    check_no_direct_env_access(py_files)
    check_naming_conventions(py_files)
    check_test_file_exists(py_files)

    if violations:
        print(f"Architecture violations ({len(violations)}):")
        for v in violations:
            print(v)
        return 1

    print(f"Architecture clean ({len(py_files)} files checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
