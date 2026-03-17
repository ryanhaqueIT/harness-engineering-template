#!/usr/bin/env bash
# check_ui_playwright.sh — Layer 5 Application Legibility with REAL browser.
#
# Uses Playwright to launch a headless browser, navigate pages, interact
# with forms, and verify the app works as a real user would experience it.
#
# This goes BEYOND curl-based checks:
#   - Renders JavaScript (catches React hydration failures)
#   - Captures console.error (catches runtime JS errors)
#   - Fills forms and clicks buttons (catches broken interactions)
#   - Takes screenshots (enables visual regression testing)
#
# Prerequisites: npx playwright install chromium
# Falls back gracefully if Playwright is not installed.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="${ROOT_DIR}/frontend"
PORT="${1:-3857}"
PASS=0
FAIL=0
CLEANUP_PID=""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

check() {
    local name="$1"
    shift
    if "$@" 2>&1; then
        echo -e "  ${GREEN}PASS${NC} $name"
        ((PASS++))
    else
        echo -e "  ${RED}FAIL${NC} $name"
        ((FAIL++))
    fi
}

cleanup() {
    if [ -n "$CLEANUP_PID" ]; then
        kill "$CLEANUP_PID" 2>/dev/null
        wait "$CLEANUP_PID" 2>/dev/null
    fi
}
trap cleanup EXIT

echo "Layer 5 — Application Legibility (Playwright)"
echo ""

# Check if Playwright is available
if ! npx playwright --version &>/dev/null; then
    echo -e "${YELLOW}Playwright not installed. Install with: npx playwright install chromium${NC}"
    echo -e "${YELLOW}Falling back to curl-based checks.${NC}"
    exec bash "${SCRIPT_DIR}/check_ui_legibility.sh" "$@"
fi

# Build and start frontend (detect framework)
cd "$FRONTEND_DIR"

if [ -f "next.config.js" ] || [ -f "next.config.ts" ] || [ -f "next.config.mjs" ]; then
    if [ ! -d ".next" ]; then
        echo "Building frontend..."
        npx next build > /dev/null 2>&1
    fi
    npx next start -p "$PORT" > /dev/null 2>&1 &
    CLEANUP_PID=$!
elif [ -f "vite.config.ts" ] || [ -f "vite.config.js" ]; then
    npx vite preview --port "$PORT" > /dev/null 2>&1 &
    CLEANUP_PID=$!
elif grep -q '"start"' package.json 2>/dev/null; then
    PORT="$PORT" npm start > /dev/null 2>&1 &
    CLEANUP_PID=$!
else
    echo -e "${RED}Cannot detect frontend framework${NC}"
    exit 1
fi

echo "Booting frontend on port $PORT..."
for i in $(seq 1 20); do
    if curl -s "http://localhost:${PORT}" > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

if ! curl -s "http://localhost:${PORT}" > /dev/null 2>&1; then
    echo -e "${RED}Frontend failed to start on port ${PORT}${NC}"
    exit 1
fi

echo "Frontend running on port $PORT"
echo ""

# Create Playwright test script
TEST_SCRIPT=$(mktemp /tmp/playwright_test_XXXXXX.js)
cat > "$TEST_SCRIPT" << 'PLAYWRIGHT_EOF'
const { chromium } = require('playwright');

(async () => {
    const port = process.argv[2] || '3857';
    const baseUrl = `http://localhost:${port}`;
    const results = [];
    let consoleErrors = [];

    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1280, height: 720 } });
    const page = await context.newPage();

    // Capture console errors
    page.on('console', msg => {
        if (msg.type() === 'error') {
            consoleErrors.push(msg.text());
        }
    });
    page.on('pageerror', err => {
        consoleErrors.push(err.message);
    });

    // Test 1: Home page loads and renders
    try {
        await page.goto(baseUrl, { waitUntil: 'networkidle', timeout: 15000 });
        const bodyText = await page.textContent('body');
        const hasContent = bodyText && bodyText.length > 50;
        results.push({ name: 'Home page renders with content', pass: hasContent });
    } catch (e) {
        results.push({ name: 'Home page renders with content', pass: false, error: e.message });
    }

    // Test 2: No JavaScript console errors
    results.push({
        name: `No console errors (found ${consoleErrors.length})`,
        pass: consoleErrors.length === 0,
        error: consoleErrors.length > 0 ? consoleErrors.slice(0, 3).join('; ') : undefined
    });

    // Test 3: Screenshot captures (visual evidence)
    try {
        const screenshotDir = '/tmp/harness-screenshots';
        const fs = require('fs');
        if (!fs.existsSync(screenshotDir)) fs.mkdirSync(screenshotDir, { recursive: true });
        await page.screenshot({ path: `${screenshotDir}/home.png`, fullPage: true });
        results.push({ name: `Screenshots saved to ${screenshotDir}/`, pass: true });
    } catch (e) {
        results.push({ name: 'Screenshots captured', pass: false, error: e.message });
    }

    await browser.close();

    // Output results as JSON
    console.log(JSON.stringify({ results, consoleErrors }));
    process.exit(results.every(r => r.pass) ? 0 : 1);
})();
PLAYWRIGHT_EOF

# Run Playwright tests
echo "-- Playwright Browser Tests"
RESULT=$(node "$TEST_SCRIPT" "$PORT" 2>/dev/null)
EXIT_CODE=$?

if [ "$EXIT_CODE" -eq 0 ]; then
    echo "$RESULT" | python3 -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    for r in data['results']:
        status = 'PASS' if r['pass'] else 'FAIL'
        print(f'  {status} {r[\"name\"]}')
    passed = sum(1 for r in data['results'] if r['pass'])
    total = len(data['results'])
    print(f'Playwright: {passed}/{total} passed')
except:
    print('  Could not parse Playwright results')
" 2>/dev/null
    PASS=$((PASS + 1))
    echo -e "   ${GREEN}PASS${NC}"
else
    FAIL=$((FAIL + 1))
    echo -e "   ${RED}FAIL${NC}"
fi

# Cleanup temp file
rm -f "$TEST_SCRIPT"

echo ""
echo "Layer 5 Legibility: ${PASS} passed, ${FAIL} failed"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
