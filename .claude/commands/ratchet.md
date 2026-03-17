Run the ratchet check and show the violation comparison table.

## Steps

1. Check if `scripts/ratchet.py` exists. If not, report that the ratchet script is not yet installed and suggest adding it.
2. Execute `python scripts/ratchet.py` from the repository root.
3. Display the violation comparison table showing:
   - Category name
   - Baseline count (last known good)
   - Current count
   - Delta (regression or improvement)
4. If any category regressed (current > baseline):
   - Name the category.
   - Run targeted analysis to find the specific files causing regression:
     - For lint regressions: run `ruff check .` and list new violations
     - For type regressions: run `pyright` and list new errors
     - For test regressions: run `pytest` and list newly failing tests
     - For architecture regressions: run `scripts/check_architecture.py` and list new violations
     - For import regressions: run `scripts/check_imports.py` and list new violations
   - For each file, show the exact line causing the regression.
5. If no regressions: confirm "Ratchet holds -- no categories regressed."
6. If any categories improved (current < baseline): highlight them as wins.

## Context

The ratchet enforces that violation counts never increase. Each commit must have
fewer or equal violations compared to the baseline. The baseline is stored in
`scripts/ratchet_baseline.json` (or similar). Categories include: lint errors,
type errors, test failures, architecture violations, import violations, and
security findings.
