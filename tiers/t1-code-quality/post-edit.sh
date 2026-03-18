#!/usr/bin/env bash
# post-edit.sh — Quick lint on changed files after edits.
# Runs fast checks (< 2 seconds) to give immediate feedback.
# Designed for use as a Claude Code post-edit hook or standalone.

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

# Check modified Python files with ruff
CHANGED_PY=$(git diff --name-only --diff-filter=M -- '*.py' 2>/dev/null)
if [ -n "$CHANGED_PY" ]; then
    if command -v ruff &>/dev/null; then
        timeout 2 ruff check $CHANGED_PY 2>/dev/null || echo "WARNING: Lint issues in changed Python files"
    fi
fi

# Check modified TypeScript/JavaScript files with eslint
CHANGED_TS=$(git diff --name-only --diff-filter=M -- '*.ts' '*.tsx' '*.js' '*.jsx' 2>/dev/null)
if [ -n "$CHANGED_TS" ]; then
    if command -v npx &>/dev/null && [ -d "$REPO_ROOT/node_modules/.bin" ]; then
        timeout 2 npx eslint $CHANGED_TS --no-error-on-unmatched-pattern 2>/dev/null || echo "WARNING: Lint issues in changed JS/TS files"
    fi
fi
