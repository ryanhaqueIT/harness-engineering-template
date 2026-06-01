"""Tests for scripts/check_tiers.py (Component D — tier-audit gate).

Iron Law: NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST.
These tests are written before the gate. They MUST fail on first run
(ModuleNotFoundError) to prove the harness is hooked up.

The gate makes the guaranteed/proxied/hoped-for distinction a standing
check: a "guaranteed" entry whose declared wiring is absent (e.g. an
empty "Stop": [] array in settings.json) must fail --strict.

These tests use FIXTURES (temp registry + temp settings.json + temp
files), never the live repo, so they are deterministic regardless of
whether the real Stop wiring has landed yet.

Run with:
    cd <repo-root>
    python -m pytest scripts/tests/test_check_tiers.py -q
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

# This import fails until check_tiers.py exists — that's the RED phase.
import check_tiers  # noqa: E402


# ─── Fixture builders ────────────────────────────────────────────────


def _write_registry(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def _write_settings(path: Path, stop_hooks: list[dict] | None = None) -> None:
    data = {"hooks": {"Stop": stop_hooks if stop_hooks is not None else []}}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _touch(repo_root: Path, rel: str) -> None:
    f = repo_root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("# stub\n", encoding="utf-8")


def _stop_hook_referencing(rel_file: str) -> list[dict]:
    """A non-empty Stop hook array that references `rel_file`."""
    return [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": f'python "$CLAUDE_PROJECT_DIR/{rel_file}"',
                }
            ]
        }
    ]


# ─── audit(): the core, exercised directly ──────────────────────────


class TestAuditFileExistence:
    def test_present_file_not_missing(self, tmp_path):
        _touch(tmp_path, "scripts/validate.sh")
        reg = tmp_path / "registry.json"
        settings = tmp_path / "settings.json"
        _write_settings(settings)
        _write_registry(
            reg,
            [
                {
                    "name": "validate",
                    "file": "scripts/validate.sh",
                    "tier": "guaranteed",
                    "rederives": "all gates",
                    "wired_via": "validate.sh",
                }
            ],
        )
        results = check_tiers.audit(reg, repo_root=tmp_path, settings_path=settings)
        entry = results[0]
        assert entry.file_exists is True
        assert entry.missing_file is False

    def test_absent_file_is_missing(self, tmp_path):
        reg = tmp_path / "registry.json"
        settings = tmp_path / "settings.json"
        _write_settings(settings)
        _write_registry(
            reg,
            [
                {
                    "name": "ghost",
                    "file": "scripts/does_not_exist.py",
                    "tier": "guaranteed",
                    "rederives": "",
                    "wired_via": "validate.sh",
                }
            ],
        )
        results = check_tiers.audit(reg, repo_root=tmp_path, settings_path=settings)
        assert results[0].file_exists is False
        assert results[0].missing_file is True


class TestAuditWiring:
    def test_guaranteed_stop_entry_with_wiring_is_consistent(self, tmp_path):
        _touch(tmp_path, "scripts/stop_verification.py")
        reg = tmp_path / "registry.json"
        settings = tmp_path / "settings.json"
        _write_settings(settings, _stop_hook_referencing("scripts/stop_verification.py"))
        _write_registry(
            reg,
            [
                {
                    "name": "stop_verification",
                    "file": "scripts/stop_verification.py",
                    "tier": "guaranteed",
                    "rederives": "feature verification state",
                    "wired_via": ".claude/settings.json Stop",
                }
            ],
        )
        results = check_tiers.audit(reg, repo_root=tmp_path, settings_path=settings)
        entry = results[0]
        assert entry.wiring_required is True
        assert entry.wiring_ok is True
        assert entry.missing_wiring is False

    def test_guaranteed_stop_entry_without_wiring_is_flagged(self, tmp_path):
        # File exists, but settings.json has an EMPTY Stop array — the exact
        # "Stop": [] class of bug this gate is designed to catch.
        _touch(tmp_path, "scripts/stop_verification.py")
        reg = tmp_path / "registry.json"
        settings = tmp_path / "settings.json"
        _write_settings(settings, [])  # empty Stop
        _write_registry(
            reg,
            [
                {
                    "name": "stop_verification",
                    "file": "scripts/stop_verification.py",
                    "tier": "guaranteed",
                    "rederives": "feature verification state",
                    "wired_via": ".claude/settings.json Stop",
                }
            ],
        )
        results = check_tiers.audit(reg, repo_root=tmp_path, settings_path=settings)
        entry = results[0]
        assert entry.wiring_required is True
        assert entry.wiring_ok is False
        assert entry.missing_wiring is True

    def test_non_settings_wiring_does_not_require_settings_check(self, tmp_path):
        # A guaranteed entry wired via validate.sh should not be checked
        # against settings.json at all.
        _touch(tmp_path, "scripts/check_mutation.py")
        reg = tmp_path / "registry.json"
        settings = tmp_path / "settings.json"
        _write_settings(settings, [])
        _write_registry(
            reg,
            [
                {
                    "name": "check_mutation",
                    "file": "scripts/check_mutation.py",
                    "tier": "guaranteed",
                    "rederives": "test meaningfulness",
                    "wired_via": "validate.sh",
                }
            ],
        )
        results = check_tiers.audit(reg, repo_root=tmp_path, settings_path=settings)
        entry = results[0]
        assert entry.wiring_required is False
        assert entry.missing_wiring is False

    def test_proxied_entry_never_requires_wiring(self, tmp_path):
        _touch(tmp_path, "scripts/check_tdd.py")
        reg = tmp_path / "registry.json"
        settings = tmp_path / "settings.json"
        _write_settings(settings, [])
        _write_registry(
            reg,
            [
                {
                    "name": "check_tdd",
                    "file": "scripts/check_tdd.py",
                    "tier": "proxied",
                    "rederives": "",
                    "wired_via": "validate.sh",
                }
            ],
        )
        results = check_tiers.audit(reg, repo_root=tmp_path, settings_path=settings)
        assert results[0].wiring_required is False


# ─── CLI exit codes (the load-bearing contract) ─────────────────────


def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "check_tiers.py"), *args],
        capture_output=True,
        text=True,
    )


class TestCliStrict:
    def test_strict_exits_nonzero_when_guaranteed_entry_unwired(self, tmp_path):
        # File present, but Stop array empty → strict must FAIL.
        _touch(tmp_path, "scripts/stop_verification.py")
        reg = tmp_path / "registry.json"
        settings = tmp_path / "settings.json"
        _write_settings(settings, [])  # the bug
        _write_registry(
            reg,
            [
                {
                    "name": "stop_verification",
                    "file": "scripts/stop_verification.py",
                    "tier": "guaranteed",
                    "rederives": "feature verification state",
                    "wired_via": ".claude/settings.json Stop",
                }
            ],
        )
        result = _run_cli(
            [
                "--strict",
                "--registry",
                str(reg),
                "--repo-root",
                str(tmp_path),
                "--settings",
                str(settings),
            ]
        )
        assert result.returncode != 0, result.stdout + result.stderr

    def test_strict_exits_nonzero_when_guaranteed_file_missing(self, tmp_path):
        reg = tmp_path / "registry.json"
        settings = tmp_path / "settings.json"
        _write_settings(settings, _stop_hook_referencing("scripts/stop_verification.py"))
        _write_registry(
            reg,
            [
                {
                    "name": "ghost",
                    "file": "scripts/does_not_exist.py",
                    "tier": "guaranteed",
                    "rederives": "",
                    "wired_via": "validate.sh",
                }
            ],
        )
        result = _run_cli(
            [
                "--strict",
                "--registry",
                str(reg),
                "--repo-root",
                str(tmp_path),
                "--settings",
                str(settings),
            ]
        )
        assert result.returncode != 0, result.stdout + result.stderr

    def test_strict_exits_zero_when_all_consistent(self, tmp_path):
        # Everything present + wired correctly → strict PASSES.
        _touch(tmp_path, "scripts/validate.sh")
        _touch(tmp_path, "scripts/stop_verification.py")
        _touch(tmp_path, "scripts/check_tdd.py")
        reg = tmp_path / "registry.json"
        settings = tmp_path / "settings.json"
        _write_settings(settings, _stop_hook_referencing("scripts/stop_verification.py"))
        _write_registry(
            reg,
            [
                {
                    "name": "validate",
                    "file": "scripts/validate.sh",
                    "tier": "guaranteed",
                    "rederives": "all gates",
                    "wired_via": "validate.sh",
                },
                {
                    "name": "stop_verification",
                    "file": "scripts/stop_verification.py",
                    "tier": "guaranteed",
                    "rederives": "feature verification state",
                    "wired_via": ".claude/settings.json Stop",
                },
                {
                    "name": "check_tdd",
                    "file": "scripts/check_tdd.py",
                    "tier": "proxied",
                    "rederives": "",
                    "wired_via": "validate.sh",
                },
            ],
        )
        result = _run_cli(
            [
                "--strict",
                "--registry",
                str(reg),
                "--repo-root",
                str(tmp_path),
                "--settings",
                str(settings),
            ]
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_default_nonstrict_exits_zero_even_with_problems(self, tmp_path):
        # Same broken fixture as the failing-strict case, but WITHOUT --strict
        # the gate just reports and exits 0.
        _touch(tmp_path, "scripts/stop_verification.py")
        reg = tmp_path / "registry.json"
        settings = tmp_path / "settings.json"
        _write_settings(settings, [])
        _write_registry(
            reg,
            [
                {
                    "name": "stop_verification",
                    "file": "scripts/stop_verification.py",
                    "tier": "guaranteed",
                    "rederives": "feature verification state",
                    "wired_via": ".claude/settings.json Stop",
                }
            ],
        )
        result = _run_cli(
            [
                "--registry",
                str(reg),
                "--repo-root",
                str(tmp_path),
                "--settings",
                str(settings),
            ]
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_report_groups_by_tier_with_counts(self, tmp_path):
        _touch(tmp_path, "scripts/validate.sh")
        _touch(tmp_path, "scripts/check_tdd.py")
        reg = tmp_path / "registry.json"
        settings = tmp_path / "settings.json"
        _write_settings(settings, [])
        _write_registry(
            reg,
            [
                {
                    "name": "validate",
                    "file": "scripts/validate.sh",
                    "tier": "guaranteed",
                    "rederives": "all gates",
                    "wired_via": "validate.sh",
                },
                {
                    "name": "check_tdd",
                    "file": "scripts/check_tdd.py",
                    "tier": "proxied",
                    "rederives": "",
                    "wired_via": "validate.sh",
                },
                {
                    "name": "golden_principles",
                    "file": "",
                    "tier": "hoped-for",
                    "rederives": "",
                    "wired_via": "",
                },
            ],
        )
        result = _run_cli(
            [
                "--registry",
                str(reg),
                "--repo-root",
                str(tmp_path),
                "--settings",
                str(settings),
            ]
        )
        out = result.stdout.lower()
        assert "guaranteed" in out
        assert "proxied" in out
        assert "hoped-for" in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
