# Tier 2: Architecture Gates

> Status: **Skeleton** — not yet implemented. This README explains the concept for stakeholder alignment.

## What T2 Enforces

Fixed structural rules with configurable thresholds and escape hatches. Unlike T1 (which checks syntax-level quality), T2 checks *design-level* quality.

## Gate Categories

### T2.1 Import Boundaries
AST-enforced module dependency graph. Prevents modules from importing things they shouldn't.

- Configuration: `.harness/t2/import-rules.json`
- Example rule: `"backend/api" cannot import from "backend/workers"`
- Enforcement: static analysis of import statements
- Escape hatch: `# harness:allow-import` comment

### T2.2 God Files
Maximum file line threshold. Catches files that have grown too large and need splitting.

- Default threshold: 300 lines
- Configurable per-repo in `.harness/t2/thresholds.json`
- Excludes: `__init__.py`, generated files, migrations
- Escape hatch: `# harness:allow-large-file` at top of file

### T2.3 Golden Principles
Mandatory code patterns that every team agrees on:

| Principle | What it checks |
|-----------|---------------|
| No `print()` | Use structured logging (`logging.*` or `structlog.*`) |
| Type hints | All function signatures must have type annotations |
| No bare `except` | Must catch specific exceptions |
| Structured errors | Custom exception classes, not bare `raise Exception()` |

Configurable: teams can enable/disable individual principles.

## Enterprise Value

Same categories everywhere, thresholds per-repo. A new team joining the org gets the same T2 rules as everyone else — they just configure thresholds appropriate for their codebase maturity.

## Implementation References

These scripts on the `master` branch contain logic that will be adapted for T2:
- `scripts/check_imports.py` — import boundary checking
- `scripts/check_architecture.py` — architecture validation
- `scripts/check_golden_principles.py` — golden principle enforcement

## Planned Files

```
tiers/t2-architecture/
├── README.md           ← you are here
├── install.sh          (placeholder)
└── validate-t2.sh      (placeholder)
```
