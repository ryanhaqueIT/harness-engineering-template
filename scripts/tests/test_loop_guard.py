"""Tests for scripts/loop_guard.py — failure fingerprinting + loop detection.

The fingerprint is the heart of the gate: it must be stable across cosmetic
differences (line numbers, timestamps) and sensitive to semantic ones
(different missing module = different fingerprint).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import loop_guard  # noqa: E402


def _gate(gid: str, layer: int = 2, details: list[str] | None = None) -> loop_guard.FailingGate:
    return loop_guard.FailingGate(
        gate_id=gid,
        name=gid,
        layer=layer,
        details=details or [],
    )


class TestNormalize:
    def test_strips_iso_timestamp(self):
        out = loop_guard._normalize_error_text("error at 2026-05-16T22:01:30.123Z")
        assert "2026" not in out
        assert "<ts>" in out

    def test_strips_line_numbers(self):
        out = loop_guard._normalize_error_text("File foo.py:42 has issue")
        assert "42" not in out
        assert "<line>" in out

    def test_strips_hex_addresses(self):
        out = loop_guard._normalize_error_text("at 0xdeadbeef")
        assert "deadbeef" not in out

    def test_lowercases_and_collapses_whitespace(self):
        out = loop_guard._normalize_error_text("ERROR  on  LINE")
        assert out == "error on line"


class TestFingerprintStability:
    def test_same_failure_same_fingerprint(self):
        g1 = _gate("B5", details=["E001 missing import 'requests'"])
        g2 = _gate("B5", details=["E001 missing import 'requests'"])
        assert loop_guard.fingerprint_failure([g1]) == loop_guard.fingerprint_failure([g2])

    def test_different_missing_module_different_fingerprint(self):
        g1 = _gate("B5", details=["No module named 'requests'"])
        g2 = _gate("B5", details=["No module named 'numpy'"])
        assert loop_guard.fingerprint_failure([g1]) != loop_guard.fingerprint_failure([g2])

    def test_line_number_change_does_not_change_fingerprint(self):
        g1 = _gate("B7", details=["error at foo.py:42 missing"])
        g2 = _gate("B7", details=["error at foo.py:55 missing"])
        assert loop_guard.fingerprint_failure([g1]) == loop_guard.fingerprint_failure([g2])

    def test_no_failures_returns_no_fail_sentinel(self):
        assert loop_guard.fingerprint_failure([]) == "no-fail"

    def test_fingerprint_fits_in_log_line(self):
        gates = [_gate(f"X{i}", details=["x"]) for i in range(20)]
        fp = loop_guard.fingerprint_failure(gates)
        assert len(fp) <= 120

    def test_fingerprint_sorts_by_layer(self):
        """Lower-layer failures (root cause) come first."""
        g_low = _gate("B1", layer=1, details=["lint fail"])
        g_high = _gate("X5", layer=7, details=["feature fail"])
        # Order of input shouldn't matter; output should put B1 (layer 1) first
        fp_a = loop_guard.fingerprint_failure([g_low, g_high])
        fp_b = loop_guard.fingerprint_failure([g_high, g_low])
        assert fp_a == fp_b
        assert fp_a.split("|")[0].startswith("B1")


class TestSignatureExtraction:
    def test_extracts_missing_module(self):
        g = _gate("B5", details=["No module named 'requests'"])
        sig = loop_guard._signature_for_gate(g)
        assert "requests" in sig

    def test_extracts_http_mismatch(self):
        g = _gate("X6", details=["HTTP 500 != 200"])
        sig = loop_guard._signature_for_gate(g)
        assert "500" in sig and "200" in sig

    def test_extracts_wiring_keyword(self):
        g = _gate("B8", details=["  ORPHAN: backend/foo.py — imported by nothing"])
        sig = loop_guard._signature_for_gate(g)
        assert "ORPHAN" in sig

    def test_falls_back_to_normalized_prose(self):
        g = _gate("X1", details=["something quite generic happened here"])
        sig = loop_guard._signature_for_gate(g)
        assert sig  # non-empty
        assert len(sig) <= 40


class TestLoopDetection:
    def _summary(self, run_id: int, fp: str, fail: bool = True) -> loop_guard.RunSummary:
        gates = [_gate("B8")] if fail else []
        return loop_guard.RunSummary(
            run_id=run_id, timestamp="t", failing_gates=gates, fingerprint=fp
        )

    def test_three_same_fingerprints_is_a_loop(self):
        s = [self._summary(i, "B8=orphan") for i in range(3)]
        looped, fp = loop_guard.detect_loop(s, window=3)
        assert looped is True
        assert fp == "B8=orphan"

    def test_different_fingerprints_no_loop(self):
        s = [
            self._summary(1, "B8=orphan"),
            self._summary(2, "B5=missing-import"),
            self._summary(3, "B8=cycle"),
        ]
        looped, _ = loop_guard.detect_loop(s, window=3)
        assert looped is False

    def test_recent_pass_breaks_loop(self):
        s = [
            self._summary(1, "B8=orphan"),
            self._summary(2, "no-fail", fail=False),
            self._summary(3, "B8=orphan"),
        ]
        looped, _ = loop_guard.detect_loop(s, window=3)
        assert looped is False

    def test_insufficient_history_no_loop(self):
        s = [self._summary(1, "B8")]
        looped, _ = loop_guard.detect_loop(s, window=3)
        assert looped is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
