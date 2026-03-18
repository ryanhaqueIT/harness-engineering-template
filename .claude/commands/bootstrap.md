Fully automated harness engineering bootstrap. Deploys all 22 validation gates into the current repo, configured for the detected stack. No manual steps — runs end to end.

$ARGUMENTS: target_path

## Execution

Run everything below automatically. Do not pause for confirmation unless you encounter a destructive action (overwriting user-modified files). The goal is: one command, fully harnessed repo.

### 1. Resolve Paths

- If `$ARGUMENTS` is provided, use that as the target repo path.
- If not provided, use the current working directory.
- Set `HARNESS_SOURCE` to `~/.harness`. This is where the template repo lives.

### 2. Fetch Harness Source

Run these commands:
```bash
if [ ! -d ~/.harness ]; then
  git clone https://github.com/ryanhaqueIT/harness-engineering-template.git ~/.harness
else
  git -C ~/.harness pull --ff-only 2>/dev/null || true
fi
```

### 3. Discover (Phase 0)

Read `~/.harness/playbooks/00-discover.md` and execute ALL detection steps against the target repo. Build the complete repo profile: language, framework, modules, DB library, AI libraries, API endpoints, frontend pages, existing harness artifacts. Do not skip any detection step.

### 4. Analyze (Phase 1)

Read `~/.harness/playbooks/01-analyze.md` and derive ALL configuration values:
- Import boundary RULES dict (trace actual imports between modules)
- Architecture constants (DB_MODULE, DB_IMPORT_PATTERNS, AI_ALLOWED_MODULES, TESTABLE_MODULES, MAX_LINES)
- Feature list seed (from discovered API endpoints and frontend pages)
- Three-tier boundaries (Always/Ask/Never)
- UI legibility pages array

**Do NOT ask the user about custom requirements.** Use sensible defaults based on what you discovered. The user can customize later.

### 5. Generate (Phase 2)

Read `~/.harness/playbooks/02-generate.md` and execute ALL generation steps:

**5a. Create directories** in the target repo:
```
scripts/ .harness/ .claude/commands/ .claude/hooks/ docs/design-docs/
docs/exec-plans/active/ docs/exec-plans/completed/ docs/product-specs/
docs/references/ docs/generated/ agents/ observability/ .github/workflows/
```

**5b. Copy static scripts** from `~/.harness/scripts/` to target `scripts/`:
```
check_features.py check_features.sh playwright_gate.py check_ui_playwright.sh
check_observability.sh query_logs.sh query_metrics.sh ratchet.py
harness_scorecard.py review_pr.sh screenshot_baseline.sh track_quality.sh
boot_worktree.sh check_ui_legibility.sh check_e2e_deployed.sh validate.sh
```

**5c. Generate configured scripts** by copying from `~/.harness/scripts/` and modifying:
- `scripts/check_imports.py` — Fill RULES dict with analyzed import boundaries. Set BACKEND path.
- `scripts/check_golden_principles.py` — Set BACKEND path to match source root.
- `scripts/check_architecture.py` — Fill ALL constants: MAX_LINES, DB_MODULE, DB_IMPORT_PATTERNS, AI_ALLOWED_MODULES, AI_IMPORT_PATTERNS, TESTABLE_MODULES, BACKEND path.

**5d. Generate AGENTS.md** in the target repo with:
- THE RULE (`validate.sh must exit 0 before every commit`)
- Commands section (detected build/test/lint/format commands)
- Module Dependency Rules (from analyzed import boundaries)
- Golden Principles (mechanically enforced list)
- Three-tier Boundaries (Always/Ask/Never)
- Progressive Disclosure table
- Feature List rules
- Standing Maintenance Orders
- ExecPlans reference
- Git conventions

**5e. Generate CLAUDE.md** — same content as AGENTS.md, add "Keep in sync with AGENTS.md".

**5f. Generate .github/copilot-instructions.md** — adapted version for Copilot.

**5g. Generate .claude/settings.json** with permissions for all generated scripts and hooks.

**5h. Copy Claude Code integration** from `~/.harness/`:
- `.claude/hooks/pre-commit.sh` and `.claude/hooks/post-edit.sh`
- All `.claude/commands/*.md` files (validate, scorecard, features, ratchet, review, plan, morning-check, entropy)

**5i. Copy CI workflows** from `~/.harness/.github/workflows/` (ci.yml, claude-review.yml, quality-scan.yml, doc-gardening.yml). Adapt language detection if needed.

**5j. Seed feature list** — Write `.harness/feature_list.json` with features derived from discovered endpoints and pages. All `passes: false`.

**5k. Copy documentation** from `~/.harness/docs/` (QUALITY_SCORE.md, SECURITY.md, RELIABILITY.md, DESIGN.md, PRODUCT_SENSE.md, core-beliefs.md, tech-debt-tracker.md).

**5l. Copy PLANS.md** from `~/.harness/PLANS.md`.

**5m. Copy agent definitions** from `~/.harness/agents/` (planner.md, reviewer.md, entropy-cleaner.md).

**5n. Copy observability stack** from `~/.harness/` (docker-compose.observability.yml, observability/vector.toml).

**5o. Append to .gitignore** (if not already present): `.harness/snapshots/`, `instance-metadata.json`, `*.pid`.

### 6. Verify (Phase 3)

Read `~/.harness/playbooks/03-verify.md` and execute verification:

**6a. Syntax check** — Verify all generated .py scripts compile and all .sh scripts parse.

**6b. Run validate.sh** in the target repo. Report results (pass/fail/skip counts).

**6c. Init ratchet** — Run `python3 scripts/ratchet.py --init` to create baseline.

**6d. Run scorecard** — Run `python3 scripts/harness_scorecard.py` and report the grade.

**6e. Check feature list** — Run `python3 scripts/check_features.py` and report status.

### 7. Report

Print a summary:

```
═══════════════════════════════════════════════════
 Harness Engineering Bootstrap — Complete
═══════════════════════════════════════════════════

Target:     /path/to/repo
Stack:      [detected language] ([detected framework])
Gates:      22 configured
Scripts:    XX copied, XX configured
Docs:       XX generated

validate.sh: XX passed, XX failed, XX skipped
Scorecard:   Grade [X] (XX/31)
Ratchet:     Baseline initialized
Features:    0/XX passing (ready for implementation)

Harness is live. validate.sh is now THE RULE.
═══════════════════════════════════════════════════
```
