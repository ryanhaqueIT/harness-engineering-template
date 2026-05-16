#!/usr/bin/env python3
"""check_spec_quality.py — Pre-build spec quality gate.

The cheapest place to catch a bad feature is BEFORE you write code for it.
This gate inspects an ExecPlan (or product spec) and scores it on the
properties that an autonomous build pipeline needs:

  1. Observable outcomes  — every milestone has a "Demo:" or measurable result
  2. Concrete steps       — commands with exact paths, not "update the config"
  3. Acceptance criteria  — assertions you can check, not "should work well"
  4. No vague language    — flags "user-friendly", "robust", "fast", "etc."
  5. Self-contained       — does not say "see prior plan" or "as discussed"

The orchestrator (ship.py) runs this BEFORE seeding features. A spec that
fails here gets bounced back for revision instead of producing wasted code.

Inspired by the Specwright "7-dimension spec review" pattern, but reduced to
mechanical heuristics that don't need an LLM.

Usage:
  python scripts/check_spec_quality.py docs/exec-plans/active/foo.md
  python scripts/check_spec_quality.py docs/product-specs/bar.md --strict
  python scripts/check_spec_quality.py --all-active       # all active plans
  python scripts/check_spec_quality.py --summary          # one-line output

Exit codes:
  0 = spec passes quality threshold (or no active spec found)
  1 = spec fails quality threshold and should be revised before build
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ─── Color output ────────────────────────────────────────────────────

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
DIM = "\033[2m"
BOLD = "\033[1m"
NC = "\033[0m"


def c(code: str, text: str) -> str:
    if not (hasattr(sys.stdout, "isatty") and sys.stdout.isatty()):
        return text
    return f"{code}{text}{NC}"


# ─── Heuristics ──────────────────────────────────────────────────────

# Words that almost always indicate vague, unverifiable language.
# We allow them inside code blocks and inline code, only flag in prose.
VAGUE_WORDS = {
    "user-friendly",
    "intuitive",
    "seamless",
    "robust",
    "performant",
    "scalable",
    "secure",
    "fast enough",
    "appropriate",
    "reasonable",
    "well-designed",
    "should work",
    "should handle",
    "as needed",
    "etc.",
    "and so on",
    "various",
    "some",
    "many",
    "tbd",
    "todo",
}

# Phrases that indicate the spec references context the autonomous build
# cannot see. The spec must be self-contained.
EXTERNAL_REF_PATTERNS = [
    r"\bas discussed\b",
    r"\bas (we|you) (?:agreed|decided)\b",
    r"\bprior (?:plan|conversation|discussion)\b",
    r"\bsee (?:the|prior|previous)\b.*\b(?:plan|doc|discussion)\b",
    r"\b(?:from|in) (?:our|the) (?:meeting|call|slack|email)\b",
]

# A "demo statement" anchors a milestone to an observable outcome.
# Accepts: **Demo:**, **Demo**:, Demo:, **Demo statement:**, Observable outcome:, Acceptance:
DEMO_MARKERS = [
    r"\*\*demo[\* ]",                  # **Demo... (covers **Demo:** and **Demo**:)
    r"\*\*demo statement",
    r"(?<![a-z])demo:",                # demo: not preceded by another letter
    r"observable outcome:",
    r"acceptance:",
]

# Code-block patterns we ignore for vague-word checks
CODE_BLOCK = re.compile(r"```[\s\S]*?```|`[^`\n]+`")


@dataclass
class SpecCheck:
    name: str
    passed: bool
    severity: str  # "blocker" | "warning" | "info"
    detail: str = ""
    locations: list[str] = field(default_factory=list)


@dataclass
class SpecReport:
    path: Path
    checks: list[SpecCheck] = field(default_factory=list)

    @property
    def blockers(self) -> list[SpecCheck]:
        return [ck for ck in self.checks if ck.severity == "blocker" and not ck.passed]

    @property
    def warnings(self) -> list[SpecCheck]:
        return [ck for ck in self.checks if ck.severity == "warning" and not ck.passed]

    @property
    def passing(self) -> list[SpecCheck]:
        return [ck for ck in self.checks if ck.passed]

    @property
    def grade(self) -> str:
        total = len(self.checks) or 1
        passed = len(self.passing)
        ratio = passed / total
        if self.blockers:
            return "F"
        if ratio >= 0.9:
            return "A"
        if ratio >= 0.8:
            return "B"
        if ratio >= 0.7:
            return "C"
        if ratio >= 0.6:
            return "D"
        return "F"


# ─── Individual checks ───────────────────────────────────────────────


def strip_code(text: str) -> str:
    """Remove fenced and inline code so vague-word checks don't false-positive."""
    return CODE_BLOCK.sub(" ", text)


def find_line_numbers(text: str, pattern: re.Pattern) -> list[int]:
    locs: list[int] = []
    for i, line in enumerate(text.splitlines(), 1):
        if pattern.search(line):
            locs.append(i)
    return locs


def check_purpose_section(text: str) -> SpecCheck:
    """A purpose / big-picture section must exist."""
    has = re.search(r"^#+\s*(?:purpose|big picture|goal|overview)\b", text, re.IGNORECASE | re.MULTILINE)
    return SpecCheck(
        name="Purpose/Big Picture section",
        passed=bool(has),
        severity="blocker",
        detail="Spec must answer 'what can users do after this change that they could not before?'",
    )


def check_milestones_have_demo(text: str) -> SpecCheck:
    """Each milestone heading must be followed by a Demo statement."""
    lines = text.splitlines()
    milestone_pattern = re.compile(r"^#+\s*milestone\s+\d+", re.IGNORECASE)
    demo_re = re.compile("|".join(DEMO_MARKERS), re.IGNORECASE)

    missing_at: list[int] = []
    n = len(lines)
    for i, line in enumerate(lines):
        if not milestone_pattern.match(line):
            continue
        # Look ahead within 15 lines for a demo marker
        window = "\n".join(lines[i + 1 : i + 16])
        if not demo_re.search(window):
            missing_at.append(i + 1)

    return SpecCheck(
        name="Milestones have Demo statements",
        passed=len(missing_at) == 0,
        severity="blocker",
        detail=f"{len(missing_at)} milestone(s) missing a 'Demo:' or 'Observable outcome:' marker"
        if missing_at
        else "All milestones have observable outcomes",
        locations=[f"line {n}" for n in missing_at[:5]],
    )


def check_concrete_commands(text: str) -> SpecCheck:
    """Spec should include actual shell/code commands, not just prose."""
    fenced_blocks = re.findall(r"```[\s\S]*?```", text)
    # Look for blocks that contain shell-like content
    cmd_indicators = [
        r"\$\s+\S+",
        r"\bcurl\b",
        r"\bpytest\b",
        r"\bnpm\b",
        r"\bpython\b",
        r"\bnpx\b",
        r"\bbash\b",
        r"\bvalidate\.sh\b",
        r"\bcheck_features",
    ]
    cmd_re = re.compile("|".join(cmd_indicators))
    cmd_blocks = sum(1 for b in fenced_blocks if cmd_re.search(b))

    return SpecCheck(
        name="Concrete commands present",
        passed=cmd_blocks >= 1,
        severity="warning",
        detail=f"Found {cmd_blocks} code block(s) with shell commands"
        if cmd_blocks
        else "No shell commands found — spec is prose-only",
    )


def check_file_paths_referenced(text: str) -> SpecCheck:
    """Spec should reference specific files/modules so the executor knows the surface area."""
    # Look for paths like backend/main.py, scripts/foo.sh, docs/exec-plans/active/...
    path_re = re.compile(r"\b(?:[A-Za-z0-9_-]+/){1,}[A-Za-z0-9_.-]+\.(?:py|ts|tsx|js|jsx|md|sh|json|yaml|yml|toml)\b")
    matches = path_re.findall(text)
    unique_paths = set(matches)

    return SpecCheck(
        name="File paths referenced",
        passed=len(unique_paths) >= 2,
        severity="warning",
        detail=f"Found {len(unique_paths)} file path(s)"
        if unique_paths
        else "No repository-relative file paths found — executor will have to guess where to put code",
    )


def check_no_vague_language(text: str) -> SpecCheck:
    """Flag vague, unverifiable adjectives in prose (not in code blocks)."""
    prose = strip_code(text).lower()
    found: dict[str, int] = {}
    for word in VAGUE_WORDS:
        count = prose.count(word)
        if count > 0:
            found[word] = count

    return SpecCheck(
        name="No vague language",
        passed=len(found) == 0,
        severity="warning",
        detail=(
            "Vague terms in prose: "
            + ", ".join(f"'{w}'×{n}" for w, n in sorted(found.items(), key=lambda x: -x[1])[:5])
        )
        if found
        else "No vague language detected",
    )


def check_self_contained(text: str) -> SpecCheck:
    """Spec must not reference invisible external context."""
    found_refs: list[tuple[str, int]] = []
    for pattern in EXTERNAL_REF_PATTERNS:
        rx = re.compile(pattern, re.IGNORECASE)
        for i, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                found_refs.append((line.strip()[:60], i))

    return SpecCheck(
        name="Self-contained (no external references)",
        passed=len(found_refs) == 0,
        severity="blocker",
        detail=f"{len(found_refs)} reference(s) to invisible external context"
        if found_refs
        else "Spec is self-contained",
        locations=[f"line {ln}: '{txt}...'" for txt, ln in found_refs[:3]],
    )


def check_acceptance_criteria(text: str) -> SpecCheck:
    """A Validation/Acceptance section must exist with at least one assertion."""
    has_section = re.search(
        r"^#+\s*(?:validation|acceptance|verification)\b",
        text,
        re.IGNORECASE | re.MULTILINE,
    )
    if not has_section:
        return SpecCheck(
            name="Acceptance criteria section",
            passed=False,
            severity="blocker",
            detail="No 'Validation' or 'Acceptance' section — autonomous build can't know when done",
        )

    # Look for assertion-like language in the section
    section_start = has_section.start()
    section_text = text[section_start : section_start + 3000]
    assertion_indicators = [
        r"\breturns?\s+(?:http\s+)?\d{3}\b",
        r"\bequals?\b",
        r"\bcontains?\b",
        r"\b(?:should|must|will)\s+\w+",
        r"\bverif(?:y|ies|ied)\b",
        r"\bassert\b",
    ]
    assertion_count = sum(
        len(re.findall(p, section_text, re.IGNORECASE)) for p in assertion_indicators
    )

    return SpecCheck(
        name="Acceptance criteria has assertions",
        passed=assertion_count >= 2,
        severity="warning",
        detail=f"Found {assertion_count} assertion-like statements"
        if assertion_count
        else "Acceptance section exists but lacks specific assertions",
    )


def check_rollback_procedure(text: str) -> SpecCheck:
    """For risky operations, a rollback procedure should be described."""
    risky_indicators = [
        r"\bmigration\b",
        r"\bdrop (?:table|column|index)\b",
        r"\bdelete\b.*\b(?:user|data|record)\b",
        r"\bcdk deploy\b",
        r"\bterraform apply\b",
    ]
    risky_re = re.compile("|".join(risky_indicators), re.IGNORECASE)
    has_risky = bool(risky_re.search(text))

    if not has_risky:
        return SpecCheck(
            name="Rollback procedure (when risky)",
            passed=True,
            severity="info",
            detail="No risky operations detected — rollback not required",
        )

    has_rollback = re.search(
        r"\brollback\b|\bidempotence\b|\brevert\b|\brecover\b",
        text,
        re.IGNORECASE,
    )
    return SpecCheck(
        name="Rollback procedure (risky ops detected)",
        passed=bool(has_rollback),
        severity="warning",
        detail="Risky ops mentioned but no rollback/idempotence procedure found"
        if not has_rollback
        else "Rollback or idempotence procedure documented",
    )


CHECKS = [
    check_purpose_section,
    check_milestones_have_demo,
    check_acceptance_criteria,
    check_self_contained,
    check_concrete_commands,
    check_file_paths_referenced,
    check_no_vague_language,
    check_rollback_procedure,
]


# ─── Driver ──────────────────────────────────────────────────────────


def review_spec(path: Path) -> SpecReport:
    text = path.read_text(encoding="utf-8", errors="replace")
    report = SpecReport(path=path)
    for fn in CHECKS:
        report.checks.append(fn(text))
    return report


def render_report(report: SpecReport, summary: bool) -> str:
    if summary:
        passed = len(report.passing)
        total = len(report.checks)
        blockers = len(report.blockers)
        if blockers:
            return f"Spec quality: {passed}/{total} ({report.grade}) — {blockers} blocker(s)"
        return f"Spec quality: {passed}/{total} ({report.grade})"

    lines = [
        c(BOLD, "═══════════════════════════════════════════════════"),
        c(BOLD, f" Spec Quality Review — {report.path.name}"),
        c(BOLD, "═══════════════════════════════════════════════════"),
    ]
    for ck in report.checks:
        if ck.severity == "info" and ck.passed:
            tag = c(DIM, "INFO")
        elif ck.passed:
            tag = c(GREEN, "PASS")
        elif ck.severity == "blocker":
            tag = c(RED, "FAIL")
        else:
            tag = c(YELLOW, "WARN")
        lines.append(f"  {tag}  {ck.name}")
        if ck.detail:
            lines.append(f"        {c(DIM, ck.detail)}")
        for loc in ck.locations[:3]:
            lines.append(f"        {c(DIM, loc)}")

    lines.append("")
    blockers = len(report.blockers)
    warnings = len(report.warnings)
    grade = report.grade
    grade_color = GREEN if grade in ("A", "B") else YELLOW if grade in ("C", "D") else RED
    lines.append(
        c(BOLD, f" Grade: {c(grade_color, grade)}  ")
        + f" ({len(report.passing)}/{len(report.checks)} checks, "
        f"{blockers} blocker(s), {warnings} warning(s))"
    )
    if blockers:
        lines.append("")
        lines.append(c(RED, "  Build is NOT recommended — fix blockers before invoking /ship."))
    elif warnings:
        lines.append("")
        lines.append(c(YELLOW, "  Build can proceed but spec has warnings worth addressing."))
    else:
        lines.append("")
        lines.append(c(GREEN, "  Spec is ready for autonomous build."))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Spec quality pre-build gate")
    parser.add_argument("path", nargs="?", help="Path to spec file (.md)")
    parser.add_argument("--all-active", action="store_true", help="Review every plan in docs/exec-plans/active/")
    parser.add_argument("--strict", action="store_true", help="Fail on warnings, not just blockers")
    parser.add_argument("--summary", action="store_true", help="One-line output")
    args = parser.parse_args()

    paths: list[Path] = []
    if args.all_active:
        active_dir = REPO_ROOT / "docs" / "exec-plans" / "active"
        if active_dir.is_dir():
            paths = sorted(active_dir.glob("*.md"))
    elif args.path:
        paths = [Path(args.path)]
    else:
        # Default: pick the most recently modified plan in active/
        active_dir = REPO_ROOT / "docs" / "exec-plans" / "active"
        if active_dir.is_dir():
            candidates = sorted(active_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
            paths = candidates[:1]

    if not paths:
        if args.summary:
            print("Spec quality: SKIP (no active spec)")
        else:
            print(c(YELLOW, "No spec to review. Pass a path or create docs/exec-plans/active/<name>.md"))
        return 0

    overall_fail = False
    for p in paths:
        if not p.exists():
            print(c(RED, f"Spec file not found: {p}"))
            overall_fail = True
            continue
        report = review_spec(p)
        print(render_report(report, summary=args.summary))
        if not args.summary:
            print()
        if report.blockers or (args.strict and report.warnings):
            overall_fail = True

    return 1 if overall_fail else 0


if __name__ == "__main__":
    sys.exit(main())
