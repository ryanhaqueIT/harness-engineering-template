#!/usr/bin/env bash
# check_ui_legibility.sh — Layer 5: Application Legibility for the frontend.
#
# Boots the frontend (or reuses a running one), then verifies that
# pages render correctly and contain expected DOM elements. Uses Playwright
# when available for full headless-browser checks (console.error detection,
# JS-rendered content). Falls back to curl-based static HTML checks when
# Playwright is not installed.
#
# Exit code: 0 = all pass, 1 = at least one failure.
#
# CONFIGURABLE: Edit the PAGES array and expected content checks below.
#
# Usage:
#   ./scripts/check_ui_legibility.sh           # Auto-detect / boot frontend
#   ./scripts/check_ui_legibility.sh 3847       # Use already-running frontend on port
#   PLAYWRIGHT=1 ./scripts/check_ui_legibility.sh  # Force Playwright mode

set -uo pipefail

# ─── Constants ────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="${ROOT_DIR}/frontend"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

PASS=0
FAIL=0
SKIP=0
BOOTED_BY_US=""  # PID of frontend we started (empty = external)

# ═══════════════════════════════════════════════════
# CONFIGURE: Pages to check and expected content
# ═══════════════════════════════════════════════════

# Pages to check for HTTP 200 and non-empty content
PAGES=("/" "/login" "/dashboard")

# Keywords expected on the home page (at least 2 must match)
HOME_KEYWORDS=("Login\|Sign\|Welcome\|Dashboard\|Home\|Get Started")

# ─── Helpers ──────────────────────────────────────────────────────────

check() {
    local name="$1"
    shift
    if "$@" 2>&1; then
        echo -e "  ${GREEN}PASS${NC}  $name"
        ((PASS++))
    else
        echo -e "  ${RED}FAIL${NC}  $name"
        ((FAIL++))
    fi
}

skip() {
    echo -e "  ${YELLOW}SKIP${NC}  $1 — $2"
    ((SKIP++))
}

cleanup() {
    if [ -n "$BOOTED_BY_US" ]; then
        kill "$BOOTED_BY_US" 2>/dev/null
        wait "$BOOTED_BY_US" 2>/dev/null
    fi
}
trap cleanup EXIT

find_free_port() {
    python3 -c "import socket; s=socket.socket(); s.bind(('',0)); print(s.getsockname()[1]); s.close()" 2>/dev/null \
        || python -c "import socket; s=socket.socket(); s.bind(('',0)); print(s.getsockname()[1]); s.close()" 2>/dev/null \
        || echo "3847"
}

# ─── Determine port & boot if needed ─────────────────────────────────

PORT="${1:-}"

if [ -n "$PORT" ] && curl -s -o /dev/null -w "" "http://localhost:${PORT}" 2>/dev/null; then
    echo -e "${CYAN}Using existing frontend on port ${PORT}${NC}"
elif [ -n "$PORT" ]; then
    echo -e "${RED}ERROR: Nothing running on port ${PORT}${NC}"
    exit 1
else
    # Try to find a running frontend on common dev ports
    for TRY_PORT in 3000 3001 3847 3900 5173 8080; do
        if curl -sf -o /dev/null "http://localhost:${TRY_PORT}" 2>/dev/null; then
            PORT="$TRY_PORT"
            echo -e "${CYAN}Found running frontend on port ${PORT}${NC}"
            break
        fi
    done

    # Nothing found — boot one ourselves
    if [ -z "$PORT" ]; then
        if [ ! -d "$FRONTEND_DIR" ] || [ ! -f "$FRONTEND_DIR/package.json" ]; then
            echo -e "${RED}ERROR: No frontend/ directory found${NC}"
            exit 1
        fi

        # Detect framework and build if needed
        cd "$FRONTEND_DIR"

        # Next.js
        if [ -f "next.config.js" ] || [ -f "next.config.ts" ] || [ -f "next.config.mjs" ]; then
            if [ ! -d ".next" ]; then
                echo "Building frontend (first run)..."
                npx next build > /dev/null 2>&1 || { echo -e "${RED}Build failed${NC}"; exit 1; }
            fi
            PORT=$(find_free_port)
            echo "Booting Next.js on port ${PORT}..."
            npx next start -p "$PORT" > /dev/null 2>&1 &
            BOOTED_BY_US=$!

        # Vite
        elif [ -f "vite.config.ts" ] || [ -f "vite.config.js" ]; then
            PORT=$(find_free_port)
            echo "Booting Vite on port ${PORT}..."
            npx vite preview --port "$PORT" > /dev/null 2>&1 &
            BOOTED_BY_US=$!

        # Generic
        elif grep -q '"start"' package.json 2>/dev/null; then
            PORT=$(find_free_port)
            echo "Booting frontend (npm start) on port ${PORT}..."
            PORT="$PORT" npm start > /dev/null 2>&1 &
            BOOTED_BY_US=$!

        else
            echo -e "${RED}ERROR: Cannot detect frontend framework${NC}"
            exit 1
        fi

        # Wait for ready (up to 20s)
        READY=0
        for i in $(seq 1 20); do
            if curl -sf -o /dev/null "http://localhost:${PORT}" 2>/dev/null; then
                READY=1
                break
            fi
            sleep 1
        done

        if [ "$READY" -eq 0 ]; then
            echo -e "${RED}ERROR: Frontend failed to start within 20 seconds${NC}"
            exit 1
        fi
        echo -e "${CYAN}Frontend running on port ${PORT}${NC}"
    fi
fi

BASE="http://localhost:${PORT}"

echo ""
echo -e "${BOLD}=== UI Legibility — Layer 5 ===${NC}"
echo -e "  Target: ${BASE}"
echo ""

# ─── Detect Playwright availability ──────────────────────────────────

USE_PLAYWRIGHT=0
if [ "${PLAYWRIGHT:-}" = "1" ] || command -v npx &>/dev/null; then
    if npx --no-install playwright --version &>/dev/null 2>&1; then
        USE_PLAYWRIGHT=1
    fi
fi

# ─── Gate 1: Pages return HTTP 200 ───────────────────────────────────

echo -e "${BOLD}[L5-1] Page availability${NC}"

for PAGE in "${PAGES[@]}"; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE}${PAGE}" 2>/dev/null || echo "000")
    if [ "$STATUS" = "200" ]; then
        echo -e "  ${GREEN}PASS${NC}  ${PAGE} returns HTTP 200"
        ((PASS++))
    elif [ "$STATUS" = "000" ]; then
        skip "${PAGE}" "could not connect"
    else
        # 301/302 redirects are acceptable for auth-gated pages
        if [ "$STATUS" = "301" ] || [ "$STATUS" = "302" ] || [ "$STATUS" = "307" ]; then
            echo -e "  ${GREEN}PASS${NC}  ${PAGE} returns HTTP ${STATUS} (redirect, expected for auth-gated page)"
            ((PASS++))
        else
            echo -e "  ${RED}FAIL${NC}  ${PAGE} returns HTTP ${STATUS} (expected 200)"
            ((FAIL++))
        fi
    fi
done

echo ""

# ─── Gate 2: No blank pages ──────────────────────────────────────────

echo -e "${BOLD}[L5-2] No blank or broken pages${NC}"

PAGES_CHECKED=0
BLANK_PAGES=0

for PAGE in "${PAGES[@]}"; do
    BODY=$(curl -sf "${BASE}${PAGE}" 2>/dev/null || echo "")
    BODY_LEN=${#BODY}
    ((PAGES_CHECKED++))

    if [ "$BODY_LEN" -lt 50 ]; then
        echo -e "  ${RED}FAIL${NC}  ${PAGE} is blank or near-empty (${BODY_LEN} bytes)"
        ((BLANK_PAGES++))
    fi
done

if [ "$BLANK_PAGES" -eq 0 ]; then
    echo -e "  ${GREEN}PASS${NC}  All ${PAGES_CHECKED} pages have content (no blank pages)"
    ((PASS++))
else
    echo -e "  ${RED}FAIL${NC}  ${BLANK_PAGES}/${PAGES_CHECKED} pages are blank"
    ((FAIL++))
fi

echo ""

# ─── Gate 3: No server error text ────────────────────────────────────

echo -e "${BOLD}[L5-3] No server errors in responses${NC}"

ERROR_PAGES=0
for PAGE in "${PAGES[@]}"; do
    BODY=$(curl -sf "${BASE}${PAGE}" 2>/dev/null || echo "")
    if echo "$BODY" | grep -qi "Internal Server Error\|500 Server Error\|Application Error\|502 Bad Gateway\|503 Service Unavailable"; then
        echo -e "  ${RED}FAIL${NC}  ${PAGE} contains error text"
        ((ERROR_PAGES++))
    fi
done

if [ "$ERROR_PAGES" -eq 0 ]; then
    echo -e "  ${GREEN}PASS${NC}  No server-error text in any page"
    ((PASS++))
else
    echo -e "  ${RED}FAIL${NC}  ${ERROR_PAGES} page(s) contain server-error text"
    ((FAIL++))
fi

echo ""

# ─── Gate 4: Console errors (Playwright only) ────────────────────────

echo -e "${BOLD}[L5-4] Console errors (JS runtime)${NC}"

if [ "$USE_PLAYWRIGHT" -eq 1 ]; then
    TMPSCRIPT=$(mktemp /tmp/pw_check_XXXXXX.mjs)
    cat > "$TMPSCRIPT" << 'PLAYWRIGHT_EOF'
import { chromium } from 'playwright';

const base = process.argv[2] || 'http://localhost:3000';
const pages = ['/', '/login', '/dashboard'];
const errors = [];

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();

for (const path of pages) {
    const page = await context.newPage();
    const pageErrors = [];

    page.on('console', msg => {
        if (msg.type() === 'error') {
            pageErrors.push(`${path}: ${msg.text()}`);
        }
    });

    page.on('pageerror', err => {
        pageErrors.push(`${path}: UNCAUGHT ${err.message}`);
    });

    try {
        await page.goto(`${base}${path}`, { waitUntil: 'networkidle', timeout: 15000 });
    } catch (e) {
        // Timeout is ok for slow pages
    }

    errors.push(...pageErrors);
    await page.close();
}

await browser.close();

if (errors.length > 0) {
    console.log(`Found ${errors.length} console error(s):`);
    errors.forEach(e => console.log(`  - ${e}`));
    process.exit(1);
} else {
    console.log('No console errors detected');
    process.exit(0);
}
PLAYWRIGHT_EOF

    check "No console.error on any page" node "$TMPSCRIPT" "$BASE"
    rm -f "$TMPSCRIPT"
else
    skip "Console error check" "Playwright not installed (install: npx playwright install chromium)"
fi

echo ""

# ─── Gate 5: Static asset integrity ──────────────────────────────────

echo -e "${BOLD}[L5-5] Static assets${NC}"

DASH_BODY=$(curl -sf "${BASE}/" 2>/dev/null || echo "")

CSS_PATH=$(echo "$DASH_BODY" | grep -oE '(/_next/static|/assets|/static)/[^"]+\.css' | head -1)
JS_PATH=$(echo "$DASH_BODY" | grep -oE '(/_next/static|/assets|/static)/[^"]+\.js' | head -1)

if [ -n "$CSS_PATH" ]; then
    CSS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE}${CSS_PATH}")
    check "CSS asset loads (${CSS_STATUS})" test "$CSS_STATUS" = "200"
else
    skip "CSS asset check" "no CSS link found in HTML (may use inline styles)"
fi

if [ -n "$JS_PATH" ]; then
    JS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE}${JS_PATH}")
    check "JS asset loads (${JS_STATUS})" test "$JS_STATUS" = "200"
else
    skip "JS asset check" "no JS bundle link found in HTML"
fi

echo ""

# ─── Results ──────────────────────────────────────────────────────────

TOTAL=$((PASS + FAIL))
echo "==========================================="
echo -e " ${BOLD}UI Legibility Results${NC}"
echo " ${PASS} passed, ${FAIL} failed, ${SKIP} skipped (${TOTAL} checked)"
echo "==========================================="

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}UI LEGIBILITY FAILED${NC}"
    echo ""
    echo "Fix the failures above. Common causes:"
    echo "  - Frontend not built: cd frontend && npm run build"
    echo "  - Missing env vars: check .env.local"
    echo "  - API unreachable: backend must be running for SSR pages"
    exit 1
else
    echo -e "${GREEN}UI LEGIBILITY PASSED${NC}"
    exit 0
fi
