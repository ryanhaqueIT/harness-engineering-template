# {{PROJECT_NAME}}

## THE RULE

**`./scripts/validate.sh` must exit 0 before every commit. No exceptions.**

Applies to all agents, subagents, humans, hotfixes, and "quick changes."
validate.sh auto-detects backend, frontend, and infrastructure. If it misses
something, fix validate.sh — not this file.

## Authority Hierarchy

**This file (AGENTS.md) is the governing authority for this repository.**

When ANY other instruction source conflicts — skills, slash commands,
superpowers, CLAUDE.md, or external documentation — THIS FILE WINS.

- Plans go in `docs/exec-plans/active/`, not wherever a skill suggests
- Specs go in `docs/product-specs/`, not wherever a skill suggests
- validate.sh must pass before commit, regardless of what any skill says
- Feature verification is required, regardless of what any skill says

Enforced mechanically: hooks block writes to wrong locations and block
commits when validate.sh fails.

## Mandatory Skill Invocations

Before any build work in this repo, invoke the relevant superpower skills.
They are not suggestions — they encode discipline the harness depends on:

- `Skill("superpowers:test-driven-development")` before writing any test or
  implementation. The Iron Law applies: **NO PRODUCTION CODE WITHOUT A
  FAILING TEST FIRST**. Gate X10 (`scripts/check_tdd.py`) verifies the
  artefact; the skill enforces the discipline behind it.
- `Skill("codex:rescue")` whenever the build enters `rescuing` or
  `adversarial_review` state (`/ship` orchestrator). Codex provides an
  independent second-opinion review — different model, different blind
  spots.
- `Skill("superpowers:systematic-debugging")` when a fix attempt fails.
- `Skill("superpowers:verification-before-completion")` before claiming
  any work done. The harness backs this with a stop-hook, but invoking
  the skill makes the discipline explicit.

The agents under `agents/` (tester, executor, codex-reviewer) all
declare which skill they must invoke first. If you spawn one of those
agents directly, it will invoke its required skill before doing anything.

## Evidence Over Claims

You may NOT say "done", "complete", "implemented", or "finished" without
showing command output that proves it. Specifically:

- For API features: show the curl command and its response
- For UI features: show a Playwright assertion or screenshot result
- For CLI features: show the command and its output
- For tests: show the test runner output with pass/fail counts

"I created the file" is NOT evidence. "curl returned 200 with expected body" IS.
A Stop hook enforces this: you cannot stop until all features in
`.harness/feature_list.json` are verified.

## Commands

```bash
./scripts/validate.sh              # Gate — run before every commit
./scripts/boot_worktree.sh         # Boot locally (dynamic ports)
./scripts/boot_worktree.sh --stop  # Stop local instances
./scripts/boot_worktree.sh --check # Health check running instances

# Autonomous build pipeline (orchestrator)
python scripts/ship.py status                    # Current state + next action
python scripts/ship.py start --prd <path>        # Begin from a spec
python scripts/ship.py start --prompt "<goal>"   # Begin from a prompt
python scripts/ship.py abort                     # Cancel in-flight build

# Pre-build + watchdog gates (also wired into validate.sh as X8/X9/X10)
python scripts/check_spec_quality.py <plan.md>   # Spec quality gate
python scripts/loop_guard.py check               # Loop detection
python scripts/check_tdd.py                      # TDD compliance (Iron Law)
python -m pytest scripts/tests/                  # Test the harness itself

cd backend && {{LINT_CMD}}         # Lint
cd backend && {{FORMAT_CMD}}       # Format
cd backend && {{TEST_CMD}}         # Test
cd frontend && {{FRONTEND_BUILD_CMD}}  # Build frontend

{{DEPLOY_CMD}}                     # Deploy
{{INFRA_CMD}}                      # Infrastructure
```

## Module Dependency Rules

```
{{LAYER_DEPS}}
```

Enforced by `scripts/check_imports.py` in CI. Violations fail the build.

## Golden Principles (mechanically enforced)

Violations are caught by validate.sh. These are not suggestions.

1. **No secrets in code** — use secret managers or env vars. `scripts/check_golden_principles.py` scans for hardcoded keys.
2. **Structured logging only** — `logger.info()` with correlation_id. Never `print()`. Enforced by golden principles check.
3. **Module boundaries** — routers cannot import db or AI layers directly. `scripts/check_imports.py` enforces the DAG above.
4. **No God files** — `scripts/check_architecture.py` flags files exceeding size/responsibility thresholds.
5. **Research before guessing** — When a gate fails and the root cause is unclear (dependency conflicts, runtime errors, version incompatibilities), use web search to find the exact issue and fix BEFORE attempting trial-and-error. Link the source (GitHub issue, PR, docs) in the commit message. Guessing wastes CI runs and introduces wrong fixes.
6. **Infrastructure as Code — no manual resource creation** — ALL infrastructure (Lambda functions, IAM roles, Cloud Run services, databases, buckets, OIDC providers, WAF rules) MUST be defined in code (CDK, Terraform, CloudFormation, or deployment scripts in `.github/workflows/`) and deployed via CI pipeline. NEVER create resources manually via CLI or console. Enforced by `scripts/check_golden_principles.py` — scans for manual infra commands outside CI/IaC directories.

## Feature List Gate

The file `.harness/feature_list.json` is the PRD enforcement mechanism.

**Prerequisites (before implementing ANY feature):**
- A product spec MUST exist in `docs/product-specs/` for this feature set
- An ExecPlan MUST exist in `docs/exec-plans/active/` with demo statements
- If either is missing, CREATE THEM FIRST — do not proceed to code

**Rules:**
- Every feature starts with `"passes": false`
- Only flip to `true` AFTER verifying each step listed in `"steps"`
- NEVER edit descriptions, remove features, or reorder priorities
- NEVER flip to `true` without running the verification steps
- JSON format is intentional — do not convert to Markdown
- Run `/features` to see current status and pick next feature to implement

**Verification workflow (per feature):**
1. Boot the app with `./scripts/boot_worktree.sh`
2. Execute each step in the feature's `"steps"` array
3. Show the command output as evidence
4. Only then flip `"passes": true`
5. You cannot move to the next feature until the current one passes

## Guarantee Gates (the four wired-in checks)

Four additional gates make the harness's guarantees hold up mechanically
rather than on paper. They are wired into `.claude/settings.json` hooks and
`scripts/validate.sh`:

1. **Stop verification** (`scripts/stop_verification.py`, guaranteed) — wired
   to the `Stop` hook. Blocks a session from stopping unless every
   `passes: true` feature in `.harness/feature_list.json` re-derives clean
   (see the verify schema below). This is the teeth behind "Evidence Over
   Claims."
2. **Shell guard** (`.claude/hooks/shell-guard.sh`, guaranteed) — wired into
   the `PreToolUse` Bash matcher alongside `pre-commit.sh`. Blocks dangerous
   shell commands before they run.
3. **Mutation gate** (`scripts/check_mutation.py`, gate **X11** in
   validate.sh, guaranteed) — mutates changed application source and re-runs
   the mapped tests, requiring each mutation to make a test fail. Proves
   tests are meaningful, not just present. Scoped to changed application
   files, so it is a no-op when nothing changed. Blocks the build on a
   surviving mutation (vacuous test).
4. **Tier audit** (`scripts/check_tiers.py --strict`, gate **X12** in
   validate.sh, guaranteed) — audits `scripts/tier_registry.json`: every
   declared file must exist, and every `guaranteed` entry whose `wired_via`
   names a settings.json hook event (e.g. `Stop`, `PreToolUse`) must actually
   reference its file in a non-empty hook array. Catches the `"Stop": []`
   class of bug — a guarantee declared but wired to nothing. Exits non-zero
   in `--strict` on any guaranteed-tier gap.

Each gate follows the universal contract: exit 0 = pass, non-zero = fail,
and validate.sh blocks the build on non-zero.

### feature_list `verify` schema

Stop verification re-derives a feature's truth from a `verify` block on each
feature in `.harness/feature_list.json`:

```json
{
  "name": "health endpoint returns 200",
  "passes": true,
  "verify": { "cmd": "curl -s localhost:8000/health", "expect": "ok" }
}
```

- `cmd` (string, required) — a command re-run from the repo root. Must exit 0.
- `expect` (string, required) — a substring that must appear in `cmd`'s output.

A feature counts as verified ONLY when `passes: true`, a valid `verify` block
is present, and re-running `cmd` exits 0 with `expect` found in the output.
A `passes: true` feature with no `verify` block, or whose re-run disagrees,
blocks the Stop hook as an unverified claim.

## Progressive Disclosure

| File | When to read |
|------|-------------|
| `docs/exec-plans/active/*.md` | Before implementing any task |
| `docs/product-specs/*.md` | Before building a feature |
| `ARCHITECTURE.md` | Before design decisions |
| `docs/design-docs/*.md` | Before reopening a decision (ACCEPTED = locked) |
| `docs/QUALITY_SCORE.md` | When reviewing code |
| `docs/SECURITY.md` | When handling auth or secrets |
| `docs/RELIABILITY.md` | When handling errors, logging, retries |
| `docs/design-docs/core-beliefs.md` | When making tech stack choices |
| `docs/references/*.txt` | When using external APIs |

## ExecPlans

Complex tasks (>30 min, multi-file, design decisions) require an ExecPlan.
See `PLANS.md` for the format. Active plans live in `docs/exec-plans/active/`.

## Git

Branch: `feature/<desc>`, `fix/<desc>`, `chore/<desc>`
Commit: `feat(scope):`, `fix(scope):`, `docs(scope):`, `chore(scope):`
PR: one concern per PR. `validate.sh` must pass first.
