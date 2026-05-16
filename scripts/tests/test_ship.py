"""Tests for scripts/ship.py — the autonomous build orchestrator.

These tests cover the state machine invariants and persistence behaviour
that the harness relies on: transitions are strictly checked, state is
deterministic, and the full happy-path walk reaches `done`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import ship  # noqa: E402


class TestStateMachineInvariants:
    def test_all_states_have_next_action(self):
        """Every declared state must have user-facing guidance."""
        for state in ship.STATES:
            assert state in ship.NEXT_ACTION, f"state '{state}' missing NEXT_ACTION entry"

    def test_all_states_in_transitions(self):
        """Every state must declare its outgoing transitions (even if empty)."""
        for state in ship.STATES:
            assert state in ship.TRANSITIONS, f"state '{state}' missing in TRANSITIONS"

    def test_transition_targets_are_real_states(self):
        """A transition must point at a state that actually exists."""
        valid = set(ship.STATES)
        for src, targets in ship.TRANSITIONS.items():
            for t in targets:
                assert t in valid, f"transition {src} → {t} points at non-existent state"

    def test_done_is_terminal(self):
        assert ship.TRANSITIONS["done"] == set()

    def test_adversarial_review_is_reachable(self):
        """The new adversarial_review state must be reachable from post_review."""
        assert "adversarial_review" in ship.TRANSITIONS["post_review"]

    def test_adversarial_review_can_commit(self):
        assert "committing" in ship.TRANSITIONS["adversarial_review"]

    def test_adversarial_review_can_route_back_to_fixing(self):
        """If codex finds a blocker, we must be able to go back to fixing."""
        assert "fixing" in ship.TRANSITIONS["adversarial_review"]


class TestPersistence:
    def test_save_and_load_round_trip(self, tmp_path, monkeypatch):
        state_file = tmp_path / "ship_state.json"
        monkeypatch.setattr(ship, "STATE_FILE", state_file)

        state = ship.ShipState(status="building", spec_path="docs/foo.md")
        ship.save_state(state)

        loaded = ship.load_state()
        assert loaded.status == "building"
        assert loaded.spec_path == "docs/foo.md"

    def test_load_with_no_state_file_returns_init(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ship, "STATE_FILE", tmp_path / "does-not-exist.json")
        state = ship.load_state()
        assert state.status == "init"

    def test_state_file_is_valid_json_after_save(self, tmp_path, monkeypatch):
        state_file = tmp_path / "ship_state.json"
        monkeypatch.setattr(ship, "STATE_FILE", state_file)
        ship.save_state(ship.ShipState(status="intake"))
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["status"] == "intake"


class TestTransitionValidation:
    def test_invalid_transition_is_rejected(self, capsys, tmp_path, monkeypatch):
        monkeypatch.setattr(ship, "STATE_FILE", tmp_path / "state.json")
        state = ship.ShipState(status="init")
        ok = ship._transition(state, "committing")  # not allowed from init
        assert ok is False

    def test_valid_transition_changes_status(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ship, "STATE_FILE", tmp_path / "state.json")
        state = ship.ShipState(status="init")
        ok = ship._transition(state, "intake")
        assert ok is True
        assert state.status == "intake"


class TestHappyPathReachable:
    """The happy path from init to done must be walkable in TRANSITIONS."""

    def test_init_to_done_path_exists(self):
        # BFS to confirm 'done' is reachable from 'init'
        seen = {"init"}
        frontier = ["init"]
        while frontier:
            cur = frontier.pop()
            for nxt in ship.TRANSITIONS.get(cur, set()):
                if nxt not in seen:
                    seen.add(nxt)
                    frontier.append(nxt)
        assert "done" in seen


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
