"""Tests for scripts/check_spec_quality.py — the pre-build spec quality gate.

The gate must catch vague language, missing Demo statements, and references
to invisible external context, without flagging code blocks as prose.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import check_spec_quality as csq  # noqa: E402


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "plan.md"
    p.write_text(body, encoding="utf-8")
    return p


class TestPurposeSection:
    def test_purpose_present_passes(self, tmp_path):
        p = _write(tmp_path, "# Purpose\n\nUsers can do X.\n")
        report = csq.review_spec(p)
        purpose_check = next(c for c in report.checks if "Purpose" in c.name)
        assert purpose_check.passed

    def test_no_purpose_fails(self, tmp_path):
        p = _write(tmp_path, "# Some Random Heading\n\nbody\n")
        report = csq.review_spec(p)
        purpose_check = next(c for c in report.checks if "Purpose" in c.name)
        assert not purpose_check.passed


class TestMilestoneDemos:
    def test_milestone_with_demo_passes(self, tmp_path):
        body = (
            "# Purpose\nX\n"
            "## Milestone 1\n\n**Demo:** When I do X, I see Y.\n"
            "## Validation\n\nresponse should equal 200, verify response\n"
        )
        p = _write(tmp_path, body)
        report = csq.review_spec(p)
        ck = next(c for c in report.checks if "Milestones" in c.name)
        assert ck.passed

    def test_milestone_without_demo_fails(self, tmp_path):
        body = (
            "# Purpose\nX\n"
            "## Milestone 1\n\nDo some stuff.\n"
        )
        p = _write(tmp_path, body)
        report = csq.review_spec(p)
        ck = next(c for c in report.checks if "Milestones" in c.name)
        assert not ck.passed


class TestVagueLanguage:
    def test_clean_prose_passes(self, tmp_path):
        body = "# Purpose\nThe service exposes GET /health returning 200.\n"
        p = _write(tmp_path, body)
        report = csq.review_spec(p)
        ck = next(c for c in report.checks if "vague" in c.name.lower())
        assert ck.passed

    def test_vague_word_fails(self, tmp_path):
        body = (
            "# Purpose\nThe system should be robust and user-friendly with "
            "appropriate handling of various inputs.\n"
        )
        p = _write(tmp_path, body)
        report = csq.review_spec(p)
        ck = next(c for c in report.checks if "vague" in c.name.lower())
        assert not ck.passed

    def test_vague_words_inside_code_are_ignored(self, tmp_path):
        body = (
            "# Purpose\n"
            "Exact API:\n```\nGET /api/v1/robust  # robust is the endpoint name\n```\n"
        )
        p = _write(tmp_path, body)
        report = csq.review_spec(p)
        ck = next(c for c in report.checks if "vague" in c.name.lower())
        # 'robust' appears only inside a code block — should pass
        assert ck.passed


class TestSelfContained:
    def test_external_reference_fails(self, tmp_path):
        body = "# Purpose\nUsers do X as discussed.\n"
        p = _write(tmp_path, body)
        report = csq.review_spec(p)
        ck = next(c for c in report.checks if "Self-contained" in c.name)
        assert not ck.passed

    def test_clean_spec_self_contained_passes(self, tmp_path):
        body = "# Purpose\nUsers do X. The API is GET /api/foo returning 200.\n"
        p = _write(tmp_path, body)
        report = csq.review_spec(p)
        ck = next(c for c in report.checks if "Self-contained" in c.name)
        assert ck.passed


class TestGrade:
    def test_clean_spec_gets_a_or_b(self, tmp_path):
        body = (
            "# Purpose\n\n"
            "Users can POST /api/invoices to create invoices.\n\n"
            "## Milestone 1: Create endpoint\n\n"
            "**Demo:** When I POST /api/invoices, I see HTTP 201 with body containing invoice_id.\n\n"
            "Files involved: backend/routers/invoices.py and backend/tests/test_invoices.py.\n\n"
            "## Validation and Acceptance\n\n"
            "POST /api/invoices returns 201 with valid invoice_id field.\n"
            "Response must contain status equals 'created' and amount equals input.\n"
            "Verify response.total equals the sum of line items.\n\n"
            "```\n$ curl -X POST http://localhost:8000/api/invoices\n```\n"
        )
        p = _write(tmp_path, body)
        report = csq.review_spec(p)
        assert report.grade in {"A", "B", "C"}, f"got {report.grade}"
        assert not report.blockers

    def test_terrible_spec_fails_grade(self, tmp_path):
        body = "# Stuff\nMake it work as discussed. Should be user-friendly etc.\n"
        p = _write(tmp_path, body)
        report = csq.review_spec(p)
        assert report.grade == "F"
        assert len(report.blockers) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
