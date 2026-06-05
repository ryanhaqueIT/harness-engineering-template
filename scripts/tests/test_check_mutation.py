"""Tests for scripts/check_mutation.py (Component B — Mutation gate).

The mutation gate is the ungameable complement to check_tdd.py: where the
TDD gate proves a test FILE exists, the mutation gate proves the test is
MEANINGFUL. It does this by deterministically mutating the implementation
and requiring the mapped test to FAIL. A test that still passes under a
mutation is vacuous → a violation.

Iron Law: the failing test comes first. These tests are written before
check_mutation.py exists; the import below MUST fail on first run (RED).

Run with:
    cd <repo-root>
    python -m pytest scripts/tests/test_check_mutation.py -q
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

# RED phase: this import fails until check_mutation.py is implemented.
import check_mutation  # noqa: E402


# ─── Fixture: a real impl + a meaningful test, and a vacuous test ────
#
# We build a tiny self-contained "app" under a tmp repo root so the gate
# can run pytest against it hermetically. The impl has comparison /
# boolean / return / arithmetic surface area so every mutation operator
# the gate applies has something to bite on.

IMPL_SOURCE = textwrap.dedent(
    '''\
    """Sample application module under test (mutation target)."""


    def is_adult(age):
        if age >= 18:
            return True
        return False


    def add(a, b):
        return a + b
    '''
)

# A MEANINGFUL test: it pins down the boundary (>= vs >), the boolean
# return values, and the arithmetic. Every mutation the gate makes should
# break at least one of these assertions, so the gate must report NO
# violation for this file.
MEANINGFUL_TEST = textwrap.dedent(
    '''\
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    import sample  # noqa: E402


    def test_is_adult_boundary():
        assert sample.is_adult(18) is True
        assert sample.is_adult(17) is False


    def test_is_adult_truthy_falsy():
        assert sample.is_adult(99) is True
        assert sample.is_adult(0) is False


    def test_add():
        assert sample.add(2, 3) == 5
        assert sample.add(10, 1) == 11
    '''
)

# A VACUOUS test: it imports the impl and "exercises" it but asserts
# nothing meaningful — it never checks a result, so it passes no matter
# how the impl is mutated. The gate MUST flag this file.
VACUOUS_TEST = textwrap.dedent(
    '''\
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    import sample  # noqa: E402


    def test_smoke():
        sample.is_adult(18)
        sample.add(2, 3)
        assert True
    '''
)


def _build_repo(tmp_path: Path, test_source: str) -> Path:
    """Create a tmp repo: backend/sample.py + backend/tests/test_sample.py."""
    backend = tmp_path / "backend"
    tests = backend / "tests"
    tests.mkdir(parents=True)
    (backend / "__init__.py").write_text("", encoding="utf-8")
    (backend / "sample.py").write_text(IMPL_SOURCE, encoding="utf-8")
    (tests / "test_sample.py").write_text(test_source, encoding="utf-8")
    return tmp_path


# ─── Mutation generation (pure, deterministic) ───────────────────────


class TestGenerateMutations:
    def test_swaps_comparison_operator(self):
        muts = check_mutation.generate_mutations("if age >= 18:\n")
        bodies = [m.mutated for m in muts]
        assert any(">=" not in b for b in bodies)

    def test_flips_boolean_literal(self):
        muts = check_mutation.generate_mutations("return True\n")
        assert any("False" in m.mutated for m in muts)

    def test_return_value_to_none(self):
        muts = check_mutation.generate_mutations("return a + b\n")
        assert any(m.mutated.strip() == "return None" for m in muts)

    def test_swaps_arithmetic_operator(self):
        muts = check_mutation.generate_mutations("return a + b\n")
        assert any("a - b" in m.mutated for m in muts)

    def test_each_mutation_changes_the_source(self):
        src = "if x >= 1:\n    return True\n"
        for m in check_mutation.generate_mutations(src):
            assert m.mutated != src

    def test_no_mutatable_surface_returns_empty(self):
        muts = check_mutation.generate_mutations("x = 'hello world'\n")
        assert muts == []

    def test_mutations_capped_per_file(self):
        # A line with lots of surface area should still be bounded.
        src = "\n".join(f"if a{i} >= b{i}:" for i in range(100)) + "\n"
        muts = check_mutation.generate_mutations(src, max_mutations=5)
        assert len(muts) <= 5


# ─── eligible_files: exclusions to avoid self-eating ─────────────────


class TestEligibleFiles:
    def test_backend_impl_is_eligible(self, tmp_path):
        repo = _build_repo(tmp_path, MEANINGFUL_TEST)
        eligible = check_mutation.eligible_files(
            ["backend/sample.py"], repo_root=repo
        )
        assert [e.impl_file for e in eligible] == ["backend/sample.py"]

    def test_scripts_dir_is_excluded(self, tmp_path):
        eligible = check_mutation.eligible_files(
            ["scripts/check_mutation.py"], repo_root=tmp_path
        )
        assert eligible == []

    def test_dot_claude_is_excluded(self, tmp_path):
        eligible = check_mutation.eligible_files(
            [".claude/hooks/foo.py"], repo_root=tmp_path
        )
        assert eligible == []

    def test_test_files_are_excluded(self, tmp_path):
        repo = _build_repo(tmp_path, MEANINGFUL_TEST)
        eligible = check_mutation.eligible_files(
            ["backend/tests/test_sample.py"], repo_root=repo
        )
        assert eligible == []

    def test_migrations_excluded(self, tmp_path):
        eligible = check_mutation.eligible_files(
            ["backend/migrations/0001_init.py"], repo_root=tmp_path
        )
        assert eligible == []

    def test_impl_without_mapped_test_is_not_eligible(self, tmp_path):
        # backend/orphan.py exists but no test_orphan.py anywhere.
        (tmp_path / "backend").mkdir()
        (tmp_path / "backend" / "orphan.py").write_text(
            "def f():\n    return 1\n", encoding="utf-8"
        )
        eligible = check_mutation.eligible_files(
            ["backend/orphan.py"], repo_root=tmp_path
        )
        assert eligible == []


# ─── End-to-end: the gate's core contract ────────────────────────────


class TestGateContract:
    def test_meaningful_test_catches_mutations_gate_passes(self, tmp_path):
        repo = _build_repo(tmp_path, MEANINGFUL_TEST)
        violations = check_mutation.detect_vacuous_tests(
            ["backend/sample.py"], repo_root=repo
        )
        assert violations == [], (
            "A meaningful test should catch every mutation → no violation"
        )

    def test_vacuous_test_is_flagged(self, tmp_path):
        repo = _build_repo(tmp_path, VACUOUS_TEST)
        violations = check_mutation.detect_vacuous_tests(
            ["backend/sample.py"], repo_root=repo
        )
        assert len(violations) == 1
        v = violations[0]
        assert v.impl_file == "backend/sample.py"
        # The violation should name the surviving mutation(s).
        assert v.survived, "Expected at least one surviving mutation recorded"

    def test_no_eligible_files_means_no_violations(self, tmp_path):
        violations = check_mutation.detect_vacuous_tests(
            ["scripts/check_mutation.py", "README.md"], repo_root=tmp_path
        )
        assert violations == []

    def test_original_file_is_restored_after_run(self, tmp_path):
        repo = _build_repo(tmp_path, VACUOUS_TEST)
        before = (repo / "backend" / "sample.py").read_text(encoding="utf-8")
        check_mutation.detect_vacuous_tests(["backend/sample.py"], repo_root=repo)
        after = (repo / "backend" / "sample.py").read_text(encoding="utf-8")
        assert after == before, "Impl file must be restored byte-for-byte"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
