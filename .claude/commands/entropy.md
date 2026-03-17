Scan the codebase for entropy, drift, and accumulated tech debt.

## Steps

1. Run `python scripts/harness_scorecard.py` from the repo root. Report the grade and any failing checks.
2. Run `python scripts/ratchet.py --show` from the repo root. Report the current baseline vs potential improvements.
3. Search for entropy markers in backend code:
   - `grep -rn "TODO\|FIXME\|HACK\|XXX\|NOCOMMIT" backend/ --include="*.py" | head -30`
   - If a frontend/ directory exists, also scan: `grep -rn "TODO\|FIXME\|HACK\|XXX" frontend/ --include="*.ts" --include="*.tsx" | head -20`
4. Check for orphan files: find Python files in backend/ that are not imported by any other Python file in the project. Ignore `__init__.py`, test files, and scripts/.
5. Check for dead code: find functions/classes defined in backend/ that are never referenced elsewhere (best effort — check with grep).
6. Check for pattern drift:
   - Are all routers registered in `backend/main.py`?
   - Are all repository files following the same class pattern?
   - Are all services using structured logging consistently?
7. Read `docs/exec-plans/tech-debt-tracker.md` and check:
   - Are any items older than 2 weeks without progress?
   - Are any marked "in progress" but not touched recently?

## Output

For each issue found, report:
- **File:line** and description
- **Category**: `debt` (technical debt), `drift` (pattern inconsistency), `orphan` (unused code), `stale` (outdated tracker item)
- **Suggested fix**: a specific, actionable remediation

After scanning, update `docs/exec-plans/tech-debt-tracker.md` with any new items found. Do not remove existing items — only append new ones or update status on existing ones.

## Context

This command implements Concept 5 (Entropy Management) from the harness engineering framework. Entropy accumulates naturally — TODOs that never get done, imports that drift, dead code that lingers. Running this regularly keeps the codebase honest.
