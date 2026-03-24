#!/usr/bin/env bash
# Post-edit hook: fast project-specific checks on changed files.
# Two tiers: (1) standard linters, (2) project-specific gates.
#
# This hook is invoked by Claude Code after file edits.
# It provides real-time feedback — catches violations DURING development,
# not just at commit time. This closes the gap where subagents write code
# that passes ruff but violates project-specific rules (print(), os.environ, etc).

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

WARNINGS=0

# ── Tier 1: Standard linters (language-specific) ──────────────────────

# Check modified Python files with ruff (if available)
CHANGED_PY=$(git diff --name-only --diff-filter=M -- '*.py' 2>/dev/null)
if [ -n "$CHANGED_PY" ]; then
    if command -v ruff &>/dev/null; then
        ruff check $CHANGED_PY 2>/dev/null || { echo "WARNING: Lint issues found in changed Python files"; WARNINGS=$((WARNINGS+1)); }
    fi
fi

# Check modified TypeScript/JavaScript files with eslint (if available)
CHANGED_TS=$(git diff --name-only --diff-filter=M -- '*.ts' '*.tsx' '*.js' '*.jsx' 2>/dev/null)
if [ -n "$CHANGED_TS" ]; then
    if command -v npx &>/dev/null && [ -f "frontend/node_modules/.bin/eslint" ]; then
        npx eslint $CHANGED_TS --no-error-on-unmatched-pattern 2>/dev/null || { echo "WARNING: Lint issues found in changed TypeScript/JavaScript files"; WARNINGS=$((WARNINGS+1)); }
    fi
fi

# Check modified Terraform files (if available)
CHANGED_TF=$(git diff --name-only --diff-filter=M -- '*.tf' 2>/dev/null)
if [ -n "$CHANGED_TF" ]; then
    if command -v terraform &>/dev/null; then
        for f in $CHANGED_TF; do
            terraform fmt -check "$f" 2>/dev/null || { echo "WARNING: Terraform formatting issue in $f"; WARNINGS=$((WARNINGS+1)); }
        done
    fi
fi

# ── Tier 2: Project-specific gates (catch what linters miss) ──────────
# These run the custom checkers that enforce project rules like:
# - No print() in production code (golden principles)
# - No os.environ outside config/ (architecture)
# - Module import boundaries (dependency DAG)
# Each checker is optional — only runs if the script exists.

if [ -f "scripts/check_golden_principles.py" ]; then
    python scripts/check_golden_principles.py 2>/dev/null || { echo "WARNING: Golden principle violations detected — fix before committing"; WARNINGS=$((WARNINGS+1)); }
fi

if [ -f "scripts/check_architecture.py" ]; then
    python scripts/check_architecture.py 2>/dev/null || { echo "WARNING: Architecture violations detected — fix before committing"; WARNINGS=$((WARNINGS+1)); }
fi

if [ -f "scripts/check_imports.py" ]; then
    python scripts/check_imports.py 2>/dev/null || { echo "WARNING: Import boundary violations detected — fix before committing"; WARNINGS=$((WARNINGS+1)); }
fi

if [ $WARNINGS -gt 0 ]; then
    echo ""
    echo "⚠ $WARNINGS issue(s) found. Fix these BEFORE writing more code."
fi
