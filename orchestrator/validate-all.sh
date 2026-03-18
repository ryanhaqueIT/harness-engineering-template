#!/usr/bin/env bash
# validate-all.sh — Orchestrator: runs all installed tier validations.
#
# Reads .harness/manifest.json to discover which tiers are installed,
# then runs each tier's validate script in order (T1 → T2 → T3 → T4).
#
# Usage:
#   bash orchestrator/validate-all.sh [--continue]
#
# Flags:
#   --continue    Run all tiers even if earlier ones fail (default: stop on first failure)

set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

REPO_ROOT="$(git rev-parse --show-toplevel)"
MANIFEST="$REPO_ROOT/.harness/manifest.json"
CONTINUE_ON_FAIL=false

if [[ "${1:-}" == "--continue" ]]; then
    CONTINUE_ON_FAIL=true
fi

echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
echo -e "${BOLD} Harness Orchestrator — Validate All Tiers${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
echo ""

# ─── Check manifest exists ────────────────────────

if [ ! -f "$MANIFEST" ]; then
    echo -e "  ${RED}No manifest found at .harness/manifest.json${NC}"
    echo -e "  Run a tier's install.sh first."
    exit 1
fi

# ─── Parse installed tiers ────────────────────────

TIER_PASS=0
TIER_FAIL=0
TIER_SKIP=0

run_tier() {
    local tier_key="$1"
    local tier_name="$2"
    local validate_script="$3"

    # Check if tier is installed in manifest
    local installed
    installed=$(python3 -c "
import json, sys
try:
    m = json.load(open('$MANIFEST'))
    t = m.get('tiers', {}).get('$tier_key', {})
    print('true' if t.get('installed') else 'false')
except: print('false')
" 2>/dev/null)

    if [ "$installed" != "true" ]; then
        echo -e "  ${YELLOW}SKIP${NC}  $tier_name (not installed)"
        ((TIER_SKIP++))
        return 0
    fi

    echo -e "${BOLD}── $tier_name ──────────────────────────────────${NC}"

    if [ ! -f "$validate_script" ]; then
        echo -e "  ${RED}FAIL${NC}  Validate script not found: $validate_script"
        ((TIER_FAIL++))
        return 1
    fi

    if bash "$validate_script"; then
        echo -e "  ${GREEN}✓ $tier_name PASSED${NC}"
        ((TIER_PASS++))
        return 0
    else
        echo -e "  ${RED}✗ $tier_name FAILED${NC}"
        ((TIER_FAIL++))
        return 1
    fi
}

# ─── Run tiers in order ──────────────────────────

OVERALL=0

for tier in \
    "t1-code-quality:Tier 1 - Code Quality:$REPO_ROOT/.harness/validate-t1.sh" \
    "t2-architecture:Tier 2 - Architecture:$REPO_ROOT/.harness/validate-t2.sh" \
    "t3-app-testing:Tier 3 - App Testing:$REPO_ROOT/.harness/validate-t3.sh" \
    "t4-product-verification:Tier 4 - Product Verification:$REPO_ROOT/.harness/validate-t4.sh"; do

    IFS=':' read -r key name script <<< "$tier"

    if ! run_tier "$key" "$name" "$script"; then
        OVERALL=1
        if [ "$CONTINUE_ON_FAIL" = false ]; then
            echo ""
            echo -e "  ${RED}Stopping on first failure. Use --continue to run all tiers.${NC}"
            break
        fi
    fi

    echo ""
done

# ─── Summary ──────────────────────────────────────

echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
echo -e " Tiers: ${GREEN}${TIER_PASS} passed${NC}, ${RED}${TIER_FAIL} failed${NC}, ${YELLOW}${TIER_SKIP} skipped${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"

exit $OVERALL
