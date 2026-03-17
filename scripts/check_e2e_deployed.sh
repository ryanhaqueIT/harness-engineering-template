#!/usr/bin/env bash
# check_e2e_deployed.sh — E2E validation against a deployed instance.
#
# Runs HTTP-level checks against the production/staging backend to verify
# it is serving correctly. This is the Layer 7 gate.
#
# CONFIGURABLE: Edit the gates below to match your API endpoints.
#
# Exit code: 0 = all pass, 1 = at least one failure.
#
# Usage:
#   ./scripts/check_e2e_deployed.sh https://your-app.example.com
#   ./scripts/check_e2e_deployed.sh https://your-app.example.com --verbose

set -uo pipefail

# ─── Constants ────────────────────────────────────────────────────────

CURL_TIMEOUT=15  # seconds per request

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

PASS=0
FAIL=0
SKIP=0
VERBOSE=0

# ─── Parse args ───────────────────────────────────────────────────────

TARGET_URL=""

for arg in "$@"; do
    case "$arg" in
        --verbose|-v) VERBOSE=1 ;;
        --help|-h)
            echo "check_e2e_deployed.sh — E2E checks against deployed instance"
            echo ""
            echo "Usage:"
            echo "  ./scripts/check_e2e_deployed.sh <URL> [--verbose]"
            exit 0
            ;;
        http*) TARGET_URL="$arg" ;;
    esac
done

if [ -z "$TARGET_URL" ]; then
    echo -e "${RED}ERROR: No URL provided${NC}"
    echo "Usage: ./scripts/check_e2e_deployed.sh https://your-app.example.com"
    exit 1
fi

# Strip trailing slash
TARGET_URL="${TARGET_URL%/}"

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

verbose_body() {
    if [ "$VERBOSE" -eq 1 ] && [ -n "${1:-}" ]; then
        local preview="${1:0:500}"
        echo -e "  ${CYAN}---body-preview---${NC}"
        echo "  $preview"
        echo -e "  ${CYAN}---end---${NC}"
    fi
}

# ─── Banner ───────────────────────────────────────────────────────────

echo "==========================================="
echo -e " ${BOLD}E2E Deployed Instance Validation${NC}"
echo " Target: ${TARGET_URL}"
echo "==========================================="
echo ""

# ─── Preflight: is the URL reachable at all? ─────────────────────────

echo -e "${BOLD}[E2E-0] Connectivity${NC}"

if ! curl -sf --max-time "$CURL_TIMEOUT" -o /dev/null "${TARGET_URL}/health" 2>/dev/null; then
    echo "  First attempt failed, retrying (cold start)..."
    sleep 3
    if ! curl -sf --max-time "$CURL_TIMEOUT" -o /dev/null "${TARGET_URL}/health" 2>/dev/null; then
        echo -e "  ${RED}FAIL${NC}  Cannot reach ${TARGET_URL}"
        echo ""
        echo "Possible causes:"
        echo "  - Service is not deployed"
        echo "  - URL is incorrect"
        echo "  - Network/firewall issue"
        echo "  - Service is crashing on startup (check logs)"
        exit 1
    fi
fi

echo -e "  ${GREEN}PASS${NC}  Target is reachable"
((PASS++))
echo ""

# ─── Gate 1: /health returns 200 ─────────────────────────────────────

echo -e "${BOLD}[E2E-1] Health endpoint${NC}"

HEALTH_STATUS=$(curl -s --max-time "$CURL_TIMEOUT" -o /dev/null -w "%{http_code}" "${TARGET_URL}/health")
check "/health returns HTTP 200" test "$HEALTH_STATUS" = "200"

HEALTH_BODY=$(curl -sf --max-time "$CURL_TIMEOUT" "${TARGET_URL}/health" 2>/dev/null || echo "")
verbose_body "$HEALTH_BODY"

# Verify the body contains expected JSON
if echo "$HEALTH_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('status') in ('healthy','ok','up')" 2>/dev/null; then
    echo -e "  ${GREEN}PASS${NC}  /health response indicates healthy"
    ((PASS++))
else
    echo -e "  ${RED}FAIL${NC}  /health did not return a healthy status"
    echo "         Got: ${HEALTH_BODY:0:200}"
    ((FAIL++))
fi

echo ""

# ─── Gate 2: Root page returns content ────────────────────────────────

echo -e "${BOLD}[E2E-2] Root page (/)${NC}"

ROOT_STATUS=$(curl -s --max-time "$CURL_TIMEOUT" -o /dev/null -w "%{http_code}" "${TARGET_URL}/")
check "/ returns HTTP 200" test "$ROOT_STATUS" = "200"

ROOT_BODY=$(curl -sf --max-time "$CURL_TIMEOUT" "${TARGET_URL}/" 2>/dev/null || echo "")
ROOT_LEN=${#ROOT_BODY}
verbose_body "$ROOT_BODY"

check "/ has substantial content (${ROOT_LEN} bytes)" test "$ROOT_LEN" -gt 100

# Check no error indicators in body
if echo "$ROOT_BODY" | grep -qi "Internal Server Error\|500 Server Error\|Application Error\|502 Bad Gateway\|503 Service Unavailable"; then
    echo -e "  ${RED}FAIL${NC}  / contains server-error text"
    ((FAIL++))
else
    echo -e "  ${GREEN}PASS${NC}  / has no server-error indicators"
    ((PASS++))
fi

echo ""

# ─── Gate 3: API docs (if FastAPI/Swagger) ────────────────────────────

echo -e "${BOLD}[E2E-3] API documentation${NC}"

DOCS_STATUS=$(curl -s --max-time "$CURL_TIMEOUT" -o /dev/null -w "%{http_code}" "${TARGET_URL}/docs")

if [ "$DOCS_STATUS" = "200" ]; then
    DOCS_BODY=$(curl -sf --max-time "$CURL_TIMEOUT" "${TARGET_URL}/docs" 2>/dev/null || echo "")
    if echo "$DOCS_BODY" | grep -qi "swagger\|openapi\|redoc\|FastAPI"; then
        echo -e "  ${GREEN}PASS${NC}  /docs contains API documentation"
        ((PASS++))
    else
        echo -e "  ${GREEN}PASS${NC}  /docs returns 200 (content type may vary)"
        ((PASS++))
    fi
else
    skip "/docs" "returned HTTP ${DOCS_STATUS} (may not be available)"
fi

echo ""

# ─── Gate 4: Response headers ─────────────────────────────────────────

echo -e "${BOLD}[E2E-4] Response headers${NC}"

HEADERS=$(curl -sI --max-time "$CURL_TIMEOUT" "${TARGET_URL}/health" 2>/dev/null || echo "")

# Check correlation ID
if echo "$HEADERS" | grep -qi "x-correlation-id\|x-request-id\|x-trace-id"; then
    echo -e "  ${GREEN}PASS${NC}  Correlation/request ID header present"
    ((PASS++))
else
    echo -e "  ${YELLOW}SKIP${NC}  No correlation ID header (recommended but not required)"
    ((SKIP++))
fi

# Check CORS
CORS_STATUS=$(curl -s --max-time "$CURL_TIMEOUT" -o /dev/null -w "%{http_code}" \
    -X OPTIONS \
    -H "Origin: http://localhost:3000" \
    -H "Access-Control-Request-Method: GET" \
    "${TARGET_URL}/health" 2>/dev/null || echo "000")

if [ "$CORS_STATUS" = "200" ] || [ "$CORS_STATUS" = "204" ]; then
    echo -e "  ${GREEN}PASS${NC}  CORS preflight returns ${CORS_STATUS}"
    ((PASS++))
else
    echo -e "  ${YELLOW}SKIP${NC}  CORS preflight returned ${CORS_STATUS} (may be handled by gateway)"
    ((SKIP++))
fi

echo ""

# ─── Results ──────────────────────────────────────────────────────────

TOTAL=$((PASS + FAIL))
echo "==========================================="
echo -e " ${BOLD}E2E Deployed Results${NC}"
echo " Target:  ${TARGET_URL}"
echo " Results: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped (${TOTAL} checked)"
echo "==========================================="

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}E2E DEPLOYED VALIDATION FAILED${NC}"
    echo ""
    echo "Debugging steps:"
    echo "  1. Check service logs"
    echo "  2. Verify deployment status"
    echo "  3. Re-deploy and re-run this script"
    echo "  4. Run with --verbose for response body previews"
    exit 1
else
    echo -e "${GREEN}E2E DEPLOYED VALIDATION PASSED${NC}"
    exit 0
fi
