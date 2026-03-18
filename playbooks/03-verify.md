# Phase 3: Verify

Validate that the generated harness is correct, consistent, and functional. Nothing is done until this phase passes.

## Step 1: Script Syntax Validation

Verify every generated script parses without errors:

**Python scripts** — For each `.py` file in the target's `scripts/` directory:
```bash
python3 -c "import py_compile; py_compile.compile('scripts/check_imports.py', doraise=True)"
```
Do this for: check_imports.py, check_golden_principles.py, check_architecture.py, check_features.py, playwright_gate.py, ratchet.py, harness_scorecard.py.

**Shell scripts** — For each `.sh` file:
```bash
bash -n scripts/validate.sh
```
Do this for: validate.sh, boot_worktree.sh, check_ui_legibility.sh, check_e2e_deployed.sh, check_observability.sh, check_features.sh, query_logs.sh, query_metrics.sh.

If ANY script fails syntax validation, fix it before proceeding.

## Step 2: validate.sh Dry Run

Run validate.sh from the target repo root:
```bash
cd /path/to/target-repo && bash scripts/validate.sh
```

**Expected outcome**: A mix of PASS, FAIL, and SKIP results. The script should NOT crash or error.

- PASS on structural checks (import boundaries, golden principles, architecture, doc cross-refs, secret scan)
- SKIP on runtime checks (E2E, UI legibility, observability — these require a running app)
- FAIL is acceptable for existing code quality issues (lint errors, missing tests) — the ratchet will baseline these

**NOT acceptable**: Script crashes, syntax errors, or "command not found" errors. Fix these immediately.

Review the output and note:
- How many gates passed
- How many were skipped (and why)
- How many failed (these become the ratchet baseline)

## Step 3: Feature List Validation

Verify the generated `.harness/feature_list.json`:

```bash
python3 scripts/check_features.py
```

Expected output: `Feature List Gate — 0/N passing` (all features start as `passes: false`).

Verify:
- JSON is valid (no parse errors)
- Every feature has required fields: id, category, priority, description, steps, passes
- Feature IDs are unique
- Categories are valid: functional, ui, security, reliability, observability

## Step 4: Initialize Ratchet Baseline

Run the ratchet in init mode to lock in the current quality state:

```bash
python3 scripts/ratchet.py --init
```

This creates `.harness/baseline.json` with current violation counts. From this point forward, quality can only improve — the ratchet prevents regressions.

Review the baseline:
- `lint_errors`: Current lint error count (will decrease over time)
- `format_errors`: Current format issues
- `import_violations`: Should be 0 if rules are correct
- `architecture_violations`: Should be 0 if constants are correct
- `golden_principle_violations`: Current count
- `todo_fixme_count`: Current TODO/FIXME/HACK count
- `god_files`: Number of files over MAX_LINES
- `test_coverage_ratio`: Current test-to-source ratio

If `import_violations` or `architecture_violations` are non-zero, review the configuration — the rules may need adjustment.

## Step 5: Run Scorecard

Run the harness maturity scorecard:

```bash
python3 scripts/harness_scorecard.py
```

**Target: Grade B or higher** (21+ out of 31 checks passing).

The scorecard checks for file existence, lint gates, format gates, import checker, golden principles checker, architecture checker, CI workflows, test directory, test count, E2E scripts, UI validation, health endpoint, observability, ratchet baseline, and more.

If the grade is below B, review which checks failed and determine if additional files need to be generated or if the target repo needs prerequisites installed.

## Step 6: Agent File Consistency Check

Verify that AGENTS.md, CLAUDE.md, and .github/copilot-instructions.md are consistent:

1. Extract the Commands section from each file
2. Verify all three list the same commands with the same syntax
3. Extract the Module Dependency Rules from each
4. Verify all three list the same rules
5. Extract the Boundaries section from each
6. Verify the Always/Ask/Never lists match

If any inconsistency is found, fix the divergent file.

## Step 7: Claude Code Integration Check

Verify `.claude/settings.json`:
1. Valid JSON (no parse errors)
2. Every script referenced in `permissions.allow` exists in the target's `scripts/` directory
3. Hook scripts referenced in `hooks` exist in `.claude/hooks/`
4. Command files exist in `.claude/commands/`

Run a quick check:
```bash
python3 -c "import json; json.load(open('.claude/settings.json'))"
```

## Step 8: CI Workflow Validation

If CI workflows were generated:

**GitHub Actions**: Verify YAML syntax:
```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
```

Check that:
- Workflow triggers are correct (push to main, pull_request)
- All referenced scripts exist
- Language setup matches the detected stack

## Step 9: Cross-Reference Validation

Verify internal consistency across all generated files:

1. Every module listed in AGENTS.md's Module Dependency Rules exists as a directory in the source root
2. Every doc file referenced in AGENTS.md's Progressive Disclosure table exists
3. Every script referenced in validate.sh exists in `scripts/`
4. If PLANS.md references `docs/exec-plans/active/`, that directory exists

## Step 10: Run validate.sh One More Time

After all fixes from steps 1-9, run validate.sh again:

```bash
cd /path/to/target-repo && bash scripts/validate.sh
```

Confirm the results are clean (or have only expected failures from pre-existing code quality).

## Step 11: Final Report

Produce a comprehensive summary:

```
═══════════════════════════════════════════════════
 Harness Engineering Bootstrap — Verification Report
═══════════════════════════════════════════════════

Target: /path/to/target-repo
Stack:  Python (FastAPI) + TypeScript (Next.js)
CI:     GitHub Actions

Scripts Generated:    22
Scripts Configured:   7 (validate.sh, check_imports.py, check_architecture.py, ...)
Scripts Static:       15 (check_features.py, ratchet.py, ...)
Docs Generated:       12
CI Workflows:         4

validate.sh Results:
  Passed: 12
  Failed: 3 (B1 lint: 23 errors, B3 tests: 2 failing, R1 ratchet: baseline created)
  Skipped: 7 (E2E, UI legibility, observability — need running app)

Ratchet Baseline:
  lint_errors: 23
  format_errors: 0
  import_violations: 0
  architecture_violations: 0
  golden_principle_violations: 5
  todo_fixme_count: 7
  god_files: 2
  test_coverage_ratio: 0.36

Scorecard: Grade B (23/31 checks passing)

Feature List: 8 features seeded (0/8 passing — ready for implementation)

Agent File Sync: AGENTS.md ✓  CLAUDE.md ✓  copilot-instructions.md ✓

Next Steps:
  1. Review and customize AGENTS.md boundaries for your team
  2. Fix the 23 lint errors (run: {{lint_cmd}} --fix)
  3. Fix the 5 golden principle violations (run: python scripts/check_golden_principles.py)
  4. Boot the app and run UI legibility checks: ./scripts/boot_worktree.sh
  5. Start verifying features in .harness/feature_list.json
  6. The ratchet is active — quality can only improve from here

═══════════════════════════════════════════════════
 Harness deployed. validate.sh is now THE RULE.
═══════════════════════════════════════════════════
```

The harness is now active. Every commit must pass validate.sh. The ratchet ensures quality only goes up. The feature list tracks PRD completion. The scorecard measures harness maturity.
