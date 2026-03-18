#!/usr/bin/env bash
# check_ui_playwright.sh — Layer 5 Browser Automation Gate
# Drives the UI like a QA engineer using Playwright.
# Based on: OpenAI CDP + Anthropic Puppeteer MCP patterns.
#
# Key insight: Uses accessibility tree snapshots over screenshots.
# This is deterministic, cheaper (no vision API), and less brittle.
#
# Usage:
#   ./scripts/check_ui_playwright.sh           # auto-detect frontend
#   ./scripts/check_ui_playwright.sh 3000      # use running frontend on port
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
SNAPSHOT_DIR="${REPO_ROOT}/.harness/snapshots"
mkdir -p "$SNAPSHOT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

CLEANUP_PID=""
cleanup() {
    if [ -n "$CLEANUP_PID" ]; then
        kill "$CLEANUP_PID" 2>/dev/null
        wait "$CLEANUP_PID" 2>/dev/null
    fi
}
trap cleanup EXIT

# ─── Detect app URLs ─────────────────────────────────────────────────
METADATA="${REPO_ROOT}/instance-metadata.json"
if [ -f "$METADATA" ]; then
    BACKEND_URL=$(python3 -c "import json; print(json.load(open('$METADATA'))['backend_url'])" 2>/dev/null || echo "http://localhost:8000")
    FRONTEND_URL=$(python3 -c "import json; print(json.load(open('$METADATA'))['frontend_url'])" 2>/dev/null || echo "http://localhost:3000")
else
    BACKEND_URL="http://localhost:8000"
    FRONTEND_URL="http://localhost:3000"
fi

# ─── Determine port & boot if needed ─────────────────────────────────
PORT="${1:-}"
FRONTEND_DIR="${REPO_ROOT}/frontend"

if [ -n "$PORT" ]; then
    FRONTEND_URL="http://localhost:${PORT}"
elif ! curl -sf -o /dev/null "$FRONTEND_URL" 2>/dev/null; then
    # Try common dev ports
    for TRY_PORT in 3000 3001 3857 5173 8080; do
        if curl -sf -o /dev/null "http://localhost:${TRY_PORT}" 2>/dev/null; then
            FRONTEND_URL="http://localhost:${TRY_PORT}"
            PORT="$TRY_PORT"
            echo -e "${GREEN}Found running frontend on port ${TRY_PORT}${NC}"
            break
        fi
    done

    # Nothing found — boot one ourselves
    if [ -z "$PORT" ] && [ -d "$FRONTEND_DIR" ] && [ -f "$FRONTEND_DIR/package.json" ]; then
        cd "$FRONTEND_DIR"
        PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('',0)); print(s.getsockname()[1]); s.close()" 2>/dev/null || echo "3857")
        FRONTEND_URL="http://localhost:${PORT}"

        if [ -f "next.config.js" ] || [ -f "next.config.ts" ] || [ -f "next.config.mjs" ]; then
            [ ! -d ".next" ] && { echo "Building frontend..."; npx next build > /dev/null 2>&1; }
            npx next start -p "$PORT" > /dev/null 2>&1 &
            CLEANUP_PID=$!
        elif [ -f "vite.config.ts" ] || [ -f "vite.config.js" ]; then
            npx vite preview --port "$PORT" > /dev/null 2>&1 &
            CLEANUP_PID=$!
        elif grep -q '"start"' package.json 2>/dev/null; then
            PORT="$PORT" npm start > /dev/null 2>&1 &
            CLEANUP_PID=$!
        fi

        if [ -n "$CLEANUP_PID" ]; then
            echo "Booting frontend on port $PORT..."
            for _ in $(seq 1 20); do
                curl -sf -o /dev/null "$FRONTEND_URL" 2>/dev/null && break
                sleep 1
            done
        fi
    fi
fi

echo ""
echo -e "${BOLD}=== Layer 5 — Browser Automation Gate ===${NC}"
echo -e "  Frontend: ${FRONTEND_URL}"
echo -e "  Backend:  ${BACKEND_URL}"
echo ""

# ─── Dispatch to Python gate or fallback ──────────────────────────────
export REPO_ROOT FRONTEND_URL BACKEND_URL

if [ -f "${REPO_ROOT}/scripts/playwright_gate.py" ] && [ -f "${REPO_ROOT}/.harness/feature_list.json" ]; then
    # Full feature-driven gate
    echo -e "${BOLD}Running feature-driven browser gate...${NC}"
    python3 "${REPO_ROOT}/scripts/playwright_gate.py"
    exit $?
fi

if [ -f "${REPO_ROOT}/scripts/playwright_gate.py" ]; then
    # No feature_list.json — run default checks via Python
    echo -e "${BOLD}Running default browser checks (no feature_list.json)...${NC}"
    python3 "${REPO_ROOT}/scripts/playwright_gate.py"
    exit $?
fi

# ─── Pure-shell fallback (no playwright_gate.py) ─────────────────────
echo -e "${YELLOW}playwright_gate.py not found — falling back to HTTP checks${NC}"
echo ""

PASS=0
FAIL=0

for PAGE in "/" "/login" "/dashboard"; do
    BODY=$(curl -sf "${FRONTEND_URL}${PAGE}" 2>/dev/null || echo "")
    BODY_LEN=${#BODY}
    if [ "$BODY_LEN" -gt 50 ]; then
        echo -e "  ${GREEN}PASS${NC}  ${PAGE} returns content (${BODY_LEN} bytes)"
        ((PASS++))
    else
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${FRONTEND_URL}${PAGE}" 2>/dev/null || echo "000")
        if [ "$STATUS" = "301" ] || [ "$STATUS" = "302" ] || [ "$STATUS" = "307" ]; then
            echo -e "  ${GREEN}PASS${NC}  ${PAGE} redirects (HTTP ${STATUS})"
            ((PASS++))
        else
            echo -e "  ${RED}FAIL${NC}  ${PAGE} — ${BODY_LEN} bytes, HTTP ${STATUS}"
            ((FAIL++))
        fi
    fi
done

echo ""
echo "Layer 5 Browser Gate: ${PASS} passed, ${FAIL} failed"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
