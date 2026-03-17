#!/usr/bin/env bash
# validate.sh — THE UNIVERSAL GATE. Every line of code passes through here.
#
# Total gates: 21 (B1-B7 backend, F1-F7 frontend, I1-I2 infra, X1-X4 cross-stack, R1 ratchet)
#
# This is the ONLY way to declare code "ready." No exceptions. No shortcuts.
# Subagents, main agents, humans — everyone runs this before committing.
#
# It auto-detects what code exists and runs the appropriate gates.
# Adding a new module (frontend, backend, infra) doesn't require editing
# this script — it discovers what's present and validates it.
#
# Exit code: 0 = all pass, non-zero = at least one failure.
# NOTHING gets committed until this exits 0.

set -uo pipefail
# NOTE: No 'set -e' — we want to continue running all gates even if one fails.
# The check() function tracks pass/fail counts and we exit based on FAIL count at the end.

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

echo "═══════════════════════════════════════════════════"
echo " Universal Validation Gate"
echo " Every line of code passes through here."
echo "═══════════════════════════════════════════════════"
echo ""

# ═══════════════════════════════════════════════════
# PYTHON BACKEND GATES
# ═══════════════════════════════════════════════════

BACKEND_DIR="${REPO_ROOT}/backend"

if [ -d "$BACKEND_DIR" ] && { [ -f "$BACKEND_DIR/requirements.txt" ] || [ -f "$BACKEND_DIR/pyproject.toml" ]; }; then
    echo "── BACKEND (Python)"
    cd "$BACKEND_DIR"

    # Activate venv if exists
    if [ -d ".venv" ]; then
        source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate 2>/dev/null || true
    fi

    # Gate B1: Lint
    if command -v ruff &>/dev/null; then
        check "  [B1] Ruff lint" ruff check .
    elif command -v flake8 &>/dev/null; then
        check "  [B1] Flake8 lint" flake8 .
    else
        skip "  [B1] Lint" "no linter found (install ruff or flake8)"
    fi

    # Gate B2: Format
    if command -v ruff &>/dev/null; then
        check "  [B2] Ruff format" ruff format --check .
    elif command -v black &>/dev/null; then
        check "  [B2] Black format" black --check .
    else
        skip "  [B2] Format" "no formatter found (install ruff or black)"
    fi

    # Gate B3: Tests
    if [ -d "tests" ]; then
        check "  [B3] Pytest" python -m pytest tests/ -v --tb=short -q
    else
        skip "  [B3] Pytest" "no tests/ directory found"
    fi

    # Gate B4: Import boundaries
    if [ -f "${REPO_ROOT}/scripts/check_imports.py" ]; then
        check "  [B4] Import boundaries" python "${REPO_ROOT}/scripts/check_imports.py"
    else
        skip "  [B4] Import boundaries" "scripts/check_imports.py not found"
    fi

    # Gate B5: Golden principles
    if [ -f "${REPO_ROOT}/scripts/check_golden_principles.py" ]; then
        check "  [B5] Golden principles" python "${REPO_ROOT}/scripts/check_golden_principles.py"
    else
        skip "  [B5] Golden principles" "scripts/check_golden_principles.py not found"
    fi

    # Gate B6: Architecture invariants
    if [ -f "${REPO_ROOT}/scripts/check_architecture.py" ]; then
        check "  [B6] Architecture" python "${REPO_ROOT}/scripts/check_architecture.py"
    else
        skip "  [B6] Architecture" "scripts/check_architecture.py not found"
    fi

    # Gate B7: Type checking
    if command -v pyright &>/dev/null; then
        check "  [B7] Pyright type check" pyright
    elif command -v mypy &>/dev/null; then
        check "  [B7] Mypy type check" mypy .
    else
        skip "  [B7] Type check" "no type checker found (install pyright or mypy)"
    fi

    echo ""

# ═══════════════════════════════════════════════════
# NODE BACKEND GATES
# ═══════════════════════════════════════════════════

elif [ -d "$BACKEND_DIR" ] && [ -f "$BACKEND_DIR/package.json" ]; then
    echo "── BACKEND (Node.js)"
    cd "$BACKEND_DIR"

    if [ -d "node_modules" ]; then
        # Gate B1: Lint
        check "  [B1] ESLint" npx eslint . --max-warnings 0

        # Gate B2: Format
        check "  [B2] Prettier" npx prettier --check .

        # Gate B3: TypeScript
        check "  [B3] TypeScript" npx tsc --noEmit

        # Gate B4: Tests
        if grep -q '"test"' package.json 2>/dev/null; then
            check "  [B4] Tests" npm test -- --passWithNoTests
        else
            skip "  [B4] Tests" "no test script in package.json"
        fi

        # Gate B5: Import boundaries (if Python checker exists and is configured for node)
        if [ -f "${REPO_ROOT}/scripts/check_imports.py" ]; then
            check "  [B5] Import boundaries" python "${REPO_ROOT}/scripts/check_imports.py"
        else
            skip "  [B5] Import boundaries" "scripts/check_imports.py not found"
        fi
    else
        skip "BACKEND (Node.js)" "run 'cd backend && npm install' first"
    fi

    echo ""
else
    skip "BACKEND" "no backend/ directory with requirements.txt, pyproject.toml, or package.json"
    echo ""
fi

# ═══════════════════════════════════════════════════
# FRONTEND GATES
# ═══════════════════════════════════════════════════

FRONTEND_DIR="${REPO_ROOT}/frontend"

if [ -d "$FRONTEND_DIR" ] && [ -f "$FRONTEND_DIR/package.json" ]; then
    echo "── FRONTEND"
    cd "$FRONTEND_DIR"

    if [ -d "node_modules" ]; then
        # Gate F1: TypeScript
        check "  [F1] TypeScript" npx tsc --noEmit

        # Gate F2: ESLint
        check "  [F2] ESLint" npx eslint . --max-warnings 0

        # Gate F3: Prettier
        check "  [F3] Prettier" npx prettier --check "**/*.{ts,tsx,js,jsx}" 2>/dev/null || npx prettier --check .

        # Gate F4: Build (detect framework)
        if [ -f "next.config.js" ] || [ -f "next.config.ts" ] || [ -f "next.config.mjs" ]; then
            check "  [F4] Next.js build" npx next build
        elif [ -f "vite.config.ts" ] || [ -f "vite.config.js" ]; then
            check "  [F4] Vite build" npx vite build
        elif grep -q '"build"' package.json 2>/dev/null; then
            check "  [F4] Build" npm run build
        else
            skip "  [F4] Build" "no build config detected"
        fi

        # Gate F5: Frontend tests
        if [ -f "jest.config.ts" ] || [ -f "jest.config.js" ] || [ -f "vitest.config.ts" ] || grep -q '"test"' package.json 2>/dev/null; then
            check "  [F5] Frontend tests" npm test -- --passWithNoTests 2>/dev/null || true
        else
            skip "  [F5] Frontend tests" "no test config found"
        fi

        # Gate F6: UI legibility (if running)
        if [ "${RUN_UI:-}" = "true" ] || [ -d ".next" ] || [ -d "dist" ]; then
            if [ -f "${REPO_ROOT}/scripts/check_ui_legibility.sh" ]; then
                check "  [F6] UI legibility (Layer 5)" bash "${REPO_ROOT}/scripts/check_ui_legibility.sh"
            else
                skip "  [F6] UI legibility" "scripts/check_ui_legibility.sh not found"
            fi
        else
            skip "  [F6] UI legibility" "run with RUN_UI=true or after building"
        fi

        # Gate F7: Playwright browser tests (if Playwright installed)
        if command -v npx &>/dev/null && npx playwright --version &>/dev/null 2>&1; then
            if [ -f "${REPO_ROOT}/scripts/check_ui_playwright.sh" ]; then
                check "  [F7] Playwright browser tests (Layer 5)" bash "${REPO_ROOT}/scripts/check_ui_playwright.sh"
            else
                skip "  [F7] Playwright browser tests" "scripts/check_ui_playwright.sh not found"
            fi
        else
            skip "  [F7] Playwright browser tests" "playwright not installed — run 'npx playwright install chromium'"
        fi
    else
        skip "FRONTEND" "run 'cd frontend && npm install' first"
    fi

    echo ""
else
    skip "FRONTEND" "no frontend/ directory"
    echo ""
fi

# ═══════════════════════════════════════════════════
# INFRASTRUCTURE GATES
# ═══════════════════════════════════════════════════

TERRAFORM_DIR="${REPO_ROOT}/terraform"
INFRA_DIR="${REPO_ROOT}/infrastructure"

# Check for terraform (could be in terraform/ or infrastructure/)
TF_DIR=""
if [ -d "$TERRAFORM_DIR" ] && [ -f "$TERRAFORM_DIR/main.tf" ]; then
    TF_DIR="$TERRAFORM_DIR"
elif [ -d "$INFRA_DIR" ] && [ -f "$INFRA_DIR/main.tf" ]; then
    TF_DIR="$INFRA_DIR"
fi

if [ -n "$TF_DIR" ]; then
    echo "── INFRASTRUCTURE (Terraform)"

    if command -v terraform &>/dev/null; then
        check "  [I1] Terraform format" terraform -chdir="$TF_DIR" fmt -check -recursive
    else
        skip "  [I1] Terraform format" "terraform not installed"
    fi

    if [ -d "$TF_DIR/.terraform" ]; then
        check "  [I2] Terraform validate" terraform -chdir="$TF_DIR" validate
    else
        skip "  [I2] Terraform validate" "not initialized — run 'terraform init'"
    fi

    echo ""
elif [ -d "${REPO_ROOT}/pulumi" ] && [ -f "${REPO_ROOT}/pulumi/Pulumi.yaml" ]; then
    echo "── INFRASTRUCTURE (Pulumi)"

    if command -v pulumi &>/dev/null; then
        check "  [I1] Pulumi preview" pulumi preview --cwd "${REPO_ROOT}/pulumi" --non-interactive 2>/dev/null || true
    else
        skip "  [I1] Pulumi preview" "pulumi not installed"
    fi

    echo ""
else
    skip "INFRASTRUCTURE" "no terraform/ or pulumi/ directory"
    echo ""
fi

# ═══════════════════════════════════════════════════
# CROSS-STACK GATES
# ═══════════════════════════════════════════════════

echo "── CROSS-STACK"

# Gate X1: Documentation cross-references
check "  [X1] Doc cross-refs" bash -c "
    cd '${REPO_ROOT}'
    BROKEN=0
    if [ -f AGENTS.md ]; then
        for ref in \$(grep -oE 'docs/[a-zA-Z0-9/_.-]+\.md' AGENTS.md 2>/dev/null); do
            if [ ! -f \"\$ref\" ]; then
                echo \"    BROKEN: AGENTS.md references \$ref but file missing\"
                BROKEN=\$((BROKEN + 1))
            fi
        done
    fi
    [ \$BROKEN -eq 0 ]
"

# Gate X2: No secrets in repo
check "  [X2] No secrets" bash -c "
    FOUND=0
    for f in \$(find '${REPO_ROOT}' -name '*.py' -o -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.go' -o -name '*.rs' | grep -v node_modules | grep -v .venv | grep -v __pycache__ | grep -v target); do
        if grep -qE '(AIza[A-Za-z0-9_-]{35}|sk-[a-zA-Z0-9]{40,}|AKIA[A-Z0-9]{16}|BEGIN (RSA |EC )?PRIVATE KEY)' \"\$f\" 2>/dev/null; then
            echo \"    SECRET FOUND: \$f\"
            FOUND=\$((FOUND + 1))
        fi
    done
    [ \$FOUND -eq 0 ]
"

# Gate X3: E2E validation (if app is running locally)
if [ -f "${REPO_ROOT}/instance-metadata.json" ] || [ "${RUN_E2E:-}" = "true" ]; then
    if [ -f "${REPO_ROOT}/scripts/check_e2e_deployed.sh" ]; then
        BACKEND_URL=$(python3 -c "import json; print(json.load(open('${REPO_ROOT}/instance-metadata.json'))['backend_url'])" 2>/dev/null || echo "")
        if [ -n "$BACKEND_URL" ]; then
            check "  [X3] E2E validation (local)" bash "${REPO_ROOT}/scripts/check_e2e_deployed.sh" "$BACKEND_URL"
        else
            skip "  [X3] E2E validation (local)" "no backend_url in instance-metadata.json"
        fi
    else
        skip "  [X3] E2E validation (local)" "scripts/check_e2e_deployed.sh not found"
    fi
else
    skip "  [X3] E2E validation (local)" "no running instance — use RUN_E2E=true or boot_worktree.sh"
fi

# Gate X4: E2E deployed (if DEPLOYED_URL is set or reachable)
if [ -n "${DEPLOYED_URL:-}" ]; then
    if [ -f "${REPO_ROOT}/scripts/check_e2e_deployed.sh" ]; then
        check "  [X4] E2E deployed (Layer 7)" bash "${REPO_ROOT}/scripts/check_e2e_deployed.sh" "${DEPLOYED_URL}"
    else
        skip "  [X4] E2E deployed" "scripts/check_e2e_deployed.sh not found"
    fi
else
    skip "  [X4] E2E deployed (Layer 7)" "set DEPLOYED_URL to enable"
fi

echo ""

# Gate O1: Layer 6 — Observability health (if stack is running)
if curl -s http://localhost:8428/health &>/dev/null && curl -s http://localhost:9428/health &>/dev/null; then
    check "  [O1] Observability (Layer 6)" bash "${REPO_ROOT}/scripts/check_observability.sh"
else
    skip "  [O1] Observability (Layer 6)" "stack not running — docker compose -f docker-compose.observability.yml up -d"
fi

# Gate R1: Ratchet check (quality can only improve, never regress)
if [ -f "${REPO_ROOT}/scripts/ratchet.py" ]; then
    check "  [R1] Ratchet (quality baseline)" python "${REPO_ROOT}/scripts/ratchet.py"
else
    skip "  [R1] Ratchet" "scripts/ratchet.py not found"
fi

echo ""

# ═══════════════════════════════════════════════════
# RESULTS
# ═══════════════════════════════════════════════════

TOTAL=$((PASS + FAIL))
echo "═══════════════════════════════════════════════════"
echo " Results: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped (${TOTAL} total)"
echo "═══════════════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}VALIDATION FAILED — fix errors above before committing${NC}"
    echo ""
    echo "RULE: Nothing gets committed until this script exits 0."
    echo "      No exceptions. No shortcuts. Run this again after fixing."
    exit 1
else
    echo -e "${GREEN}ALL GATES PASSED — ready to commit${NC}"
    exit 0
fi
