#!/usr/bin/env python3
"""check_spec_compliance.py — Evidence traceability pipeline.

Maps every feature in .harness/feature_list.json to:
  - Implementation evidence: file:line where the feature is implemented
  - Test evidence: test name at file:line where the feature is tested
  - Status: PASS (both found), WARN (impl but no test), FAIL (neither)

Produces an evidence matrix that can be embedded in PR bodies.
Saves full report to .harness/evidence.md.

Exit code 0 = all features have evidence, 1 = gaps found.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
FEATURE_LIST = REPO_ROOT / ".harness" / "feature_list.json"
EVIDENCE_FILE = REPO_ROOT / ".harness" / "evidence.md"

# Directories to search for implementation
IMPL_DIRS = ["backend", "src", "app", "lib", "api", "server"]

# Directories to search for tests
TEST_DIRS = ["tests", "test", "backend/tests", "src/tests", "__tests__"]

# File extensions to search
CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs"}
TEST_PATTERNS = {"test_", "_test.", ".test.", ".spec.", "tests/", "test/", "__tests__/"}


def load_features() -> list[dict]:
    """Load feature list from .harness/feature_list.json."""
    if not FEATURE_LIST.exists():
        return []
    data = json.loads(FEATURE_LIST.read_text(encoding="utf-8"))
    return data.get("features", [])


def collect_source_files(dirs: list[str]) -> list[Path]:
    """Collect source files from given directories."""
    files = []
    for dirname in dirs:
        d = REPO_ROOT / dirname
        if d.is_dir():
            for f in d.rglob("*"):
                if f.suffix in CODE_EXTS and "__pycache__" not in str(f) and "node_modules" not in str(f):
                    files.append(f)
    return files


def is_test_file(filepath: Path) -> bool:
    """Check if a file is a test file."""
    name = filepath.name.lower()
    path_str = str(filepath).lower()
    return any(p in name or p in path_str for p in TEST_PATTERNS)


def extract_search_terms(feature: dict) -> list[str]:
    """Extract meaningful search terms from a feature description and steps."""
    terms = []
    desc = feature.get("description", "")
    steps = feature.get("steps", [])

    # Extract HTTP endpoints (e.g., /health, /api/auth/register)
    for text in [desc] + steps:
        endpoints = re.findall(r'(?:GET|POST|PUT|DELETE|PATCH)?\s*(/[\w/.-]+)', text)
        terms.extend(endpoints)

    # Extract key nouns from description
    # Remove common verbs and articles
    stop_words = {
        "returns", "creates", "shows", "renders", "with", "and", "the", "a",
        "an", "from", "that", "this", "for", "are", "is", "be", "has",
        "verify", "send", "check", "contains", "http", "response", "request",
        "valid", "invalid", "page", "endpoint", "after", "before",
    }
    words = re.findall(r'\b([a-zA-Z_]{4,})\b', desc.lower())
    terms.extend(w for w in words if w not in stop_words)

    # Extract quoted strings
    quoted = re.findall(r'"([^"]+)"', desc)
    terms.extend(quoted)

    # Extract status codes
    codes = re.findall(r'\b(\d{3})\b', " ".join([desc] + steps))
    terms.extend(codes)

    return list(set(terms))


def find_implementation(
    feature: dict,
    source_files: list[Path],
) -> Optional[tuple[str, int]]:
    """Search source files for implementation evidence."""
    terms = extract_search_terms(feature)
    if not terms:
        return None

    best_match: Optional[tuple[str, int, int]] = None  # (file, line, score)

    for filepath in source_files:
        if is_test_file(filepath):
            continue
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        lines = content.split("\n")
        for line_num, line in enumerate(lines, 1):
            score = sum(1 for t in terms if t.lower() in line.lower())
            if score >= 2:  # At least 2 terms match on same line
                if best_match is None or score > best_match[2]:
                    rel = str(filepath.relative_to(REPO_ROOT))
                    best_match = (rel, line_num, score)

    if best_match:
        return (best_match[0], best_match[1])

    # Fallback: search for any single strong term (endpoint)
    for filepath in source_files:
        if is_test_file(filepath):
            continue
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for term in terms:
            if term.startswith("/") and len(term) > 2:  # Endpoint
                lines = content.split("\n")
                for line_num, line in enumerate(lines, 1):
                    if term in line:
                        rel = str(filepath.relative_to(REPO_ROOT))
                        return (rel, line_num)

    return None


def find_test_evidence(
    feature: dict,
    source_files: list[Path],
) -> Optional[tuple[str, str, int]]:
    """Search test files for test evidence. Returns (file, test_name, line)."""
    terms = extract_search_terms(feature)
    if not terms:
        return None

    for filepath in source_files:
        if not is_test_file(filepath):
            continue
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        lines = content.split("\n")
        current_test = None
        current_test_line = 0

        for line_num, line in enumerate(lines, 1):
            # Detect test function definitions
            test_match = re.match(
                r'\s*(?:def|async def|it|test|describe)\s+["\']?(test_\w+|[\w\s]+)["\']?',
                line,
            )
            if test_match or re.match(r'\s*(?:def|async def)\s+(test_\w+)', line):
                func_match = re.match(r'\s*(?:def|async def)\s+(test_\w+)', line)
                if func_match:
                    current_test = func_match.group(1)
                    current_test_line = line_num

            # Check if any terms appear in test context
            score = sum(1 for t in terms if t.lower() in line.lower())
            if score >= 1 and current_test:
                rel = str(filepath.relative_to(REPO_ROOT))
                return (rel, current_test, current_test_line)

    return None


def generate_report(features: list[dict], evidence: list[dict]) -> str:
    """Generate markdown evidence report."""
    lines = [
        "# Spec Compliance Evidence Report",
        "",
        "Generated by `check_spec_compliance.py`",
        "",
        "| # | Feature | Implementation | Test | Status |",
        "|---|---------|---------------|------|--------|",
    ]

    for e in evidence:
        impl = e["implementation"] or "NOT FOUND"
        test = e["test"] or "NOT FOUND"
        status = e["status"]
        status_icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}.get(status, "❓")
        lines.append(
            f"| {e['id']} | {e['description'][:40]} | `{impl}` | `{test}` | {status_icon} {status} |"
        )

    # Summary
    pass_count = sum(1 for e in evidence if e["status"] == "PASS")
    warn_count = sum(1 for e in evidence if e["status"] == "WARN")
    fail_count = sum(1 for e in evidence if e["status"] == "FAIL")
    lines.extend([
        "",
        f"**Summary:** {pass_count} PASS, {warn_count} WARN, {fail_count} FAIL",
    ])

    return "\n".join(lines)


def main() -> int:
    features = load_features()

    if not features:
        print("[X7] Spec compliance: no features in .harness/feature_list.json — skipping")
        return 0

    # Collect all source files
    source_files = collect_source_files(IMPL_DIRS + TEST_DIRS)

    # Also search root-level Python files
    for f in REPO_ROOT.glob("*.py"):
        if f.name not in {"setup.py", "conftest.py"}:
            source_files.append(f)

    evidence: list[dict] = []
    has_failures = False

    print("[X7] SPEC COMPLIANCE — Evidence Traceability")
    print("=" * 70)
    print(f"{'ID':<6} {'Description':<35} {'Impl':<20} {'Test':<20} {'Status'}")
    print("-" * 70)

    for feature in features:
        fid = feature.get("id", "?")
        desc = feature.get("description", "")[:35]

        impl = find_implementation(feature, source_files)
        test = find_test_evidence(feature, source_files)

        impl_str = f"{impl[0]}:{impl[1]}" if impl else None
        test_str = f"{test[1]} at {test[0]}:{test[2]}" if test else None

        if impl and test:
            status = "PASS"
        elif impl and not test:
            status = "WARN"
            has_failures = True
        else:
            status = "FAIL"
            has_failures = True

        evidence.append({
            "id": fid,
            "description": feature.get("description", ""),
            "implementation": impl_str,
            "test": test_str,
            "status": status,
        })

        status_icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}[status]
        print(
            f"{fid:<6} {desc:<35} "
            f"{(impl_str or 'NOT FOUND'):<20} "
            f"{(test_str[:20] if test_str else 'NOT FOUND'):<20} "
            f"{status_icon} {status}"
        )

    print("=" * 70)

    pass_count = sum(1 for e in evidence if e["status"] == "PASS")
    warn_count = sum(1 for e in evidence if e["status"] == "WARN")
    fail_count = sum(1 for e in evidence if e["status"] == "FAIL")

    print(f"Results: {pass_count} PASS, {warn_count} WARN, {fail_count} FAIL")

    # Write evidence report
    report = generate_report(features, evidence)
    EVIDENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_FILE.write_text(report, encoding="utf-8")
    print(f"\nEvidence report saved to: .harness/evidence.md")

    # Also save as JSON for programmatic use
    evidence_json = REPO_ROOT / ".harness" / "evidence.json"
    evidence_json.write_text(
        json.dumps({"features": evidence}, indent=2),
        encoding="utf-8",
    )

    if fail_count > 0:
        print(f"\n[X7] SPEC COMPLIANCE FAILED — {fail_count} feature(s) missing implementation evidence")
        return 1
    elif warn_count > 0:
        print(f"\n[X7] SPEC COMPLIANCE WARNING — {warn_count} feature(s) missing test evidence")
        # Warnings don't fail the gate, but are visible
        return 0
    else:
        print(f"\n[X7] Spec compliance passed — all features have implementation + test evidence")
        return 0


if __name__ == "__main__":
    sys.exit(main())
