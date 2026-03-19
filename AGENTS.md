# {{PROJECT_NAME}}

## THE RULE

**`./scripts/validate.sh` must exit 0 before every commit. No exceptions.**

Applies to all agents, subagents, humans, hotfixes, and "quick changes."
validate.sh auto-detects backend, frontend, and infrastructure. If it misses
something, fix validate.sh — not this file.

## Commands

```bash
./scripts/validate.sh              # Gate — run before every commit
./scripts/boot_worktree.sh         # Boot locally (dynamic ports)
./scripts/boot_worktree.sh --stop  # Stop local instances
./scripts/boot_worktree.sh --check # Health check running instances

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

## Feature List Gate

The file `.harness/feature_list.json` is the PRD enforcement mechanism.

**Rules:**
- Every feature starts with `"passes": false`
- Only flip to `true` AFTER verifying each step listed in `"steps"`
- NEVER edit descriptions, remove features, or reorder priorities
- NEVER flip to `true` without running the verification steps
- JSON format is intentional — do not convert to Markdown
- Run `/features` to see current status and pick next feature to implement

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
