Run the universal validation gate and report results.

## Steps

1. Execute `scripts/validate.sh` from the repository root.
2. Parse the output for PASS, FAIL, and SKIP counts.
3. If any gate fails:
   - List each failed gate by ID (e.g., [B1], [F3], [X2]) with the error output.
   - For each failure, provide a specific fix instruction:
     - Lint failures: run `ruff check --fix .` or `eslint --fix .`
     - Format failures: run `ruff format .` or `prettier --write .`
     - Test failures: show the failing test name and assertion
     - Import boundary violations: name the offending import and which module rule it breaks
     - Golden principle violations: name the file and line
     - Architecture violations: name the file and the boundary crossed
     - Secret detection: name the file containing the secret
4. If all gates pass: confirm "All gates passed -- ready to commit."
5. Show the summary line: X passed, Y failed, Z skipped.

## Important

- Run from the repository root directory.
- Do not skip any failed gate -- report all of them.
- If validate.sh is missing, report that and suggest running `setup.sh` first.
