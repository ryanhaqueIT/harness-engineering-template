# Harness Engineering Template

> A reusable framework for AI-first software development. Clone, run `setup.sh`, and get a fully instrumented project that any AI coding agent can navigate, validate, and ship in.

## What Is Harness Engineering?

Harness engineering is the discipline of designing environments, constraints, and feedback loops that enable AI coding agents to write reliable software at scale. Instead of writing code directly, engineers design the system that makes agents write *good* code: structured documentation, mechanical enforcement of architecture, automated quality gates, and progressive context disclosure.

The fundamental insight is that AI agents replicate patterns already present in a repository -- including bad ones. Left unchecked, this leads to architectural drift, copy-paste propagation, and compounding entropy. The harness prevents this by encoding invariants into scripts, enforcing them in CI, and making the running application visible to agents for self-validation. The investment is in the harness, not the code. The code is the dividend.

## The 7-Layer Testing Pyramid

Harness engineering structures validation into seven layers, each catching a different class of defect. Lower layers run fastest and catch the most common issues. Higher layers provide deeper confidence.

| Layer | Name | What It Checks | Tools |
|-------|------|----------------|-------|
| **1** | Static Analysis | Lint errors, formatting, syntax | ruff, eslint, prettier, tsc |
| **2** | Unit Tests | Individual functions and modules | pytest, jest, vitest |
| **3** | Import Boundaries | Module dependency rules (no circular imports, no cross-layer access) | `check_imports.py` (AST-based) |
| **4** | Golden Principles | No print(), no secrets, type hints, no bare except | `check_golden_principles.py` (AST-based) |
| **5** | Architecture Invariants | No God files, naming conventions, test mirrors, DB access rules | `check_architecture.py` (AST-based) |
| **6** | Application Legibility | Pages render, DOM content present, no console errors, static assets load | `check_ui_legibility.sh`, Playwright |
| **7** | E2E Deployed Validation | Health endpoints, API schemas, response headers, CORS | `check_e2e_deployed.sh` |

Every layer produces actionable error messages with file paths, line numbers, and fix instructions so agents can self-repair without human intervention.

## How to Use This Template

### Quick Start

```bash
git clone https://github.com/your-org/harness-engineering-template.git my-project
cd my-project
bash setup.sh
```

The interactive setup will ask you:
1. **Project name** (e.g., "Acme Platform")
2. **Backend language** (python / node)
3. **Frontend framework** (next / react / vue / none)
4. **Infrastructure tool** (terraform / pulumi / none)

It then generates your `AGENTS.md`, configures `check_imports.py` with correct module rules, creates the appropriate CI workflow, and makes `validate.sh` ready to run.

### After Setup

```bash
# Validate everything (run before every commit)
./scripts/validate.sh

# Boot both backend + frontend on dynamic ports
./scripts/boot_worktree.sh

# Run E2E against deployed instance
./scripts/check_e2e_deployed.sh https://your-app.example.com
```

### Manual Setup

If you prefer not to use the interactive setup:

1. Copy this template into your project root
2. Edit `AGENTS.md` -- replace all `{{PLACEHOLDER}}` values with your project specifics
3. Edit `scripts/check_imports.py` -- define your module dependency RULES dict
4. Edit `scripts/check_architecture.py` -- configure your DB library name and AI library name
5. Run `./scripts/validate.sh` to verify everything works

## The 5-Phase Lifecycle

### Phase 1: Scaffold
Set up project structure, install dependencies, configure CI. The harness validates that the skeleton compiles, lints, and passes empty test suites.

### Phase 2: Specify
Write specs in `docs/product-specs/`, create ExecPlans in `docs/exec-plans/active/`, document design decisions in `docs/design-docs/`. The harness validates cross-references and prevents orphan documentation.

### Phase 3: Implement
Agents read the active ExecPlan, implement the feature, and run `validate.sh` after every change. The Ralph Wiggum Loop: implement, validate, fix, re-validate until exit 0.

### Phase 4: Validate
Run all 7 layers. Boot the app with `boot_worktree.sh`. Run `check_ui_legibility.sh` for frontend smoke tests. Run `check_e2e_deployed.sh` against the deployed instance. Nothing merges until all gates pass.

### Phase 5: Maintain
Weekly doc-gardening (`.github/workflows/doc-gardening.yml`) catches orphan docs and broken cross-references. Daily quality scans (`.github/workflows/quality-scan.yml`) track code metrics and gate drift. Tech debt is tracked in `docs/exec-plans/tech-debt-tracker.md`.

## Repository Structure

```
harness-engineering-template/
  AGENTS.md               # Entry point for all AI agents (~150 lines)
  PLANS.md                # ExecPlan template and rules
  README.md               # This file
  setup.sh                # Interactive project setup
  docs/
    QUALITY_SCORE.md      # Grading rubric (code, tests, architecture, security, reliability)
    PRODUCT_SENSE.md      # Product beliefs and decision framework
    SECURITY.md           # Auth, secrets, data protection, API security
    RELIABILITY.md        # Logging, errors, timeouts, idempotency, degradation
    DESIGN.md             # Design system documentation template
    FRONTEND.md           # Frontend conventions template
    design-docs/
      core-beliefs.md     # Locked technical beliefs
    exec-plans/
      active/             # In-progress execution plans
      completed/          # Finished execution plans
      tech-debt-tracker.md # Known technical debt
    generated/            # Auto-generated docs (DB schema, API docs)
    product-specs/        # Feature specifications
    references/           # External API docs formatted for LLMs
  scripts/
    validate.sh           # THE UNIVERSAL GATE
    check_imports.py      # Module dependency boundary enforcement
    check_golden_principles.py # No print, no secrets, type hints, no bare except
    check_architecture.py # God files, naming, test mirrors, access rules
    check_ui_legibility.sh # Frontend DOM/content smoke tests
    check_e2e_deployed.sh # E2E against deployed instance
    boot_worktree.sh      # Per-worktree app booting with dynamic ports
    setup.sh              # One-command harness initialization
  .github/workflows/
    ci.yml                # CI pipeline (lint, test, structural checks)
    doc-gardening.yml     # Weekly orphan/cross-ref scan
    quality-scan.yml      # Daily quality dashboard
```

## Credits

This methodology is based on [OpenAI's "Harness engineering: leveraging Codex in an agent-first world"](https://openai.com/index/harness-engineering/) (February 2026, Ryan Lopopolo) and battle-tested across multiple production AI agent platforms.

## License

MIT
