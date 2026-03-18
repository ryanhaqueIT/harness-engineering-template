#!/usr/bin/env bash
# validate-t1.sh — Tier 1: Code Quality Gates
#
# Checks: lint, format, typecheck, tests for Python and Next.js
# Auto-detects which stacks are present and skips absent ones.
#
# Exit code: 0 = all run gates pass, non-zero = at least one failure.

set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

PASS=0
FAIL=0
SKIP=0

REPO_ROOT="$(git rev-parse --show-toplevel)"

check() {
    local name="$1"
    shift
    echo "── $name"
    if "$@" 2>&1; then
        echo -e "   ${GREEN}✓ PASS${NC}"
        ((PASS++))
    else
        echo -e "   ${RED}✗ FAIL${NC}"
        ((FAIL++))
    fi
}

skip() {
    echo -e "── $1 ${YELLOW}(skipped — $2)${NC}"
    ((SKIP++))
}

# ═══════════════════════════════════════════════════
# Stack detection
# ═══════════════════════════════════════════════════

detect_stack() {
    # Placeholder: if repo analyzer output exists, use it
    if [ -n "${REPO_ANALYZER_OUTPUT:-}" ] && [ -f "$REPO_ANALYZER_OUTPUT" ]; then
        echo "  Using repo analyzer output: $REPO_ANALYZER_OUTPUT"
        return
    fi

    # Fallback: detect by file presence
    HAS_PYTHON=false
    HAS_NEXTJS=false

    if [ -f "$REPO_ROOT/pyproject.toml" ] || [ -f "$REPO_ROOT/setup.py" ] || \
       find "$REPO_ROOT" -maxdepth 3 -name "*.py" -not -path "*/.venv/*" -not -path "*/node_modules/*" -not -path "*/.harness/*" | head -1 | grep -q .; then
        HAS_PYTHON=true
    fi

    if [ -f "$REPO_ROOT/package.json" ]; then
        HAS_NEXTJS=true
    fi
}

# ═══════════════════════════════════════════════════
# Test command detection
# ═══════════════════════════════════════════════════

detect_python_test_cmd() {
    # Cascade: pyproject.toml [tool.pytest] → pytest.ini → setup.cfg [tool:pytest] → tests/ dir → skip
    if [ -f "$REPO_ROOT/pyproject.toml" ] && grep -q '\[tool\.pytest' "$REPO_ROOT/pyproject.toml" 2>/dev/null; then
        echo "python3 -m pytest"
        return
    fi
    if [ -f "$REPO_ROOT/pytest.ini" ]; then
        echo "python3 -m pytest"
        return
    fi
    if [ -f "$REPO_ROOT/setup.cfg" ] && grep -q '\[tool:pytest\]' "$REPO_ROOT/setup.cfg" 2>/dev/null; then
        echo "python3 -m pytest"
        return
    fi
    if [ -d "$REPO_ROOT/tests" ]; then
        echo "python3 -m pytest"
        return
    fi
    echo ""
}

detect_nextjs_test_cmd() {
    # Cascade: package.json scripts.test → vitest.config → jest.config → skip
    if [ -f "$REPO_ROOT/package.json" ]; then
        # Check if there's a "test" script that isn't the default "no test specified"
        local test_script
        test_script=$(python3 -c "
import json, sys
try:
    pkg = json.load(open('$REPO_ROOT/package.json'))
    t = pkg.get('scripts', {}).get('test', '')
    if t and 'no test specified' not in t:
        print(t)
except: pass
" 2>/dev/null)
        if [ -n "$test_script" ]; then
            echo "npm test"
            return
        fi
    fi
    # Check for vitest config
    if ls "$REPO_ROOT"/vitest.config.* 2>/dev/null | head -1 | grep -q .; then
        echo "npx vitest run"
        return
    fi
    # Check for jest config
    if ls "$REPO_ROOT"/jest.config.* 2>/dev/null | head -1 | grep -q .; then
        echo "npx jest"
        return
    fi
    echo ""
}

# ═══════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════

echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
echo -e "${BOLD} Tier 1: Code Quality Gates${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
echo ""

detect_stack

echo -e "  Python: ${HAS_PYTHON}"
echo -e "  Next.js: ${HAS_NEXTJS}"
echo ""

# ─── Exclude patterns for lint/format ─────────────
# TODO(human): Define the exclude patterns for ruff and eslint.
# These prevent harness tooling and generated dirs from polluting gate results.
# Ruff uses --extend-exclude, eslint uses --ignore-pattern.
# Example: RUFF_EXCLUDES="--extend-exclude .harness,.venv"
#          ESLINT_EXCLUDES="--ignore-pattern .harness/"
RUFF_EXCLUDES=""
ESLINT_EXCLUDES=""

# ─── Python gates ─────────────────────────────────

if [ "$HAS_PYTHON" = true ]; then
    echo -e "${BOLD}── Python ──────────────────────────────────────${NC}"

    # T1.1 Lint (Python)
    if command -v ruff &>/dev/null; then
        check "T1.1 Lint (ruff)" ruff check $RUFF_EXCLUDES "$REPO_ROOT"
    else
        skip "T1.1 Lint (ruff)" "ruff not installed"
    fi

    # T1.2 Format (Python)
    if command -v ruff &>/dev/null; then
        check "T1.2 Format (ruff)" ruff format --check $RUFF_EXCLUDES "$REPO_ROOT"
    else
        skip "T1.2 Format (ruff)" "ruff not installed"
    fi

    # T1.3 Typecheck (Python)
    if command -v pyright &>/dev/null; then
        check "T1.3 Typecheck (pyright)" pyright "$REPO_ROOT"
    else
        skip "T1.3 Typecheck (pyright)" "pyright not installed"
    fi

    # T1.4 Tests (Python)
    PY_TEST_CMD=$(detect_python_test_cmd)
    if [ -n "$PY_TEST_CMD" ]; then
        check "T1.4 Tests (Python)" $PY_TEST_CMD
    else
        skip "T1.4 Tests (Python)" "no test config found"
    fi

    echo ""
fi

# ─── Next.js gates ────────────────────────────────

if [ "$HAS_NEXTJS" = true ]; then
    echo -e "${BOLD}── Next.js ─────────────────────────────────────${NC}"

    # T1.1 Lint (Next.js)
    if command -v npx &>/dev/null && [ -d "$REPO_ROOT/node_modules" ]; then
        check "T1.1 Lint (eslint)" npx eslint "$REPO_ROOT" --no-error-on-unmatched-pattern $ESLINT_EXCLUDES
    else
        skip "T1.1 Lint (eslint)" "eslint not available"
    fi

    # T1.2 Format (Next.js)
    if command -v npx &>/dev/null && [ -d "$REPO_ROOT/node_modules" ]; then
        check "T1.2 Format (prettier)" npx prettier --check "$REPO_ROOT" --ignore-unknown
    else
        skip "T1.2 Format (prettier)" "prettier not available"
    fi

    # T1.3 Typecheck (Next.js)
    if command -v npx &>/dev/null && [ -f "$REPO_ROOT/tsconfig.json" ]; then
        check "T1.3 Typecheck (tsc)" npx tsc --noEmit
    else
        skip "T1.3 Typecheck (tsc)" "tsconfig.json not found"
    fi

    # T1.4 Tests (Next.js)
    JS_TEST_CMD=$(detect_nextjs_test_cmd)
    if [ -n "$JS_TEST_CMD" ]; then
        check "T1.4 Tests (Next.js)" $JS_TEST_CMD
    else
        skip "T1.4 Tests (Next.js)" "no test config found"
    fi

    echo ""
fi

# ─── No stacks detected ──────────────────────────

if [ "$HAS_PYTHON" = false ] && [ "$HAS_NEXTJS" = false ]; then
    echo -e "  ${YELLOW}No Python or Next.js code detected. Nothing to validate.${NC}"
    echo ""
fi

# ─── Summary ──────────────────────────────────────

echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
echo -e " Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}, ${YELLOW}${SKIP} skipped${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
