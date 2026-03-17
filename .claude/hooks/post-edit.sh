#!/usr/bin/env bash
# Post-edit hook: quick lint check on changed files.
# Only runs ruff check on modified Python files (fast, < 2 seconds).
#
# This hook is invoked by Claude Code after file edits.
# It provides fast feedback without running the full validation gate.

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Check modified Python files with ruff (if available)
CHANGED_PY=$(git diff --name-only --diff-filter=M -- '*.py' 2>/dev/null)
if [ -n "$CHANGED_PY" ]; then
    if command -v ruff &>/dev/null; then
        ruff check $CHANGED_PY 2>/dev/null || echo "WARNING: Lint issues found in changed Python files"
    fi
fi

# Check modified TypeScript/JavaScript files with eslint (if available)
CHANGED_TS=$(git diff --name-only --diff-filter=M -- '*.ts' '*.tsx' '*.js' '*.jsx' 2>/dev/null)
if [ -n "$CHANGED_TS" ]; then
    if command -v npx &>/dev/null && [ -f "frontend/node_modules/.bin/eslint" ]; then
        npx eslint $CHANGED_TS --no-error-on-unmatched-pattern 2>/dev/null || echo "WARNING: Lint issues found in changed TypeScript/JavaScript files"
    fi
fi

# Check modified Terraform files (if available)
CHANGED_TF=$(git diff --name-only --diff-filter=M -- '*.tf' 2>/dev/null)
if [ -n "$CHANGED_TF" ]; then
    if command -v terraform &>/dev/null; then
        for f in $CHANGED_TF; do
            terraform fmt -check "$f" 2>/dev/null || echo "WARNING: Terraform formatting issue in $f"
        done
    fi
fi
