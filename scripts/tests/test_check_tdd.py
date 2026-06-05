"""Tests for scripts/check_tdd.py (gate X10).

Iron Law: NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST.
These tests are written before the gate. They MUST fail on first run
to prove the test harness is hooked up and the assertions are real.

Run with:
    cd <repo-root>
    python -m pytest scripts/tests/test_check_tdd.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

# This import will fail until check_tdd.py exists — that's the RED phase.
import check_tdd  # noqa: E402


# ─── is_test_file ────────────────────────────────────────────────────


class TestIsTestFile:
    def test_pytest_naming(self):
        assert check_tdd.is_test_file("backend/tests/test_user.py")

    def test_pytest_naming_nested(self):
        assert check_tdd.is_test_file("backend/tests/services/test_invoices.py")

    def test_jest_dot_test(self):
        assert check_tdd.is_test_file("frontend/src/Header.test.tsx")

    def test_jest_dot_spec(self):
        assert check_tdd.is_test_file("frontend/src/Header.spec.ts")

    def test_jest_underscores_dir(self):
        assert check_tdd.is_test_file("frontend/src/__tests__/Header.tsx")

    def test_go_test_suffix(self):
        assert check_tdd.is_test_file("internal/auth/token_test.go")

    def test_rust_tests_dir(self):
        assert check_tdd.is_test_file("crate/tests/integration.rs")

    def test_java_test_dir(self):
        assert check_tdd.is_test_file("src/test/java/com/foo/UserTest.java")

    def test_plain_impl_is_not_test(self):
        assert not check_tdd.is_test_file("backend/services/user.py")

    def test_plain_tsx_is_not_test(self):
        assert not check_tdd.is_test_file("frontend/src/Header.tsx")


# ─── should_require_test ─────────────────────────────────────────────


class TestShouldRequireTest:
    def test_service_module_requires_test(self):
        assert check_tdd.should_require_test("backend/services/user.py")

    def test_router_requires_test(self):
        assert check_tdd.should_require_test("backend/routers/invoices.py")

    def test_react_component_requires_test(self):
        assert check_tdd.should_require_test("frontend/src/components/Form.tsx")

    def test_init_does_not_require_test(self):
        assert not check_tdd.should_require_test("backend/__init__.py")

    def test_config_does_not_require_test(self):
        assert not check_tdd.should_require_test("backend/config.py")

    def test_settings_does_not_require_test(self):
        assert not check_tdd.should_require_test("backend/settings.py")

    def test_migration_does_not_require_test(self):
        assert not check_tdd.should_require_test("backend/migrations/0001_initial.py")

    def test_alembic_versions_excluded(self):
        assert not check_tdd.should_require_test("backend/alembic/versions/abc123_init.py")

    def test_markdown_does_not_require_test(self):
        assert not check_tdd.should_require_test("docs/SECURITY.md")

    def test_test_file_does_not_require_meta_test(self):
        """A test file itself never requires another test file."""
        assert not check_tdd.should_require_test("backend/tests/test_user.py")

    def test_main_entry_excluded(self):
        """Entry points are integration-tested, not unit-tested."""
        assert not check_tdd.should_require_test("backend/main.py")

    def test_unknown_extension_skipped(self):
        assert not check_tdd.should_require_test("backend/data/sample.csv")


# ─── candidate_test_paths ────────────────────────────────────────────


class TestCandidateTestPaths:
    def test_python_service_has_pytest_candidate(self):
        candidates = check_tdd.candidate_test_paths("backend/services/user.py")
        assert "backend/tests/test_user.py" in candidates

    def test_python_service_has_sibling_tests_candidate(self):
        candidates = check_tdd.candidate_test_paths("backend/services/user.py")
        assert "backend/services/tests/test_user.py" in candidates

    def test_python_nested_service_has_mirrored_candidate(self):
        candidates = check_tdd.candidate_test_paths("backend/services/billing/charges.py")
        # At least one candidate should preserve the nesting under tests/
        assert any("billing" in c and "test_charges" in c for c in candidates)

    def test_tsx_has_dot_test_candidate(self):
        candidates = check_tdd.candidate_test_paths("frontend/src/Header.tsx")
        assert "frontend/src/Header.test.tsx" in candidates

    def test_tsx_has_dot_spec_candidate(self):
        candidates = check_tdd.candidate_test_paths("frontend/src/Header.tsx")
        assert "frontend/src/Header.spec.tsx" in candidates

    def test_tsx_has_underscores_candidate(self):
        candidates = check_tdd.candidate_test_paths("frontend/src/Header.tsx")
        assert "frontend/src/__tests__/Header.tsx" in candidates

    def test_go_candidate_is_sibling(self):
        candidates = check_tdd.candidate_test_paths("internal/auth/token.go")
        assert "internal/auth/token_test.go" in candidates

    def test_rust_candidate_is_tests_dir(self):
        candidates = check_tdd.candidate_test_paths("src/token.rs")
        assert any("tests/token" in c for c in candidates) or any(
            "tests/" in c and "token" in c for c in candidates
        )

    def test_java_candidate_mirrors_src_main_to_src_test(self):
        candidates = check_tdd.candidate_test_paths("src/main/java/com/foo/User.java")
        assert any("src/test/java/com/foo/UserTest.java" in c for c in candidates)


# ─── detect_violations ───────────────────────────────────────────────


class TestDetectViolations:
    def test_impl_with_existing_test_is_clean(self, tmp_path):
        (tmp_path / "backend" / "services").mkdir(parents=True)
        (tmp_path / "backend" / "tests").mkdir(parents=True)
        impl = tmp_path / "backend" / "services" / "user.py"
        impl.write_text("def f(): pass\n", encoding="utf-8")
        test = tmp_path / "backend" / "tests" / "test_user.py"
        test.write_text("def test_f(): pass\n", encoding="utf-8")

        violations = check_tdd.detect_violations(
            ["backend/services/user.py", "backend/tests/test_user.py"],
            repo_root=tmp_path,
        )
        assert violations == []

    def test_impl_without_test_is_flagged(self, tmp_path):
        (tmp_path / "backend" / "services").mkdir(parents=True)
        impl = tmp_path / "backend" / "services" / "user.py"
        impl.write_text("def f(): pass\n", encoding="utf-8")

        violations = check_tdd.detect_violations(
            ["backend/services/user.py"], repo_root=tmp_path
        )
        assert len(violations) == 1
        v = violations[0]
        assert v.impl_file == "backend/services/user.py"
        assert "no test file" in v.reason.lower()

    def test_pure_test_diff_is_clean(self, tmp_path):
        (tmp_path / "backend" / "tests").mkdir(parents=True)
        (tmp_path / "backend" / "tests" / "test_user.py").write_text(
            "def test_f(): pass\n", encoding="utf-8"
        )
        violations = check_tdd.detect_violations(
            ["backend/tests/test_user.py"], repo_root=tmp_path
        )
        assert violations == []

    def test_excluded_paths_dont_require_tests(self, tmp_path):
        (tmp_path / "backend").mkdir()
        (tmp_path / "backend" / "config.py").write_text("X = 1\n", encoding="utf-8")
        (tmp_path / "backend" / "main.py").write_text("pass\n", encoding="utf-8")
        violations = check_tdd.detect_violations(
            ["backend/config.py", "backend/main.py"], repo_root=tmp_path
        )
        assert violations == []

    def test_multiple_violations_aggregated(self, tmp_path):
        (tmp_path / "backend" / "services").mkdir(parents=True)
        for name in ("user.py", "billing.py"):
            (tmp_path / "backend" / "services" / name).write_text(
                "pass\n", encoding="utf-8"
            )
        violations = check_tdd.detect_violations(
            ["backend/services/user.py", "backend/services/billing.py"],
            repo_root=tmp_path,
        )
        assert len(violations) == 2
        flagged = {v.impl_file for v in violations}
        assert flagged == {"backend/services/user.py", "backend/services/billing.py"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
