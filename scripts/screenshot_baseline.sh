#!/usr/bin/env bash
# screenshot_baseline.sh — Visual regression testing via screenshot comparison.
#
# Takes screenshots of key pages and compares them to a stored baseline.
# Uses ImageMagick `compare` for pixel-level diffing when available,
# falls back to file size comparison otherwise.
#
# Usage:
#   ./scripts/screenshot_baseline.sh              # Compare current vs baseline
#   ./scripts/screenshot_baseline.sh --update      # Refresh baseline from current
#
# Screenshots stored in: .harness/screenshots/baseline/
# Threshold: 5% pixel difference allowed (accounts for timestamps, etc.)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
BASELINE_DIR="${ROOT_DIR}/.harness/screenshots/baseline"
CURRENT_DIR="${ROOT_DIR}/.harness/screenshots/current"
DIFF_DIR="${ROOT_DIR}/.harness/screenshots/diff"
THRESHOLD=5  # percent pixel difference allowed

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PASS=0
FAIL=0
SKIP=0

# ─── Parse flags ─────────────────────────────────────────────────────

UPDATE_MODE=0
if [ "${1:-}" = "--update" ]; then
    UPDATE_MODE=1
fi

# ─── Ensure directories ─────────────────────────────────────────────

mkdir -p "$BASELINE_DIR" "$CURRENT_DIR" "$DIFF_DIR"

# ─── Capture current screenshots ────────────────────────────────────

capture_screenshots() {
    local target_dir="$1"
    local port="${2:-3000}"

    # Try Playwright first
    if command -v npx &>/dev/null && npx playwright --version &>/dev/null 2>&1; then
        echo "Capturing screenshots with Playwright..."
        TMPSCRIPT=$(mktemp /tmp/screenshot_XXXXXX.js)
        cat > "$TMPSCRIPT" << PLAYWRIGHT_EOF
const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
    const port = '${port}';
    const baseUrl = \`http://localhost:\${port}\`;
    const dir = '${target_dir}';

    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1280, height: 720 } });

    const pages = ['/', '/login', '/dashboard'];
    for (const path of pages) {
        const page = await context.newPage();
        try {
            await page.goto(\`\${baseUrl}\${path}\`, { waitUntil: 'networkidle', timeout: 15000 });
            const name = path === '/' ? 'home' : path.replace(/\\//g, '_').replace(/^_/, '');
            await page.screenshot({ path: \`\${dir}/\${name}.png\`, fullPage: true });
            console.log(\`Captured: \${name}.png\`);
        } catch (e) {
            console.log(\`Skipped \${path}: \${e.message}\`);
        }
        await page.close();
    }

    await browser.close();
})();
PLAYWRIGHT_EOF
        node "$TMPSCRIPT" 2>/dev/null
        rm -f "$TMPSCRIPT"
        return 0
    fi

    # Fallback: curl + wkhtmltoimage (if available)
    if command -v wkhtmltoimage &>/dev/null; then
        echo "Capturing screenshots with wkhtmltoimage..."
        for path in "/" "/login" "/dashboard"; do
            local name
            if [ "$path" = "/" ]; then name="home"; else name=$(echo "$path" | tr '/' '_' | sed 's/^_//'); fi
            wkhtmltoimage --quiet "http://localhost:${port}${path}" "${target_dir}/${name}.png" 2>/dev/null || true
        done
        return 0
    fi

    # Last fallback: save raw HTML for size comparison
    echo "No screenshot tool available. Saving HTML for size comparison..."
    for path in "/" "/login" "/dashboard"; do
        local name
        if [ "$path" = "/" ]; then name="home"; else name=$(echo "$path" | tr '/' '_' | sed 's/^_//'); fi
        curl -sf "http://localhost:${port}${path}" > "${target_dir}/${name}.html" 2>/dev/null || true
    done
    return 0
}

# ─── Detect running frontend ────────────────────────────────────────

FRONTEND_PORT=""
for TRY_PORT in 3000 3001 3847 3900 5173 8080; do
    if curl -sf -o /dev/null "http://localhost:${TRY_PORT}" 2>/dev/null; then
        FRONTEND_PORT="$TRY_PORT"
        break
    fi
done

if [ -z "$FRONTEND_PORT" ]; then
    echo -e "${YELLOW}No running frontend detected. Start the frontend first.${NC}"
    echo "  cd frontend && npm run dev"
    exit 0
fi

echo -e "${CYAN}Frontend detected on port ${FRONTEND_PORT}${NC}"
echo ""

# ─── Update mode: refresh baseline ──────────────────────────────────

if [ "$UPDATE_MODE" -eq 1 ]; then
    echo "Updating baseline screenshots..."
    rm -f "${BASELINE_DIR}"/*.png "${BASELINE_DIR}"/*.html 2>/dev/null
    capture_screenshots "$BASELINE_DIR" "$FRONTEND_PORT"
    COUNT=$(ls -1 "${BASELINE_DIR}"/*.png 2>/dev/null | wc -l || echo "0")
    COUNT_HTML=$(ls -1 "${BASELINE_DIR}"/*.html 2>/dev/null | wc -l || echo "0")
    TOTAL=$((COUNT + COUNT_HTML))
    echo -e "${GREEN}Baseline updated: ${TOTAL} screenshot(s) saved to ${BASELINE_DIR}/${NC}"
    exit 0
fi

# ─── Compare mode: check current vs baseline ────────────────────────

echo "Capturing current screenshots..."
rm -f "${CURRENT_DIR}"/*.png "${CURRENT_DIR}"/*.html 2>/dev/null
capture_screenshots "$CURRENT_DIR" "$FRONTEND_PORT"

# Check if baseline exists
BASELINE_FILES=$(ls -1 "${BASELINE_DIR}"/*.png "${BASELINE_DIR}"/*.html 2>/dev/null | wc -l || echo "0")
if [ "$BASELINE_FILES" -eq 0 ]; then
    echo -e "${YELLOW}No baseline screenshots found. Run with --update first.${NC}"
    echo "  ./scripts/screenshot_baseline.sh --update"
    exit 0
fi

echo ""
echo "Comparing current vs baseline..."
echo ""

# Compare each file
HAS_IMAGEMAGICK=0
if command -v compare &>/dev/null; then
    HAS_IMAGEMAGICK=1
fi

for BASELINE_FILE in "${BASELINE_DIR}"/*; do
    FILENAME=$(basename "$BASELINE_FILE")
    CURRENT_FILE="${CURRENT_DIR}/${FILENAME}"

    if [ ! -f "$CURRENT_FILE" ]; then
        echo -e "  ${RED}FAIL${NC}  ${FILENAME} — missing in current capture"
        ((FAIL++))
        continue
    fi

    # PNG comparison with ImageMagick
    if [ "$HAS_IMAGEMAGICK" -eq 1 ] && [[ "$FILENAME" == *.png ]]; then
        DIFF_FILE="${DIFF_DIR}/${FILENAME}"
        # compare returns the number of different pixels via -metric AE
        DIFF_PIXELS=$(compare -metric AE "$BASELINE_FILE" "$CURRENT_FILE" "$DIFF_FILE" 2>&1 || true)
        TOTAL_PIXELS=$(identify -format "%[fx:w*h]" "$BASELINE_FILE" 2>/dev/null || echo "1")

        if [ "$TOTAL_PIXELS" -gt 0 ] 2>/dev/null; then
            DIFF_PCT=$(python3 -c "print(round(${DIFF_PIXELS} / ${TOTAL_PIXELS} * 100, 2))" 2>/dev/null || echo "100")
        else
            DIFF_PCT="0"
        fi

        if python3 -c "exit(0 if float('${DIFF_PCT}') <= ${THRESHOLD} else 1)" 2>/dev/null; then
            echo -e "  ${GREEN}PASS${NC}  ${FILENAME} — ${DIFF_PCT}% difference (threshold: ${THRESHOLD}%)"
            ((PASS++))
        else
            echo -e "  ${RED}FAIL${NC}  ${FILENAME} — ${DIFF_PCT}% difference exceeds ${THRESHOLD}% threshold"
            echo "         Diff image: ${DIFF_FILE}"
            ((FAIL++))
        fi
    else
        # Fallback: file size comparison (within 20% tolerance)
        BASELINE_SIZE=$(wc -c < "$BASELINE_FILE" 2>/dev/null || echo "0")
        CURRENT_SIZE=$(wc -c < "$CURRENT_FILE" 2>/dev/null || echo "0")

        if [ "$BASELINE_SIZE" -gt 0 ] 2>/dev/null; then
            SIZE_DIFF=$(python3 -c "print(abs(${CURRENT_SIZE} - ${BASELINE_SIZE}) / ${BASELINE_SIZE} * 100)" 2>/dev/null || echo "100")
            if python3 -c "exit(0 if float('${SIZE_DIFF}') <= 20 else 1)" 2>/dev/null; then
                echo -e "  ${GREEN}PASS${NC}  ${FILENAME} — size within 20% (baseline: ${BASELINE_SIZE}b, current: ${CURRENT_SIZE}b)"
                ((PASS++))
            else
                echo -e "  ${RED}FAIL${NC}  ${FILENAME} — size differs by ${SIZE_DIFF}% (baseline: ${BASELINE_SIZE}b, current: ${CURRENT_SIZE}b)"
                ((FAIL++))
            fi
        else
            echo -e "  ${YELLOW}SKIP${NC}  ${FILENAME} — cannot compare (empty baseline)"
            ((SKIP++))
        fi
    fi
done

echo ""
echo "==========================================="
echo "Screenshot Baseline: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped"
echo "==========================================="

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}VISUAL REGRESSION DETECTED${NC}"
    echo "  To accept current as new baseline: ./scripts/screenshot_baseline.sh --update"
    exit 1
else
    echo -e "${GREEN}NO VISUAL REGRESSION${NC}"
    exit 0
fi
