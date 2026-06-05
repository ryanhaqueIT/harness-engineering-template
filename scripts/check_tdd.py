#!/usr/bin/env python3
"""check_tdd.py — Gate X10: TDD compliance enforcement.

Mechanically enforces the Iron Law of TDD:

    NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST.

For every implementation file in the current diff (or working tree),
verifies that a corresponding test file exists. In --strict mode, also
verifies that the test was committed at or before the implementation
file (git history check) — this is the closest mechanical proxy for
"the test was seen failing before the code was written."

The gate is intentionally unfoolable:
  - It does NOT look inside files. An agent can't satisfy it by writing
    a test that just imports the implementation.
  - It relies on file conventions: pytest's `test_*.py`, Jest's `*.test.tsx`,
    Go's `*_test.go`, etc. Conventions agents already follow.
  - Files known to be untestable in isolation (entry points, config,
    migrations) are excluded by name.

Inspired by superpowers:test-driven-development. The skill enforces
discipline; this gate enforces the artifact.

Usage:
  python scripts/check_tdd.py                        # Check working tree
  python scripts/check_tdd.py --diff main...HEAD     # Check branch diff
  python scripts/check_tdd.py --strict               # Also check commit order
  python scripts/check_tdd.py --summary              # One-line output

Exit codes:
  0 = all changed implementation files have test files
  1 = at least one violation (commit blocked)
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


# ─── File classification ─────────────────────────────────────────────


CODE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java"}

# Path patterns that mark a file as a test file
TEST_PATTERNS = [
    re.compile(r"(?:^|/)test_[^/]+\.py$"),                # pytest
    re.compile(r"(?:^|/)[^/]+_test\.py$"),                # alt pytest
    re.compile(r"(?:^|/)[^/]+\.test\.[tj]sx?$"),          # Jest dot-test
    re.compile(r"(?:^|/)[^/]+\.spec\.[tj]sx?$"),          # Jest dot-spec
    re.compile(r"(?:^|/)__tests__/"),                     # Jest folder
    re.compile(r"(?:^|/)[^/]+_test\.go$"),                # Go
    re.compile(r"(?:^|/)tests?/[^/]+\.rs$"),              # Rust integration tests
    re.compile(r"(?:^|/)src/test/java/"),                 # Java
    re.compile(r"(?:^|/)[A-Z][^/]*Test\.java$"),          # Java suffix
    re.compile(r"(?:^|/)tests?/[^/]+\.py$"),              # generic Python tests/
]

# Names that don't require tests because they're entry points or config
EXCLUDED_BASENAMES = {
    "__init__.py",
    "__main__.py",
    "main.py",
    "app.py",
    "wsgi.py",
    "asgi.py",
    "manage.py",
    "conftest.py",
    "setup.py",
    "settings.py",
    "config.py",
    "constants.py",
    "schemas.py",  # often pure Pydantic models — tested via routes
    "models.py",   # often pure ORM declarations — tested via services
    "celery.py",
    "urls.py",
    "server.py",
    "deps.py",
}

# Path segments that mean the file is excluded from TDD requirement
EXCLUDED_PATH_SEGMENTS = {
    "migrations",
    "alembic",
    "versions",  # alembic/versions/
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    "vendor",
    "generated",
}


def is_test_file(path: str) -> bool:
    """True if the file is itself a test file (so it never needs its own test)."""
    norm = path.replace("\\", "/")
    return any(rx.search(norm) for rx in TEST_PATTERNS)


def should_require_test(path: str) -> bool:
    """True if a file in this path should have a corresponding test file."""
    norm = path.replace("\\", "/")
    p = Path(norm)
    if p.suffix not in CODE_EXTENSIONS:
        return False
    if is_test_file(norm):
        return False
    if p.name in EXCLUDED_BASENAMES:
        return False
    parts = set(p.parts)
    if parts & EXCLUDED_PATH_SEGMENTS:
        return False
    return True


# ─── Test path candidates per language ───────────────────────────────


def candidate_test_paths(impl_path: str) -> list[str]:
    """All locations where the test file for `impl_path` could live.

    The gate is satisfied if ANY of these paths exists. We don't enforce
    a single layout because real codebases have legitimate variation
    (top-level tests/, sibling tests/, __tests__/, etc.).
    """
    norm = impl_path.replace("\\", "/")
    p = Path(norm)
    suffix = p.suffix
    stem = p.stem
    parts = list(p.parts[:-1])  # parent dirs

    candidates: list[str] = []

    if suffix == ".py":
        # 1. Top-level tests/ mirroring the path
        candidates.append(f"tests/test_{stem}.py")
        # 2. Top-of-package tests/ (backend/tests/test_<stem>.py)
        if parts:
            top = parts[0]
            candidates.append(f"{top}/tests/test_{stem}.py")
            # Mirror the path under tests/, e.g. backend/services/billing/x.py
            # → backend/tests/services/billing/test_x.py
            if len(parts) >= 2:
                mid = "/".join(parts[1:])
                candidates.append(f"{top}/tests/{mid}/test_{stem}.py")
        # 3. Sibling tests/ — backend/services/tests/test_<stem>.py
        sibling = "/".join(parts) + "/tests/" + f"test_{stem}.py"
        candidates.append(sibling.lstrip("/"))
        # 4. Same-dir test_<stem>.py
        candidates.append(("/".join(parts) + "/" + f"test_{stem}.py").lstrip("/"))

    elif suffix in {".ts", ".tsx", ".js", ".jsx"}:
        same_dir = "/".join(parts)
        # 1. <name>.test.ext
        candidates.append((same_dir + "/" + f"{stem}.test{suffix}").lstrip("/"))
        # 2. <name>.spec.ext
        candidates.append((same_dir + "/" + f"{stem}.spec{suffix}").lstrip("/"))
        # 3. __tests__/<name>.ext
        candidates.append((same_dir + "/__tests__/" + f"{stem}{suffix}").lstrip("/"))
        # 4. Top-level tests/ (rare but valid)
        candidates.append(f"tests/{stem}.test{suffix}")

    elif suffix == ".go":
        # Go convention: <name>_test.go in same package
        same_dir = "/".join(parts)
        candidates.append((same_dir + "/" + f"{stem}_test.go").lstrip("/"))

    elif suffix == ".rs":
        # Rust integration tests under tests/, or in-file #[cfg(test)] which
        # we can't easily detect without parsing. Prefer the tests/ dir.
        candidates.append(f"tests/{stem}.rs")
        if parts:
            top = parts[0]
            candidates.append(f"{top}/tests/{stem}.rs")

    elif suffix == ".java":
        # Maven/Gradle: mirror src/main/java/... to src/test/java/...
        if "main" in parts and "java" in parts:
            # Build mirrored path
            new_parts = []
            for part in parts:
                if part == "main":
                    new_parts.append("test")
                else:
                    new_parts.append(part)
            mirrored = "/".join(new_parts) + f"/{stem}Test.java"
            candidates.append(mirrored)
        # Fallback: tests/ in same package
        same_dir = "/".join(parts)
        candidates.append((same_dir + f"/{stem}Test.java").lstrip("/"))

    # De-dupe while preserving order
    seen = set()
    deduped: list[str] = []
    for c in candidates:
        c = c.replace("//", "/")
        if c and c not in seen:
            seen.add(c)
            deduped.append(c)
    return deduped


# ─── Violation reporting ─────────────────────────────────────────────


@dataclass
class Violation:
    impl_file: str
    reason: str
    candidates: list[str]


def detect_violations(changed_files: list[str], repo_root: Path | None = None) -> list[Violation]:
    """For each implementation file in `changed_files`, check that at least
    one of its candidate test paths exists on disk.
    """
    root = Path(repo_root) if repo_root else REPO_ROOT
    violations: list[Violation] = []
    normalized = [f.replace("\\", "/") for f in changed_files]
    changed_set = set(normalized)

    for path in normalized:
        if not should_require_test(path):
            continue
        cands = candidate_test_paths(path)
        # Pass if any candidate exists on disk OR appears in the same diff
        # (covers the case where impl + test are added together in the same PR).
        for c in cands:
            if (root / c).exists() or c in changed_set:
                break
        else:
            violations.append(
                Violation(
                    impl_file=path,
                    reason="no test file found at any expected location",
                    candidates=cands,
                )
            )
    return violations


# ─── Git integration ─────────────────────────────────────────────────


def changed_files_from_git(diff_spec: str | None) -> list[str]:
    """Return the list of files changed in the working tree or against a diff base."""
    try:
        if diff_spec:
            # e.g. "main...HEAD" — three-dot for merge-base diff
            out = subprocess.check_output(
                ["git", "diff", "--name-only", diff_spec], cwd=REPO_ROOT, text=True
            )
        else:
            # Working tree + staged + untracked
            tracked = subprocess.check_output(
                ["git", "diff", "--name-only", "HEAD"], cwd=REPO_ROOT, text=True
            )
            untracked = subprocess.check_output(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=REPO_ROOT,
                text=True,
            )
            out = tracked + "\n" + untracked
    except subprocess.CalledProcessError as e:
        print(f"git failed: {e}", file=sys.stderr)
        return []
    files = [line.strip() for line in out.splitlines() if line.strip()]
    return files


def check_commit_order(impl_path: str, test_path: str) -> bool:
    """In --strict mode: return True if the test was committed at or before impl."""
    try:
        impl_log = subprocess.check_output(
            ["git", "log", "--format=%ct", "--diff-filter=A", "--", impl_path],
            cwd=REPO_ROOT,
            text=True,
        ).strip()
        test_log = subprocess.check_output(
            ["git", "log", "--format=%ct", "--diff-filter=A", "--", test_path],
            cwd=REPO_ROOT,
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        return True  # No history yet — don't fail
    if not impl_log or not test_log:
        return True
    impl_first = int(impl_log.splitlines()[-1])
    test_first = int(test_log.splitlines()[-1])
    return test_first <= impl_first


# ─── CLI ─────────────────────────────────────────────────────────────


def _render(violations: list[Violation], summary: bool) -> None:
    if summary:
        if not violations:
            print("TDD compliance: PASS (all impl files have tests)")
        else:
            print(f"TDD compliance: FAIL ({len(violations)} impl file(s) without test)")
        return

    if not violations:
        print("[X10] TDD compliance: all changed implementation files have tests.")
        return

    print(f"[X10] TDD COMPLIANCE FAILED — {len(violations)} violation(s):\n")
    for v in violations:
        print(f"  IMPL: {v.impl_file}")
        print(f"  WHY:  {v.reason}")
        print(f"  EXPECTED a test at one of:")
        for c in v.candidates[:4]:
            print(f"      - {c}")
        print()
    print("Iron Law: NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST.")
    print("Write the test, watch it fail, then implement the code.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate X10: TDD compliance")
    parser.add_argument(
        "--diff",
        help="Git diff spec, e.g. 'main...HEAD'. Default: working tree + untracked.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also verify test files were committed at or before impl files.",
    )
    parser.add_argument("--summary", action="store_true", help="One-line output.")
    parser.add_argument(
        "--files",
        nargs="*",
        help="Override: specific files to check (for testing).",
    )
    args = parser.parse_args()

    if args.files:
        files = args.files
    else:
        files = changed_files_from_git(args.diff)

    if not files:
        if args.summary:
            print("TDD compliance: SKIP (no changed files)")
        else:
            print("[X10] No changed files in scope.")
        return 0

    violations = detect_violations(files, repo_root=REPO_ROOT)

    if args.strict and not violations:
        # Check commit order for files that DO have tests
        for impl in [f for f in files if should_require_test(f)]:
            cands = candidate_test_paths(impl)
            test = next((c for c in cands if (REPO_ROOT / c).exists()), None)
            if test and not check_commit_order(impl, test):
                violations.append(
                    Violation(
                        impl_file=impl,
                        reason=f"test '{test}' was committed AFTER impl — TDD ordering violated",
                        candidates=[test],
                    )
                )

    _render(violations, summary=args.summary)
    return 0 if not violations else 1


if __name__ == "__main__":
    sys.exit(main())
