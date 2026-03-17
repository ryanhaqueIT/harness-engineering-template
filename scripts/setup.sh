#!/usr/bin/env bash
# setup.sh — One-command harness initialization for a new project.
#
# Run this AFTER cloning the template into your project:
#   bash scripts/setup.sh
#
# It creates the directory structure expected by validate.sh and
# verifies that the harness scripts are executable.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "==========================================="
echo -e " ${BOLD}Harness Engineering — Setup${NC}"
echo "==========================================="
echo ""

cd "$ROOT_DIR"

# ─── Ensure scripts are executable ─────────────────────────────────

echo -e "${BOLD}Making scripts executable...${NC}"

for script in scripts/*.sh scripts/*.py; do
    if [ -f "$script" ]; then
        chmod +x "$script"
        echo "  +x $script"
    fi
done

echo ""

# ─── Ensure directory structure exists ─────────────────────────────

echo -e "${BOLD}Verifying directory structure...${NC}"

DIRS=(
    "docs/design-docs"
    "docs/exec-plans/active"
    "docs/exec-plans/completed"
    "docs/generated"
    "docs/product-specs"
    "docs/references"
)

for dir in "${DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        echo "  Created $dir/"
    else
        echo "  OK $dir/"
    fi
done

# Ensure .gitkeep files exist in empty dirs
for dir in "${DIRS[@]}"; do
    if [ -z "$(ls -A "$dir" 2>/dev/null)" ]; then
        touch "$dir/.gitkeep"
    fi
done

echo ""

# ─── Verify core files exist ──────────────────────────────────────

echo -e "${BOLD}Verifying core files...${NC}"

REQUIRED_FILES=(
    "AGENTS.md"
    "PLANS.md"
    "scripts/validate.sh"
    "docs/QUALITY_SCORE.md"
    "docs/SECURITY.md"
    "docs/RELIABILITY.md"
    "docs/design-docs/core-beliefs.md"
    "docs/exec-plans/tech-debt-tracker.md"
)

ALL_PRESENT=1
for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "  ${GREEN}OK${NC} $file"
    else
        echo -e "  ${RED}MISSING${NC} $file"
        ALL_PRESENT=0
    fi
done

echo ""

# ─── Check for placeholder values ─────────────────────────────────

echo -e "${BOLD}Checking for unconfigured placeholders...${NC}"

PLACEHOLDER_COUNT=0
for file in AGENTS.md docs/PRODUCT_SENSE.md docs/DESIGN.md docs/FRONTEND.md; do
    if [ -f "$file" ]; then
        COUNT=$(grep -c '{{' "$file" 2>/dev/null || echo "0")
        if [ "$COUNT" -gt 0 ]; then
            echo -e "  ${CYAN}$file${NC} has ${COUNT} placeholder(s) to fill in"
            PLACEHOLDER_COUNT=$((PLACEHOLDER_COUNT + COUNT))
        fi
    fi
done

echo ""

# ─── Summary ──────────────────────────────────────────────────────

echo "==========================================="
echo -e " ${BOLD}Setup Complete${NC}"
echo "==========================================="
echo ""

if [ "$ALL_PRESENT" -eq 1 ]; then
    echo -e "${GREEN}All core files present.${NC}"
else
    echo -e "${RED}Some core files are missing. Review the list above.${NC}"
fi

if [ "$PLACEHOLDER_COUNT" -gt 0 ]; then
    echo ""
    echo "Next steps:"
    echo "  1. Edit AGENTS.md — replace {{PLACEHOLDER}} values with your project specifics"
    echo "  2. Edit scripts/check_imports.py — define your module dependency RULES"
    echo "  3. Edit scripts/check_architecture.py — configure DB_MODULE, AI patterns"
    echo "  4. Edit docs/PRODUCT_SENSE.md — describe your product and core beliefs"
    echo "  5. Run: ./scripts/validate.sh"
else
    echo ""
    echo "Run ./scripts/validate.sh to verify the harness is working."
fi

echo ""
echo "For the interactive setup that auto-generates these files, run:"
echo "  bash setup.sh  (from the project root)"
