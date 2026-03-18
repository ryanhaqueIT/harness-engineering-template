# Harness Engineering Template

A tiered, incremental code quality framework for Python + Next.js repos. Install one shell command, get lint/format/typecheck/test gates that block bad commits — without touching your existing configs.

## Why This Exists

Most quality tooling falls into two traps:

1. **All-or-nothing frameworks** — require adopting an entire ecosystem (Nx, Turborepo, etc.) just to get linting. Teams that already have tooling won't switch.
2. **DIY shell scripts** — every team writes their own pre-commit hooks, their own CI lint step, their own "how to set up the repo" wiki page. Nothing is reusable across the org.

The harness sits in between: it detects what you have, fills gaps with org defaults, and enforces quality through a standard pre-commit hook. Teams with existing ruff/eslint configs keep them. Teams with nothing get sensible defaults.

## Architecture

Four tiers, installed independently, each building on the previous:

| Tier | Name | Status | What It Enforces |
|------|------|--------|-----------------|
| **T1** | Code Quality | **Functional** | Lint, format, typecheck, unit tests |
| **T2** | Architecture | Design only | Import boundaries, file size limits, code principles |
| **T3** | App Testing | Design only | Boot contract, API smoke tests, UI legibility, E2E |
| **T4** | Product Verification | Design only | Feature completeness verified against PRD |

```
T1 (Code Quality)           ← every repo, day one
 └─► T2 (Architecture)      ← repos passing T1 consistently
      └─► T3 (App Testing)  ← repos with APIs or UIs
           └─► T4 (Product) ← product-critical repos
```

Tiers are independent — install T1 without T2. The dependency is conceptual: T2 rules assume T1 quality, T3 needs a running app, T4 needs T3's boot contract.

## Quick Start

```bash
# Clone the template
git clone <this-repo-url> harness-engineering-template

# Install T1 into any Python or Next.js repo
bash harness-engineering-template/tiers/t1-code-quality/install.sh /path/to/your-repo
```

That's it. The install script:

1. **Detects stacks** — finds Python (pyproject.toml, setup.py, *.py) and/or Next.js (package.json)
2. **Installs tools** — ruff, pyright, eslint, prettier, typescript (only what's missing)
3. **Copies org configs** — only where the repo doesn't already have its own
4. **Sets up pre-commit hook** — symlinks `.git/hooks/pre-commit` to `.harness/hooks/pre-commit`
5. **Baselines the ratchet** — counts current violations so future commits can't make things worse

### After install

```bash
# Just commit normally — the hook runs automatically
git commit -m "my change"
# → pre-commit fires → validate-t1.sh → blocks if any gate fails

# Run gates manually
bash .harness/validate-t1.sh

# Check ratchet status
python3 .harness/ratchet-t1.py

# Show current baseline
python3 .harness/ratchet-t1.py --show
```

## What T1 Actually Checks

| Gate | Python | Next.js |
|------|--------|---------|
| **T1.1 Lint** | `ruff check .` | `npx eslint .` |
| **T1.2 Format** | `ruff format --check .` | `npx prettier --check .` |
| **T1.3 Typecheck** | `pyright` | `npx tsc --noEmit` |
| **T1.4 Tests** | Auto-detected (pytest) | Auto-detected (vitest/jest/npm test) |

Gates for missing stacks are skipped automatically. A Python-only repo won't see Next.js gates.

### Test detection cascades

The harness doesn't hardcode test commands. It detects them:

**Python:** `pyproject.toml [tool.pytest]` → `pytest.ini` → `setup.cfg [tool:pytest]` → `tests/` dir → skip

**Next.js:** `package.json scripts.test` → `vitest.config.*` → `jest.config.*` → skip

### The ratchet

The ratchet tracks 4 numbers: `lint_errors`, `format_errors`, `type_errors`, `test_failures`.

On first run, it snapshots your current counts as the baseline. On every subsequent run:
- **Violations go up** → FAIL (you made it worse)
- **Violations stay same** → PASS
- **Violations go down** → PASS + update baseline (improvement is locked in)

This means teams adopt at their own pace. A repo with 200 lint errors doesn't have to fix them all — it just can't add error 201.

## Install Matrix

The install script uses a 2x2 matrix for every tool:

| | Tool Missing | Tool Present |
|---|---|---|
| **Config Missing** | Install tool + copy org default | Copy org default |
| **Config Present** | Install tool, leave config alone | Do nothing |

Your existing configs are never overwritten. The harness fills gaps, it doesn't take over.

## AI Coding Tool Compatibility

The harness works with any tool that commits through git, because enforcement happens at the git hook layer.

| Tool | How it works | What happens |
|------|-------------|--------------|
| **Claude Code** | Commits trigger `.git/hooks/pre-commit` | Gates run before commit is created. Claude sees failures and can auto-fix. The `post-edit.sh` hook can also be wired into Claude Code's hook system for instant lint feedback on every file save. |
| **GitHub Copilot** (in VS Code/JetBrains) | Copilot suggests code, you commit | Pre-commit hook catches any quality issues Copilot introduced. Copilot Chat can read gate output to help fix. |
| **Cursor / Windsurf** | AI edits files, commits through git | Same pre-commit enforcement. These tools see the hook failure in their terminal and can iterate. |
| **OpenCode / RooCode** | Terminal-based agents that use git | Pre-commit hook blocks bad commits. Agent sees the error output and can fix-and-retry. |
| **Any CI system** | Run `bash .harness/validate-t1.sh` as a CI step | Same gates, same output, same exit codes. CI catches what local hooks missed. |

The key insight: **the harness doesn't care who writes the code.** Human, AI, or a mix — the pre-commit hook runs the same gates. AI tools that can read terminal output (Claude Code, OpenCode, RooCode, Cursor) will see the failure message and can auto-fix.

For Claude Code specifically, `post-edit.sh` provides a tighter feedback loop — lint runs after every file edit, not just at commit time. This means Claude sees issues within seconds of writing them instead of at commit time.

Future tiers will include a **project memory architecture** — a structured `docs/` layout that gives AI agents navigable context about the codebase (architecture, conventions, decisions, domain boundaries). Instead of every agent re-discovering the project from scratch, memory files act as a routing table so agents load only the context relevant to their current task. This reduces hallucination, keeps AI-generated code consistent with project conventions, and means fewer gate failures in the first place.

## Day-to-Day

After install, the harness is invisible. Developers commit normally — the pre-commit hook runs, blocks if something fails, and shows exactly which gate broke. Tech leads can check any repo's ratchet baseline to track improvement over time. Platform teams install T1 across repos in bulk — same gates everywhere, each repo keeps its own configs and baselines.

## What Gets Installed in Your Repo

```
your-repo/
├── .harness/
│   ├── validate-t1.sh          # The gate runner
│   ├── ratchet-t1.py           # The ratchet (baseline tracking)
│   ├── t1-baseline.json        # Current violation counts (gitignored)
│   ├── manifest.json           # Which tiers are installed
│   └── hooks/
│       ├── pre-commit          # Wrapper that calls validate-t1.sh
│       └── post-edit.sh        # Quick lint for AI coding tools
├── .git/hooks/
│   └── pre-commit → ../../.harness/hooks/pre-commit  (symlink)
├── ruff.toml                   # Only if you didn't have one
├── pyrightconfig.json          # Only if you didn't have one
├── eslint.config.mjs           # Only if you didn't have one (Next.js)
├── prettier.config.mjs         # Only if you didn't have one (Next.js)
└── tsconfig.json               # Only if you didn't have one (Next.js)
```

## Escape Hatches

- **Skip the hook once:** `git commit --no-verify` (use sparingly)
- **Customize tool configs:** edit the copied config files (ruff.toml, eslint.config.mjs, etc.) — the harness uses whatever config is in your repo
- **Exclude directories from scanning:** set `RUFF_EXCLUDES` and `ESLINT_EXCLUDES` in `validate-t1.sh`
- **Reset the ratchet baseline:** delete `.harness/t1-baseline.json` and run `python3 .harness/ratchet-t1.py` to re-baseline
- **Uninstall completely:** remove `.harness/`, the config files it added, and `.git/hooks/pre-commit`

## Tier Roadmap

### T2: Architecture (design only)

Structural rules with configurable thresholds. Import boundary enforcement (which modules can import what), god file detection (files over N lines), and golden principles (no print(), structured logging, type hints required, no bare except).

T2 also introduces **agent memory** — a file-based context architecture (`docs/` with INDEX.md, architecture.md, conventions.md, decisions.md) that AI coding tools can read to understand the project without scanning every file. Same categories org-wide, thresholds per-repo. → [T2 Design Doc](tiers/t2-architecture/README.md)

### T3: App Testing (design only)

Standardized app boot via a `boot.sh` contract. Every repo provides a script that starts the app and writes `instance-metadata.json` with connection details. This enables automated API smoke tests, UI legibility checks, and E2E critical path tests — all without knowing how each team's app starts.

→ [T3 Design Doc](tiers/t3-app-testing/README.md)

### T4: Product Verification (design only)

Bridges the gap between PRD+ERD and code. The PRD (Product Requirements Document) defines what to build — features, user flows, acceptance criteria. The ERD (Engineering Requirements Document) defines how to build it — architecture decisions, API contracts, data models, infrastructure, non-functional requirements. Together they're the complete specification. Requirements are extracted into a structured `feature_list.json` with immutable verification steps. The harness mechanically executes each step against the running app and reports which features pass, which fail, and which haven't been tested.

→ [T4 Design Doc](tiers/t4-product-verification/README.md)

## Orchestrator

When multiple tiers are installed, the orchestrator runs them in order:

```bash
bash orchestrator/validate-all.sh              # stop on first failure
bash orchestrator/validate-all.sh --continue   # run all, report at end
```

It reads `.harness/manifest.json` to discover installed tiers.

## Prior Art

The v0 monolithic harness (22 gates, 23 scripts, 4 playbooks) is preserved on the `master` branch. This tiered restructure replaces it with something teams can actually adopt incrementally.
