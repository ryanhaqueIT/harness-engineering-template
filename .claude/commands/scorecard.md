Run the harness maturity scorecard and display the grade.

## Steps

1. Check if `scripts/harness_scorecard.py` exists. If not, report that the scorecard script is not yet installed and suggest adding it.
2. Execute `python scripts/harness_scorecard.py` from the repository root.
3. Display the full scorecard output including:
   - Per-category scores (documentation, testing, architecture, CI, security, reliability)
   - Overall letter grade (A/B/C/D/F)
   - Total points vs maximum possible
4. If the grade is below A:
   - List each category that lost points.
   - For each, provide a specific improvement action:
     - Missing docs: name which doc files to create or update
     - Low test coverage: name which modules lack test files
     - Architecture violations: name which boundaries are crossed
     - Missing CI gates: name which checks to add to validate.sh
     - Security gaps: name which files need secrets removed or encryption added
     - Reliability gaps: name which services lack structured logging or timeouts
5. Rank improvements by impact (most points gained per effort).

## Context

The scorecard measures harness engineering maturity across six dimensions.
Each dimension is scored 0-100. The overall grade is the weighted average.
Grade thresholds: A >= 90, B >= 80, C >= 70, D >= 60, F < 60.
