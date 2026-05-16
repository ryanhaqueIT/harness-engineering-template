"""Tests for scripts/harness_dashboard.py — the Airflow-style DAG dashboard.

Focused tests on the public metadata surface I modified (gate registration).
Full dashboard behaviour is exercised by manual smoke tests in
docs/dashboard-*.png and is not unit-testable here without a browser.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import harness_dashboard as hd  # noqa: E402


class TestGateMetadata:
    def test_new_x8_registered(self):
        assert "X8" in hd.GATES
        assert "Spec Quality" in hd.GATES["X8"]["name"]

    def test_new_x9_registered(self):
        assert "X9" in hd.GATES
        assert "Loop Guard" in hd.GATES["X9"]["name"]

    def test_new_x10_registered(self):
        assert "X10" in hd.GATES
        assert "TDD" in hd.GATES["X10"]["name"]

    def test_all_new_gates_in_layer_7(self):
        """X8/X9/X10 are PRD-enforcement-tier gates."""
        for gate in ("X8", "X9", "X10"):
            assert hd.GATES[gate]["layer"] == 7

    def test_pre_existing_gates_intact(self):
        """My additions must not have broken existing gates."""
        for gate in ("B1", "B2", "B3", "B7", "B8", "X5", "X6", "X7", "R1"):
            assert gate in hd.GATES, f"existing gate {gate} missing"

    def test_no_duplicate_gate_ids(self):
        # If the metadata dict were ever an array, duplicates could sneak in.
        # As a dict it can't — but lock the invariant in regardless.
        ids = list(hd.GATES.keys())
        assert len(ids) == len(set(ids))


class TestLayerNames:
    def test_layer_7_is_prd_enforcement(self):
        assert hd.LAYER_NAMES[7] == "PRD Enforcement"

    def test_all_referenced_layers_named(self):
        used = {info["layer"] for info in hd.GATES.values()}
        for layer in used:
            assert layer in hd.LAYER_NAMES, f"layer {layer} used but not named"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
