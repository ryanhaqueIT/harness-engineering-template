#!/usr/bin/env bash
# track_quality.sh — Historical quality trend tracking.
#
# Runs harness_scorecard.py, captures the output, and appends a timestamped
# entry to .harness/history/quality.csv. On each run, prints the last 5
# entries showing trend direction.
#
# CSV columns: date,grade,score,total_checks,passed,failed,test_count,loc_count
#
# Usage:
#   ./scripts/track_quality.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
HISTORY_DIR="${ROOT_DIR}/.harness/history"
CSV_FILE="${HISTORY_DIR}/quality.csv"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ─── Ensure directories ─────────────────────────────────────────────

mkdir -p "$HISTORY_DIR"

# ─── Initialize CSV if needed ────────────────────────────────────────

if [ ! -f "$CSV_FILE" ]; then
    echo "date,grade,score,total_checks,passed,failed,test_count,loc_count" > "$CSV_FILE"
fi

# ─── Run scorecard and capture output ────────────────────────────────

echo -e "${BOLD}Running harness scorecard...${NC}"
echo ""

SCORECARD_OUTPUT=""
if [ -f "${ROOT_DIR}/scripts/harness_scorecard.py" ]; then
    SCORECARD_OUTPUT=$(python3 "${ROOT_DIR}/scripts/harness_scorecard.py" 2>/dev/null || python "${ROOT_DIR}/scripts/harness_scorecard.py" 2>/dev/null || echo "")
    echo "$SCORECARD_OUTPUT"
else
    echo -e "${RED}harness_scorecard.py not found${NC}"
    exit 1
fi

# ─── Parse scorecard output ─────────────────────────────────────────

# Extract grade and score from output like "Grade:   A+    (28/31 checks passed)"
GRADE=$(echo "$SCORECARD_OUTPUT" | grep -oP 'Grade:.*?(\b[A-F][+]?\b)' | grep -oP '[A-F][+]?' | head -1)
PASSED=$(echo "$SCORECARD_OUTPUT" | grep -oP '\((\d+)/\d+ checks' | grep -oP '\d+' | head -1)
TOTAL_CHECKS=$(echo "$SCORECARD_OUTPUT" | grep -oP '\(\d+/(\d+) checks' | grep -oP '\d+' | tail -1)

if [ -z "$GRADE" ]; then
    GRADE="?"
fi
if [ -z "$PASSED" ]; then
    PASSED="0"
fi
if [ -z "$TOTAL_CHECKS" ]; then
    TOTAL_CHECKS="31"
fi

FAILED=$((TOTAL_CHECKS - PASSED))

# Count test files
TEST_COUNT=0
for test_dir in "backend/tests" "tests" "frontend/__tests__" "test"; do
    if [ -d "${ROOT_DIR}/${test_dir}" ]; then
        TEST_COUNT=$((TEST_COUNT + $(find "${ROOT_DIR}/${test_dir}" -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" 2>/dev/null | grep -ci "test" || echo "0")))
    fi
done

# Count lines of code (backend Python files, excluding tests/venv)
LOC_COUNT=0
if [ -d "${ROOT_DIR}/backend" ]; then
    LOC_COUNT=$(find "${ROOT_DIR}/backend" -name "*.py" -not -path "*test*" -not -path "*.venv*" -not -path "*__pycache__*" -exec cat {} + 2>/dev/null | wc -l || echo "0")
fi

# ─── Append entry ────────────────────────────────────────────────────

DATE=$(date '+%Y-%m-%d %H:%M')
echo "${DATE},${GRADE},${PASSED},${TOTAL_CHECKS},${PASSED},${FAILED},${TEST_COUNT},${LOC_COUNT}" >> "$CSV_FILE"

echo ""
echo -e "${CYAN}Entry recorded: ${DATE} | Grade: ${GRADE} | ${PASSED}/${TOTAL_CHECKS} passed${NC}"
echo ""

# ─── Show trend ──────────────────────────────────────────────────────

echo -e "${BOLD}Quality Trend (last 5 entries):${NC}"
echo ""

# Read last 5 data lines (skip header)
ENTRIES=$(tail -n +2 "$CSV_FILE" | tail -5)

PREV_SCORE=""
while IFS=',' read -r date grade score total passed failed tests loc; do
    # Determine trend arrow
    ARROW=""
    if [ -n "$PREV_SCORE" ]; then
        if [ "$score" -gt "$PREV_SCORE" ] 2>/dev/null; then
            ARROW="${GREEN}^ improving${NC}"
        elif [ "$score" -lt "$PREV_SCORE" ] 2>/dev/null; then
            ARROW="${RED}v regressing${NC}"
        else
            ARROW="${DIM}> stable${NC}"
        fi
    fi

    # Color the grade
    GRADE_COLOR="$NC"
    case "$grade" in
        A*) GRADE_COLOR="$GREEN" ;;
        B*)  GRADE_COLOR="$CYAN" ;;
        C*)  GRADE_COLOR="$YELLOW" ;;
        *)   GRADE_COLOR="$RED" ;;
    esac

    echo -e "  ${DIM}${date}${NC}  ${GRADE_COLOR}${grade}${NC}  ${passed}/${total} passed  ${tests} tests  ${loc} LOC  ${ARROW}"
    PREV_SCORE="$score"
done <<< "$ENTRIES"

echo ""
echo -e "${DIM}Full history: ${CSV_FILE}${NC}"
