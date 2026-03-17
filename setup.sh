#!/usr/bin/env bash
# setup.sh — Interactive project setup for the harness engineering template.
#
# This script asks you about your project and generates the appropriate:
#   - AGENTS.md with correct module names and commands
#   - scripts/check_imports.py with correct dependency rules
#   - scripts/check_architecture.py with correct library patterns
#   - .github/workflows/ci.yml with correct language detection
#
# Usage:
#   bash setup.sh
#
# Run this once after cloning the template. After that, edit files directly.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==========================================="
echo -e " ${BOLD}Harness Engineering — Interactive Setup${NC}"
echo "==========================================="
echo ""
echo "This will configure the harness for your project."
echo "You can always edit the generated files later."
echo ""

# ─── Gather info ──────────────────────────────────────────────────────

read -rp "Project name (e.g., Acme Platform): " PROJECT_NAME
PROJECT_NAME="${PROJECT_NAME:-My Project}"

read -rp "One-line description: " PROJECT_DESC
PROJECT_DESC="${PROJECT_DESC:-A software project.}"

echo ""
echo "Backend language:"
echo "  1) Python (FastAPI, Django, Flask)"
echo "  2) Node.js (Express, Fastify, NestJS)"
echo "  3) None (no backend)"
read -rp "Choice [1/2/3]: " BACKEND_CHOICE
BACKEND_CHOICE="${BACKEND_CHOICE:-1}"

echo ""
echo "Frontend framework:"
echo "  1) Next.js"
echo "  2) React (Vite)"
echo "  3) Vue (Vite)"
echo "  4) None (no frontend)"
read -rp "Choice [1/2/3/4]: " FRONTEND_CHOICE
FRONTEND_CHOICE="${FRONTEND_CHOICE:-1}"

echo ""
echo "Infrastructure:"
echo "  1) Terraform"
echo "  2) Pulumi"
echo "  3) None"
read -rp "Choice [1/2/3]: " INFRA_CHOICE
INFRA_CHOICE="${INFRA_CHOICE:-3}"

echo ""
echo "Cloud provider (for architecture template):"
echo "  1) AWS"
echo "  2) GCP"
echo "  3) Azure"
echo "  4) Other / Self-hosted"
read -rp "Choice [1/2/3/4]: " CLOUD_CHOICE
CLOUD_CHOICE="${CLOUD_CHOICE:-1}"

echo ""
echo "Database:"
echo "  1) PostgreSQL"
echo "  2) MongoDB"
echo "  3) DynamoDB"
echo "  4) Firestore"
echo "  5) SQLite"
echo "  6) Other"
read -rp "Choice [1-6]: " DB_CHOICE
DB_CHOICE="${DB_CHOICE:-1}"

echo ""
echo "Backend module structure (comma-separated top-level dirs inside backend/):"
echo "  Example: routers,services,db,auth,models"
read -rp "Modules: " MODULES_INPUT
MODULES_INPUT="${MODULES_INPUT:-routers,services,db,models}"

echo ""

# ─── Derive values ────────────────────────────────────────────────────

# Backend
case "$BACKEND_CHOICE" in
    1)
        BACKEND_STACK="Python, FastAPI, Pydantic"
        BACKEND_LANG="Python"
        BACKEND_CONVENTIONS="snake_case functions/vars, PascalCase classes, ruff format"
        LINT_CMD="ruff check ."
        FORMAT_CMD="ruff format --check ."
        TEST_CMD="python -m pytest tests/ -v --tb=short"
        ;;
    2)
        BACKEND_STACK="Node.js, TypeScript, Express"
        BACKEND_LANG="TypeScript"
        BACKEND_CONVENTIONS="camelCase functions/vars, PascalCase classes, prettier format"
        LINT_CMD="npx eslint . --max-warnings 0"
        FORMAT_CMD="npx prettier --check ."
        TEST_CMD="npm test"
        ;;
    3)
        BACKEND_STACK="None"
        BACKEND_LANG="N/A"
        BACKEND_CONVENTIONS="N/A"
        LINT_CMD="echo 'No backend'"
        FORMAT_CMD="echo 'No backend'"
        TEST_CMD="echo 'No backend'"
        ;;
esac

# Frontend
case "$FRONTEND_CHOICE" in
    1) FRONTEND_STACK="Next.js, TypeScript, Tailwind CSS"
       FRONTEND_LINT_CMD="npx eslint . --max-warnings 0"
       FRONTEND_FORMAT_CMD="npx prettier --check ."
       FRONTEND_BUILD_CMD="npx next build"
       ;;
    2) FRONTEND_STACK="React (Vite), TypeScript, Tailwind CSS"
       FRONTEND_LINT_CMD="npx eslint . --max-warnings 0"
       FRONTEND_FORMAT_CMD="npx prettier --check ."
       FRONTEND_BUILD_CMD="npx vite build"
       ;;
    3) FRONTEND_STACK="Vue (Vite), TypeScript"
       FRONTEND_LINT_CMD="npx eslint . --max-warnings 0"
       FRONTEND_FORMAT_CMD="npx prettier --check ."
       FRONTEND_BUILD_CMD="npx vite build"
       ;;
    4) FRONTEND_STACK="None"
       FRONTEND_LINT_CMD="echo 'No frontend'"
       FRONTEND_FORMAT_CMD="echo 'No frontend'"
       FRONTEND_BUILD_CMD="echo 'No frontend'"
       ;;
esac

# Infrastructure
case "$INFRA_CHOICE" in
    1) INFRA_STACK="Terraform"; INFRA_CMD="cd terraform && terraform init && terraform apply" ;;
    2) INFRA_STACK="Pulumi"; INFRA_CMD="cd pulumi && pulumi up" ;;
    3) INFRA_STACK="None"; INFRA_CMD="echo 'No infrastructure tool configured'" ;;
esac

# Cloud
case "$CLOUD_CHOICE" in
    1) CLOUD="AWS"; DEPLOY_CMD="# Configure AWS deployment here" ;;
    2) CLOUD="GCP"; DEPLOY_CMD="# Configure GCP deployment here" ;;
    3) CLOUD="Azure"; DEPLOY_CMD="# Configure Azure deployment here" ;;
    4) CLOUD="Self-hosted"; DEPLOY_CMD="# Configure deployment here" ;;
esac

# Database
case "$DB_CHOICE" in
    1) DATABASE="PostgreSQL"; DB_IMPORT_PATTERN="sqlalchemy"; DB_NAMING="snake_case column names" ;;
    2) DATABASE="MongoDB"; DB_IMPORT_PATTERN="pymongo"; DB_NAMING="camelCase field names" ;;
    3) DATABASE="DynamoDB"; DB_IMPORT_PATTERN="boto3"; DB_NAMING="PascalCase attribute names" ;;
    4) DATABASE="Firestore"; DB_IMPORT_PATTERN="google.cloud.firestore"; DB_NAMING="snake_case field names" ;;
    5) DATABASE="SQLite"; DB_IMPORT_PATTERN="sqlite3"; DB_NAMING="snake_case column names" ;;
    6) DATABASE="Other"; DB_IMPORT_PATTERN=""; DB_NAMING="consistent naming" ;;
esac

# Parse modules into dependency rules
IFS=',' read -ra MODULE_LIST <<< "$MODULES_INPUT"
DB_LAYER="db"
AI_LAYER="agent"

# Build module dependency string for AGENTS.md
LAYER_DEPS=""
for mod in "${MODULE_LIST[@]}"; do
    mod=$(echo "$mod" | tr -d ' ')
    case "$mod" in
        routers|routes|controllers|handlers)
            LAYER_DEPS="${LAYER_DEPS}${mod}/       -> may import: services/, models/, auth/\n"
            ;;
        services|service)
            LAYER_DEPS="${LAYER_DEPS}${mod}/    -> may import: db/, models/\n"
            ;;
        db|database|repo|repositories)
            LAYER_DEPS="${LAYER_DEPS}${mod}/          -> may import: nothing (leaf layer)\n"
            DB_LAYER="$mod"
            ;;
        models|schemas|types)
            LAYER_DEPS="${LAYER_DEPS}${mod}/      -> may import: nothing (leaf layer)\n"
            ;;
        auth|middleware)
            LAYER_DEPS="${LAYER_DEPS}${mod}/        -> may import: db/, models/\n"
            ;;
        agent|ai)
            LAYER_DEPS="${LAYER_DEPS}${mod}/       -> may import: services/, db/\n"
            AI_LAYER="$mod"
            ;;
        *)
            LAYER_DEPS="${LAYER_DEPS}${mod}/       -> may import: services/, db/\n"
            ;;
    esac
done

# ─── Generate check_imports.py RULES ─────────────────────────────────

IMPORT_RULES=""
for mod in "${MODULE_LIST[@]}"; do
    mod=$(echo "$mod" | tr -d ' ')
    case "$mod" in
        routers|routes|controllers|handlers)
            IMPORT_RULES="${IMPORT_RULES}    \"${mod}\": {\"services\", \"models\", \"auth\"},\n"
            ;;
        services|service)
            IMPORT_RULES="${IMPORT_RULES}    \"${mod}\": {\"db\", \"models\"},\n"
            ;;
        db|database|repo|repositories)
            IMPORT_RULES="${IMPORT_RULES}    \"${mod}\": set(),  # leaf layer\n"
            ;;
        models|schemas|types)
            IMPORT_RULES="${IMPORT_RULES}    \"${mod}\": set(),  # leaf layer\n"
            ;;
        auth|middleware)
            IMPORT_RULES="${IMPORT_RULES}    \"${mod}\": {\"db\", \"models\"},\n"
            ;;
        agent|ai)
            IMPORT_RULES="${IMPORT_RULES}    \"${mod}\": {\"services\", \"db\"},\n"
            ;;
        *)
            IMPORT_RULES="${IMPORT_RULES}    \"${mod}\": {\"services\", \"db\"},\n"
            ;;
    esac
done

# ─── Apply to AGENTS.md ──────────────────────────────────────────────

echo -e "${BOLD}Generating AGENTS.md...${NC}"

cd "$ROOT_DIR"

sed -i \
    -e "s|{{PROJECT_NAME}}|${PROJECT_NAME}|g" \
    -e "s|{{PROJECT_DESCRIPTION}}|${PROJECT_DESC}|g" \
    -e "s|{{BACKEND_STACK}}|${BACKEND_STACK}|g" \
    -e "s|{{FRONTEND_STACK}}|${FRONTEND_STACK}|g" \
    -e "s|{{DATABASE}}|${DATABASE}|g" \
    -e "s|{{AUTH}}|JWT / OAuth 2.0|g" \
    -e "s|{{AI_STACK}}|Configure your AI/ML stack|g" \
    -e "s|{{INFRA_STACK}}|${INFRA_STACK}|g" \
    -e "s|{{LINT_CMD}}|${LINT_CMD}|g" \
    -e "s|{{FORMAT_CMD}}|${FORMAT_CMD}|g" \
    -e "s|{{TEST_CMD}}|${TEST_CMD}|g" \
    -e "s|{{FRONTEND_LINT_CMD}}|${FRONTEND_LINT_CMD}|g" \
    -e "s|{{FRONTEND_FORMAT_CMD}}|${FRONTEND_FORMAT_CMD}|g" \
    -e "s|{{FRONTEND_BUILD_CMD}}|${FRONTEND_BUILD_CMD}|g" \
    -e "s|{{DEPLOY_CMD}}|${DEPLOY_CMD}|g" \
    -e "s|{{INFRA_CMD}}|${INFRA_CMD}|g" \
    -e "s|{{BACKEND_LANG}}|${BACKEND_LANG}|g" \
    -e "s|{{BACKEND_CONVENTIONS}}|${BACKEND_CONVENTIONS}|g" \
    -e "s|{{FRONTEND_LANG}}|TypeScript|g" \
    -e "s|{{FRONTEND_CONVENTIONS}}|camelCase functions/vars, PascalCase components, prettier format|g" \
    -e "s|{{API_ROUTE_CONVENTION}}|/api/resource-name (kebab-case paths)|g" \
    -e "s|{{DB_NAMING_CONVENTION}}|${DB_NAMING}|g" \
    -e "s|{{DB_LAYER}}|${DB_LAYER}|g" \
    -e "s|{{AI_LAYER}}|${AI_LAYER}|g" \
    -e "s|{{LAYER_1}}|backend|g" \
    AGENTS.md

# Replace the LAYER_DEPS block
python3 -c "
import re
content = open('AGENTS.md').read()
deps = '''$(echo -e "$LAYER_DEPS")'''
content = content.replace('{{LAYER_DEPS}}', deps.strip())
# Fill in remaining placeholders with sensible defaults
content = content.replace('{{PRINCIPLE_4}}', 'Data scoped by tenant')
content = content.replace('{{PRINCIPLE_4_DESC}}', 'all data access scoped by user/tenant ID. No cross-tenant access.')
content = content.replace('{{PRINCIPLE_5}}', 'Config from environment')
content = content.replace('{{PRINCIPLE_5_DESC}}', 'all config via settings module. No os.environ in business logic.')
content = content.replace('{{PRINCIPLE_6}}', 'API errors are structured')
content = content.replace('{{PRINCIPLE_6_DESC}}', 'return JSON error responses with error code, message, and details.')
content = content.replace('{{PROJECT_STRUCTURE}}', 'backend/\\n  main.py\\n  config.py\\n  ' + '/\\n  '.join('${MODULES_INPUT}'.split(',')) + '/\\nfrontend/\\nscripts/\\ndocs/')
open('AGENTS.md', 'w').write(content)
" 2>/dev/null || echo "  (Python not available for placeholder cleanup — edit AGENTS.md manually)"

echo -e "  ${GREEN}Done${NC}"

# ─── Apply to check_imports.py ────────────────────────────────────────

echo -e "${BOLD}Generating check_imports.py rules...${NC}"

if [ "$BACKEND_CHOICE" = "1" ]; then
    python3 -c "
content = open('scripts/check_imports.py').read()
old_rules = '''RULES: dict[str, set[str]] = {
    # \"module_name\": {\"allowed_import_1\", \"allowed_import_2\"},
    #
    # Example for a typical backend:
    # \"routers\":  {\"services\", \"models\", \"auth\"},
    # \"services\": {\"db\", \"models\"},
    # \"db\":       set(),  # leaf layer — no internal imports allowed
    # \"models\":   set(),  # leaf layer
    # \"auth\":     {\"db\", \"models\"},
    # \"agent\":    {\"services\", \"db\"},
}'''
new_rules = '''RULES: dict[str, set[str]] = {
$(echo -e "$IMPORT_RULES")}'''
content = content.replace(old_rules, new_rules)
open('scripts/check_imports.py', 'w').write(content)
" 2>/dev/null || echo "  (Edit scripts/check_imports.py manually)"
fi

echo -e "  ${GREEN}Done${NC}"

# ─── Apply to check_architecture.py ──────────────────────────────────

echo -e "${BOLD}Configuring check_architecture.py...${NC}"

if [ -n "$DB_IMPORT_PATTERN" ] && [ "$BACKEND_CHOICE" = "1" ]; then
    python3 -c "
content = open('scripts/check_architecture.py').read()
content = content.replace('DB_MODULE = \"db\"', 'DB_MODULE = \"${DB_LAYER}\"')
content = content.replace(
    'DB_IMPORT_PATTERNS: list[str] = [\n    # \"google.cloud.firestore\",\n    # \"sqlalchemy\",\n    # \"pymongo\",\n    # \"prisma\",\n]',
    'DB_IMPORT_PATTERNS: list[str] = [\n    \"${DB_IMPORT_PATTERN}\",\n]'
)
# Set testable modules
modules = '${MODULES_INPUT}'.split(',')
testable = [m.strip() for m in modules if m.strip() not in ('models', 'schemas', 'types')]
testable_str = ', '.join(['\"' + m + '\"' for m in testable])
content = content.replace(
    'TESTABLE_MODULES: set[str] = {\n    # \"services\",\n    # \"db\",\n    # \"agent\",\n}',
    'TESTABLE_MODULES: set[str] = {\n    ' + testable_str + ',\n}'
)
open('scripts/check_architecture.py', 'w').write(content)
" 2>/dev/null || echo "  (Edit scripts/check_architecture.py manually)"
fi

echo -e "  ${GREEN}Done${NC}"

# ─── Make scripts executable ──────────────────────────────────────────

echo -e "${BOLD}Making scripts executable...${NC}"
chmod +x scripts/*.sh scripts/*.py 2>/dev/null || true
echo -e "  ${GREEN}Done${NC}"

# ─── Run the internal setup check ─────────────────────────────────────

echo ""
echo -e "${BOLD}Running harness verification...${NC}"
echo ""
bash scripts/setup.sh

echo ""
echo "==========================================="
echo -e " ${GREEN}${BOLD}Setup Complete!${NC}"
echo "==========================================="
echo ""
echo "Your harness is configured for: ${PROJECT_NAME}"
echo ""
echo "  Backend:  ${BACKEND_STACK}"
echo "  Frontend: ${FRONTEND_STACK}"
echo "  Database: ${DATABASE}"
echo "  Infra:    ${INFRA_STACK}"
echo ""
echo "Next steps:"
echo "  1. Review AGENTS.md and fill in any remaining {{}} placeholders"
echo "  2. Create your backend/ and frontend/ directories"
echo "  3. Run: ./scripts/validate.sh"
echo ""
echo "The harness will auto-detect your code and run the appropriate gates."
