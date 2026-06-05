"""Tests for scripts/stop_verification.py — re-derivation Stop gate.

The gate must not TRUST the agent's `passes:true` flag. For every feature
claiming to pass, it RE-DERIVES truth by running the feature's `verify`
command and checking exit code 0 AND the `expect` substring in the output.

A `passes:true` feature with no verify block, or whose re-run disagrees,
is an unverified claim and must block the stop.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import stop_verification  # noqa: E402


# ─── verify_feature ──────────────────────────────────────────────────


class TestVerifyFeature:
    def test_passes_false_is_not_verified(self):
        # A feature that doesn't even claim to pass is never "verified".
        feat = {"id": "f1", "passes": False}
        assert stop_verification.verify_feature(feat) is False

    def test_missing_verify_block_is_not_verified(self):
        # passes:true but no evidence — an unverified claim.
        feat = {"id": "f1", "passes": True}
        assert stop_verification.verify_feature(feat) is False

    def test_verify_missing_cmd_is_not_verified(self):
        feat = {"id": "f1", "passes": True, "verify": {"expect": "OK"}}
        assert stop_verification.verify_feature(feat) is False

    def test_verify_missing_expect_is_not_verified(self):
        feat = {"id": "f1", "passes": True, "verify": {"cmd": "echo OK"}}
        assert stop_verification.verify_feature(feat) is False

    def test_honest_pass_exit0_and_expect_matches(self, monkeypatch):
        feat = {
            "id": "f1",
            "passes": True,
            "verify": {"cmd": "echo hello-world", "expect": "hello"},
        }

        def fake_run(cmd, **kwargs):
            assert cmd == "echo hello-world"
            return (0, "hello-world\n")

        monkeypatch.setattr(stop_verification, "_run_verify_cmd", fake_run)
        assert stop_verification.verify_feature(feat) is True

    def test_lying_pass_expect_mismatch(self, monkeypatch):
        feat = {
            "id": "f1",
            "passes": True,
            "verify": {"cmd": "echo goodbye", "expect": "hello"},
        }
        monkeypatch.setattr(
            stop_verification, "_run_verify_cmd", lambda cmd, **k: (0, "goodbye\n")
        )
        assert stop_verification.verify_feature(feat) is False

    def test_nonzero_exit_is_not_verified(self, monkeypatch):
        feat = {
            "id": "f1",
            "passes": True,
            "verify": {"cmd": "false", "expect": "hello"},
        }
        # expect substring is present, but exit code is non-zero → not verified.
        monkeypatch.setattr(
            stop_verification, "_run_verify_cmd", lambda cmd, **k: (1, "hello\n")
        )
        assert stop_verification.verify_feature(feat) is False


# ─── evaluate_features (pure decision) ───────────────────────────────


def _verifier(result_map: dict):
    """Build a verify_feature stand-in keyed by feature id."""

    def _v(feat):
        return result_map.get(feat.get("id"), False)

    return _v


class TestEvaluateFeatures:
    def test_researching_state_allows(self, monkeypatch):
        feats = [{"id": "f1", "passes": False}]
        decision = stop_verification.evaluate_features(feats, "researching")
        assert decision.allow is True
        assert decision.block_payload is None

    def test_planning_state_allows(self):
        feats = [{"id": "f1", "passes": False}]
        decision = stop_verification.evaluate_features(feats, "planning")
        assert decision.allow is True

    def test_no_features_allows(self):
        decision = stop_verification.evaluate_features([], "verifying")
        assert decision.allow is True

    def test_honest_pass_in_verifying_allows(self, monkeypatch):
        feats = [{"id": "f1", "passes": True, "verify": {"cmd": "x", "expect": "y"}}]
        monkeypatch.setattr(
            stop_verification, "verify_feature", _verifier({"f1": True})
        )
        decision = stop_verification.evaluate_features(feats, "verifying")
        assert decision.allow is True
        assert decision.block_payload is None

    def test_lying_pass_in_verifying_blocks(self, monkeypatch):
        # passes:true but re-run disagrees → unverified claim → block.
        feats = [{"id": "f1", "passes": True, "verify": {"cmd": "x", "expect": "y"}}]
        monkeypatch.setattr(
            stop_verification, "verify_feature", _verifier({"f1": False})
        )
        decision = stop_verification.evaluate_features(feats, "verifying")
        assert decision.allow is False
        assert decision.block_payload["decision"] == "block"
        assert "f1" in decision.block_payload["reason"]

    def test_missing_evidence_in_verifying_blocks(self, monkeypatch):
        # passes:true, no verify block — verify_feature returns False → block.
        feats = [{"id": "f1", "passes": True}]
        monkeypatch.setattr(
            stop_verification, "verify_feature", _verifier({"f1": False})
        )
        decision = stop_verification.evaluate_features(feats, "verifying")
        assert decision.allow is False
        assert decision.block_payload["decision"] == "block"

    def test_passes_false_in_verifying_blocks(self, monkeypatch):
        feats = [{"id": "f1", "passes": False}]
        monkeypatch.setattr(
            stop_verification, "verify_feature", _verifier({"f1": False})
        )
        decision = stop_verification.evaluate_features(feats, "verifying")
        assert decision.allow is False
        assert decision.block_payload["decision"] == "block"

    def test_building_state_warns_but_allows(self, monkeypatch):
        feats = [{"id": "f1", "passes": True, "verify": {"cmd": "x", "expect": "y"}}]
        monkeypatch.setattr(
            stop_verification, "verify_feature", _verifier({"f1": False})
        )
        decision = stop_verification.evaluate_features(feats, "building")
        assert decision.allow is True
        assert decision.block_payload is None
        assert decision.warning is not None

    def test_shipping_state_enforces(self, monkeypatch):
        feats = [{"id": "f1", "passes": True, "verify": {"cmd": "x", "expect": "y"}}]
        monkeypatch.setattr(
            stop_verification, "verify_feature", _verifier({"f1": False})
        )
        decision = stop_verification.evaluate_features(feats, "shipping")
        assert decision.allow is False
        assert decision.block_payload["decision"] == "block"

    def test_none_state_enforces(self, monkeypatch):
        feats = [{"id": "f1", "passes": True}]
        monkeypatch.setattr(
            stop_verification, "verify_feature", _verifier({"f1": False})
        )
        decision = stop_verification.evaluate_features(feats, "none")
        assert decision.allow is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
