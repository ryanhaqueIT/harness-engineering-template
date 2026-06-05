#!/usr/bin/env python3
"""check_mutation.py — Mutation gate: prove tests are MEANINGFUL, not just present.

This is the ungameable complement to check_tdd.py. Where the TDD gate proves a
test FILE exists for every implementation file, this gate proves the test
actually constrains behavior. It does so with lightweight, deterministic
mutation testing:

    For each changed application impl file that has a mapped test, apply a
    small set of deterministic mutations one at a time, run the mapped test,
    and require the test to FAIL on each mutation. If the test still PASSES
    under a mutation, that mutation "survived" — the test is vacuous, and the
    gate records a violation.

A test that passes whether the code says `>=` or `>`, `True` or `False`,
`return x` or `return None`, `+` or `-`, is not testing anything. This gate
catches exactly that.

Self-eating protection: the gate only mutates real application source. It
skips files under scripts/, .claude/, tests/, migrations, and everything
check_tdd already excludes — so it never mutates itself or other gates.

Determinism & bounds: mutations are a fixed, ordered set of textual rewrites
(no randomness). Files-per-run, mutations-per-file, and a per-test-run timeout
are all capped so the gate stays fast and predictable in CI.

Mutation operators (applied one at a time):
  - comparison swaps:  <  >   <=  >=   ==  !=
  - boolean flip:      True <-> False
  - return value drop: 'return <expr>' -> 'return None'
  - arithmetic swap:   +  <->  -

Usage:
  python scripts/check_mutation.py                       # Check working tree
  python scripts/check_mutation.py --files backend/x.py  # Override file list
  python scripts/check_mutation.py --summary             # One-line output

Exit codes:
  0 = no eligible changed files, OR every eligible file's test caught all mutations
  1 = at least one vacuous test (a mutation survived) — commit blocked
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent

# Reuse check_tdd's classification + test-path mapping so the two gates agree
# on what counts as an impl file and where its test lives.
sys.path.insert(0, str(SCRIPTS_DIR))
import check_tdd  # noqa: E402


# ─── Bounds (deterministic, CI-friendly) ─────────────────────────────

MAX_FILES_PER_RUN = 10          # cap eligible files mutated in one run
MAX_MUTATIONS_PER_FILE = 8      # cap mutation variants tried per file
PER_TEST_TIMEOUT_SECONDS = 60   # cap each pytest invocation


# ─── Self-eating protection ──────────────────────────────────────────
#
# Only mutate genuine application source. These path segments are never
# mutated, on top of everything check_tdd already excludes.

MUTATION_EXCLUDED_SEGMENTS = {
    "scripts",
    ".claude",
    "tests",
    "test",
    "migrations",
    "alembic",
    "versions",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    "vendor",
    "generated",
    "agents",
    "playbooks",
    "observability",
    "docs",
}


# ─── Mutation model ──────────────────────────────────────────────────


@dataclass
class Mutation:
    """A single deterministic source rewrite."""

    description: str
    mutated: str


@dataclass
class EligibleFile:
    """An impl file that is eligible for mutation, plus its mapped test."""

    impl_file: str
    test_file: str


@dataclass
class Violation:
    """A file whose test failed to catch one or more mutations."""

    impl_file: str
    test_file: str
    survived: list[str] = field(default_factory=list)


# ─── Mutation generation ─────────────────────────────────────────────
#
# Each operator finds occurrences in the source and, for each occurrence,
# produces one full-source variant with exactly that occurrence rewritten.
# Operators are applied independently and deterministically.

# Comparison swaps. Order longer operators first so `>=` isn't half-matched
# by a `>` rule. We match on a placeholder token then map to its swap.
_COMPARISON_SWAPS = [
    ("<=", ">="),
    (">=", "<="),
    ("==", "!="),
    ("!=", "=="),
    ("<", ">"),
    (">", "<"),
]

# Regex that captures any comparison operator as a whole token. We require
# that '<'/'>' are not part of '<='/'>=' by using negative lookarounds.
_COMPARISON_RE = re.compile(r"(<=|>=|==|!=|<(?!=)|>(?!=)|(?<![<>!=])<|(?<![<>!=])>)")

_ARITHMETIC_SWAP = {"+": "-", "-": "+"}
# Match a binary + or - surrounded by spaces (avoids unary +/-, ++ , -- , and
# augmented assignment +=/-= which would have an '=' immediately after).
_ARITHMETIC_RE = re.compile(r"(?<=\s)([+-])(?=\s)")

# `return <expr>` where expr is not already None / bare return.
_RETURN_RE = re.compile(r"^(\s*)return\s+(?!None\b)(.+?)\s*$")

# Boolean literals as whole words.
_BOOL_RE = re.compile(r"\b(True|False)\b")
_BOOL_FLIP = {"True": "False", "False": "True"}


def _occurrences(line: str, regex: re.Pattern[str]):
    """Yield (start, end, matched_text) for each non-overlapping match."""
    for m in regex.finditer(line):
        yield m.start(), m.end(), m.group(0)


def generate_mutations(source: str, max_mutations: int = MAX_MUTATIONS_PER_FILE) -> list[Mutation]:
    """Produce a bounded, deterministic list of single-point source mutations.

    Each mutation is the full source with exactly one occurrence rewritten,
    so the mapped test can be run against it independently.
    """
    lines = source.splitlines(keepends=True)
    mutations: list[Mutation] = []

    def add(line_idx: int, new_line: str, desc: str) -> None:
        mutated_lines = list(lines)
        mutated_lines[line_idx] = new_line
        mutations.append(Mutation(description=desc, mutated="".join(mutated_lines)))

    for i, raw in enumerate(lines):
        newline = ""
        line = raw
        if line.endswith("\n"):
            newline = "\n"
            line = line[:-1]

        # 1. return <expr> -> return None  (whole-line rewrite)
        rm = _RETURN_RE.match(line)
        if rm and rm.group(2).strip() not in ("None", ""):
            indent = rm.group(1)
            add(i, f"{indent}return None{newline}", f"L{i+1}: 'return {rm.group(2).strip()}' -> 'return None'")

        # 2. boolean flips
        for start, end, tok in _occurrences(line, _BOOL_RE):
            flipped = _BOOL_FLIP[tok]
            new_line = line[:start] + flipped + line[end:] + newline
            add(i, new_line, f"L{i+1}: {tok} -> {flipped}")

        # 3. comparison operator swaps
        for start, end, tok in _occurrences(line, _COMPARISON_RE):
            swap = dict(_COMPARISON_SWAPS).get(tok)
            if swap is None:
                continue
            new_line = line[:start] + swap + line[end:] + newline
            add(i, new_line, f"L{i+1}: '{tok}' -> '{swap}'")

        # 4. arithmetic + <-> -
        for start, end, tok in _occurrences(line, _ARITHMETIC_RE):
            swap = _ARITHMETIC_SWAP[tok]
            new_line = line[:start] + swap + line[end:] + newline
            add(i, new_line, f"L{i+1}: arithmetic '{tok}' -> '{swap}'")

    # De-dupe identical mutated sources while preserving order, and drop any
    # no-op mutations (mutated == original) defensively.
    seen: set[str] = set()
    deduped: list[Mutation] = []
    for m in mutations:
        if m.mutated == source:
            continue
        if m.mutated in seen:
            continue
        seen.add(m.mutated)
        deduped.append(m)

    return deduped[:max_mutations]


# ─── Eligibility ─────────────────────────────────────────────────────


def _is_mutation_excluded(path: str) -> bool:
    """True if the path is in a directory we must never mutate (self-eating guard)."""
    norm = path.replace("\\", "/")
    parts = set(Path(norm).parts)
    return bool(parts & MUTATION_EXCLUDED_SEGMENTS)


def _mapped_test_for(impl_path: str, repo_root: Path) -> str | None:
    """First candidate test path (per check_tdd convention) that exists on disk."""
    for cand in check_tdd.candidate_test_paths(impl_path):
        if (repo_root / cand).exists():
            return cand
    return None


def eligible_files(changed_files: list[str], repo_root: Path | None = None) -> list[EligibleFile]:
    """Filter changed files to application impl files that have a mapped test.

    Excludes anything check_tdd excludes, plus scripts/, .claude/, tests/,
    migrations, etc., so the gate never mutates itself or non-application code.
    """
    root = Path(repo_root) if repo_root else REPO_ROOT
    out: list[EligibleFile] = []
    for raw in changed_files:
        path = raw.replace("\\", "/")
        if Path(path).suffix != ".py":
            continue
        if not check_tdd.should_require_test(path):
            continue
        if _is_mutation_excluded(path):
            continue
        test = _mapped_test_for(path, root)
        if test is None:
            continue
        out.append(EligibleFile(impl_file=path, test_file=test))
    return out[:MAX_FILES_PER_RUN]


# ─── Test execution ──────────────────────────────────────────────────


def run_test(test_path: str, repo_root: Path, timeout: int = PER_TEST_TIMEOUT_SECONDS) -> bool:
    """Run the mapped test under pytest. Return True if it PASSED, else False.

    A timeout or any non-zero exit counts as a failure (the test did NOT pass),
    which is the safe interpretation: a mutation that hangs or errors the test
    is still "caught".
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", test_path, "-q", "-p", "no:cacheprovider"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False
    return proc.returncode == 0


def check_file(eligible: EligibleFile, repo_root: Path, timeout: int = PER_TEST_TIMEOUT_SECONDS) -> Violation | None:
    """Mutate one impl file in place, run its test per mutation, restore the original.

    Returns a Violation listing any mutations that the test failed to catch
    (i.e. the test still passed). Returns None if every mutation was caught.
    The original file is ALWAYS restored in a finally block.
    """
    impl_abs = repo_root / eligible.impl_file
    original = impl_abs.read_text(encoding="utf-8")
    mutations = generate_mutations(original)
    if not mutations:
        return None  # nothing to mutate — vacuously fine

    backup = impl_abs.with_suffix(impl_abs.suffix + ".mutbak")
    survived: list[str] = []
    try:
        shutil.copy2(impl_abs, backup)
        for mut in mutations:
            impl_abs.write_text(mut.mutated, encoding="utf-8")
            if run_test(eligible.test_file, repo_root, timeout):
                # Test PASSED under a mutated impl → the mutation survived.
                survived.append(mut.description)
    finally:
        impl_abs.write_text(original, encoding="utf-8")
        if backup.exists():
            backup.unlink()

    if survived:
        return Violation(
            impl_file=eligible.impl_file,
            test_file=eligible.test_file,
            survived=survived,
        )
    return None


def detect_vacuous_tests(
    changed_files: list[str],
    repo_root: Path | None = None,
    timeout: int = PER_TEST_TIMEOUT_SECONDS,
) -> list[Violation]:
    """Top-level orchestration: for each eligible file, run mutation testing."""
    root = Path(repo_root) if repo_root else REPO_ROOT
    violations: list[Violation] = []
    for eligible in eligible_files(changed_files, repo_root=root):
        v = check_file(eligible, root, timeout=timeout)
        if v is not None:
            violations.append(v)
    return violations


# ─── Git integration ─────────────────────────────────────────────────


def changed_files_from_git() -> list[str]:
    """Working tree + staged + untracked Python files (same shape as check_tdd)."""
    try:
        tracked = subprocess.check_output(
            ["git", "diff", "--name-only", "HEAD"], cwd=str(REPO_ROOT), text=True
        )
        untracked = subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(REPO_ROOT),
            text=True,
        )
        out = tracked + "\n" + untracked
    except subprocess.CalledProcessError as e:
        print(f"git failed: {e}", file=sys.stderr)
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


# ─── CLI ─────────────────────────────────────────────────────────────


def _render(violations: list[Violation], summary: bool) -> None:
    if summary:
        if not violations:
            print("Mutation gate: PASS (tests caught all mutations)")
        else:
            print(f"Mutation gate: FAIL ({len(violations)} vacuous test(s))")
        return

    if not violations:
        print("[MUT] Mutation gate: every eligible test caught all mutations.")
        return

    print(f"[MUT] MUTATION GATE FAILED — {len(violations)} vacuous test(s):\n")
    for v in violations:
        print(f"  IMPL: {v.impl_file}")
        print(f"  TEST: {v.test_file}")
        print("  SURVIVED mutations (test still passed — these are NOT tested):")
        for desc in v.survived[:MAX_MUTATIONS_PER_FILE]:
            print(f"      - {desc}")
        print()
    print("A test that passes when the code is broken is not a test.")
    print("Add assertions that pin down the behavior each mutation changes.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mutation gate: prove tests are meaningful")
    parser.add_argument("--summary", action="store_true", help="One-line output.")
    parser.add_argument(
        "--files",
        nargs="*",
        help="Override: specific files to check (for testing).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=PER_TEST_TIMEOUT_SECONDS,
        help="Per-test-run timeout in seconds.",
    )
    args = parser.parse_args()

    files = args.files if args.files else changed_files_from_git()

    eligible = eligible_files(files, repo_root=REPO_ROOT)
    if not eligible:
        if args.summary:
            print("Mutation gate: SKIP (no eligible application files)")
        else:
            print("[MUT] No eligible application files in scope.")
        return 0

    violations = detect_vacuous_tests(files, repo_root=REPO_ROOT, timeout=args.timeout)
    _render(violations, summary=args.summary)
    return 0 if not violations else 1


if __name__ == "__main__":
    sys.exit(main())
