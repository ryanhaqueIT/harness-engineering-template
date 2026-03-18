#!/usr/bin/env bash
# install.sh — Install Tier 1 (Code Quality) gates into a target repo.
#
# Usage:
#   bash tiers/t1-code-quality/install.sh /path/to/target-repo
#
# What it does:
#   1. Detects Python / Next.js stacks
#   2. Installs missing tools, copies org default configs where needed (2x2 matrix)
#   3. Copies validate-t1.sh, ratchet-t1.py, post-edit.sh into .harness/
#   4. Sets up pre-commit git hook via symlink
#   5. Creates .harness/manifest.json
#   6. Auto-baselines the ratchet
#   7. Updates .gitignore

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ─── Resolve paths ────────────────────────────────

HARNESS_TEMPLATE_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
T1_DIR="$HARNESS_TEMPLATE_DIR/tiers/t1-code-quality"
TARGET="${1:-$(pwd)}"

if [ ! -d "$TARGET" ]; then
    echo -e "${RED}Error: Target directory does not exist: $TARGET${NC}"
    exit 1
fi

if [ ! -d "$TARGET/.git" ]; then
    echo -e "${RED}Error: Target is not a git repository: $TARGET${NC}"
    exit 1
fi

echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
echo -e "${BOLD} Tier 1: Code Quality — Install${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
echo ""
echo -e "  Template: ${CYAN}$HARNESS_TEMPLATE_DIR${NC}"
echo -e "  Target:   ${CYAN}$TARGET${NC}"
echo ""

# ─── Idempotent file copy ─────────────────────────

COPIED=0
SKIPPED=0

copy_file() {
    local src="$1"
    local dst="$2"
    local label="$3"

    if [ ! -f "$src" ]; then
        echo -e "  ${RED}MISS${NC}  $label (source not found)"
        return
    fi

    mkdir -p "$(dirname "$dst")"

    if [ -f "$dst" ]; then
        echo -e "  ${YELLOW}SKIP${NC}  $label (already exists)"
        SKIPPED=$((SKIPPED + 1))
    else
        cp "$src" "$dst"
        echo -e "  ${GREEN}COPY${NC}  $label"
        COPIED=$((COPIED + 1))
    fi
}

copy_config() {
    local src="$1"
    local dst="$2"
    local label="$3"

    if [ -f "$dst" ]; then
        echo -e "  ${DIM}KEEP${NC}  $label (repo has its own config)"
        return
    fi

    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    echo -e "  ${GREEN}COPY${NC}  $label (org default)"
    COPIED=$((COPIED + 1))
}

# ═══════════════════════════════════════════════════
# Step 1: Detect stacks
# ═══════════════════════════════════════════════════

echo -e "${BOLD}Step 1: Detecting stacks...${NC}"

HAS_PYTHON=false
HAS_NEXTJS=false

# Placeholder: repo analyzer
if [ -n "${REPO_ANALYZER_OUTPUT:-}" ] && [ -f "$REPO_ANALYZER_OUTPUT" ]; then
    echo -e "  Using repo analyzer: $REPO_ANALYZER_OUTPUT"
else
    # Fallback: file presence
    if [ -f "$TARGET/pyproject.toml" ] || [ -f "$TARGET/setup.py" ] || \
       find "$TARGET" -maxdepth 3 -name "*.py" -not -path "*/.venv/*" -not -path "*/node_modules/*" -not -path "*/.harness/*" 2>/dev/null | head -1 | grep -q .; then
        HAS_PYTHON=true
    fi
    if [ -f "$TARGET/package.json" ]; then
        HAS_NEXTJS=true
    fi
fi

echo -e "  Python:  $HAS_PYTHON"
echo -e "  Next.js: $HAS_NEXTJS"
echo ""

# ═══════════════════════════════════════════════════
# Step 2: Install tools + configs (2x2 matrix)
# ═══════════════════════════════════════════════════

echo -e "${BOLD}Step 2: Tools & configs (2x2 matrix)...${NC}"

# ─── Python tools ─────────────────────────────────

if [ "$HAS_PYTHON" = true ]; then
    # ruff
    if ! command -v ruff &>/dev/null; then
        echo -e "  ${CYAN}INSTALL${NC} ruff (via pip)"
        pip3 install ruff --quiet 2>/dev/null || python3 -m pip install ruff --quiet 2>/dev/null || echo -e "  ${YELLOW}WARN${NC} Could not install ruff. Install manually: pip install ruff"
    else
        echo -e "  ${DIM}OK${NC}     ruff (already installed)"
    fi
    # ruff config — check for any ruff config in target
    if [ ! -f "$TARGET/ruff.toml" ] && [ ! -f "$TARGET/pyproject.toml" ] || \
       ([ -f "$TARGET/pyproject.toml" ] && ! grep -q '\[tool\.ruff\]' "$TARGET/pyproject.toml" 2>/dev/null && [ ! -f "$TARGET/ruff.toml" ] && [ ! -f "$TARGET/.ruff.toml" ]); then
        copy_config "$T1_DIR/configs/ruff.toml" "$TARGET/ruff.toml" "ruff.toml"
    else
        echo -e "  ${DIM}KEEP${NC}  ruff config (repo has its own)"
    fi

    # pyright
    if ! command -v pyright &>/dev/null; then
        echo -e "  ${CYAN}INSTALL${NC} pyright (via pip)"
        pip3 install pyright --quiet 2>/dev/null || python3 -m pip install pyright --quiet 2>/dev/null || echo -e "  ${YELLOW}WARN${NC} Could not install pyright. Install manually: pip install pyright"
    else
        echo -e "  ${DIM}OK${NC}     pyright (already installed)"
    fi
    # pyright config
    if [ ! -f "$TARGET/pyrightconfig.json" ]; then
        copy_config "$T1_DIR/configs/pyrightconfig.json" "$TARGET/pyrightconfig.json" "pyrightconfig.json"
    else
        echo -e "  ${DIM}KEEP${NC}  pyrightconfig.json (repo has its own)"
    fi
fi

# ─── Next.js tools ────────────────────────────────

if [ "$HAS_NEXTJS" = true ]; then
    cd "$TARGET"

    # eslint
    if [ ! -d "$TARGET/node_modules/eslint" ]; then
        echo -e "  ${CYAN}INSTALL${NC} eslint (via npm)"
        npm install --save-dev eslint @eslint/js --quiet 2>/dev/null || echo -e "  ${YELLOW}WARN${NC} Could not install eslint"
    else
        echo -e "  ${DIM}OK${NC}     eslint (already installed)"
    fi
    # eslint config
    HAS_ESLINT_CONFIG=false
    for f in eslint.config.* .eslintrc* .eslintrc; do
        if [ -f "$TARGET/$f" ]; then
            HAS_ESLINT_CONFIG=true
            break
        fi
    done
    if [ "$HAS_ESLINT_CONFIG" = false ]; then
        copy_config "$T1_DIR/configs/eslint.config.mjs" "$TARGET/eslint.config.mjs" "eslint.config.mjs"
    else
        echo -e "  ${DIM}KEEP${NC}  eslint config (repo has its own)"
    fi

    # prettier
    if [ ! -d "$TARGET/node_modules/prettier" ]; then
        echo -e "  ${CYAN}INSTALL${NC} prettier (via npm)"
        npm install --save-dev prettier --quiet 2>/dev/null || echo -e "  ${YELLOW}WARN${NC} Could not install prettier"
    else
        echo -e "  ${DIM}OK${NC}     prettier (already installed)"
    fi
    # prettier config
    HAS_PRETTIER_CONFIG=false
    for f in prettier.config.* .prettierrc*; do
        if [ -f "$TARGET/$f" ]; then
            HAS_PRETTIER_CONFIG=true
            break
        fi
    done
    if [ "$HAS_PRETTIER_CONFIG" = false ]; then
        copy_config "$T1_DIR/configs/prettier.config.mjs" "$TARGET/prettier.config.mjs" "prettier.config.mjs"
    else
        echo -e "  ${DIM}KEEP${NC}  prettier config (repo has its own)"
    fi

    # typescript
    if [ ! -d "$TARGET/node_modules/typescript" ]; then
        echo -e "  ${CYAN}INSTALL${NC} typescript (via npm)"
        npm install --save-dev typescript --quiet 2>/dev/null || echo -e "  ${YELLOW}WARN${NC} Could not install typescript"
    else
        echo -e "  ${DIM}OK${NC}     typescript (already installed)"
    fi
    # tsconfig
    if [ ! -f "$TARGET/tsconfig.json" ]; then
        copy_config "$T1_DIR/configs/tsconfig.base.json" "$TARGET/tsconfig.json" "tsconfig.json"
    else
        echo -e "  ${DIM}KEEP${NC}  tsconfig.json (repo has its own)"
    fi

    cd - > /dev/null
fi

echo ""

# ═══════════════════════════════════════════════════
# Step 3: Copy harness files
# ═══════════════════════════════════════════════════

echo -e "${BOLD}Step 3: Copying harness files...${NC}"

mkdir -p "$TARGET/.harness/hooks"

copy_file "$T1_DIR/validate-t1.sh" "$TARGET/.harness/validate-t1.sh" ".harness/validate-t1.sh"
chmod +x "$TARGET/.harness/validate-t1.sh" 2>/dev/null || true

copy_file "$T1_DIR/ratchet-t1.py" "$TARGET/.harness/ratchet-t1.py" ".harness/ratchet-t1.py"

copy_file "$T1_DIR/post-edit.sh" "$TARGET/.harness/hooks/post-edit.sh" ".harness/hooks/post-edit.sh"
chmod +x "$TARGET/.harness/hooks/post-edit.sh" 2>/dev/null || true

echo ""

# ═══════════════════════════════════════════════════
# Step 4: Set up git hook
# ═══════════════════════════════════════════════════

echo -e "${BOLD}Step 4: Setting up pre-commit hook...${NC}"

# Create the pre-commit wrapper
cat > "$TARGET/.harness/hooks/pre-commit" << 'HOOK'
#!/usr/bin/env bash
# Pre-commit hook: runs T1 validation gates before allowing commit.
# Installed by harness-engineering-template T1 install.

REPO_ROOT="$(git rev-parse --show-toplevel)"
echo "Running T1 code quality gates..."
bash "$REPO_ROOT/.harness/validate-t1.sh"
HOOK

chmod +x "$TARGET/.harness/hooks/pre-commit"

# Symlink into .git/hooks/
if [ -L "$TARGET/.git/hooks/pre-commit" ]; then
    echo -e "  ${YELLOW}SKIP${NC}  pre-commit hook (symlink already exists)"
elif [ -f "$TARGET/.git/hooks/pre-commit" ]; then
    echo -e "  ${YELLOW}SKIP${NC}  pre-commit hook (existing hook found — not overwriting)"
    echo -e "  ${DIM}       To use harness hook: rm .git/hooks/pre-commit && ln -s ../../.harness/hooks/pre-commit .git/hooks/pre-commit${NC}"
else
    ln -s ../../.harness/hooks/pre-commit "$TARGET/.git/hooks/pre-commit"
    echo -e "  ${GREEN}LINK${NC}  .git/hooks/pre-commit → .harness/hooks/pre-commit"
fi

echo ""

# ═══════════════════════════════════════════════════
# Step 5: Create manifest
# ═══════════════════════════════════════════════════

echo -e "${BOLD}Step 5: Creating manifest...${NC}"

MANIFEST="$TARGET/.harness/manifest.json"

cat > "$MANIFEST" << EOF
{
  "version": 1,
  "tiers": {
    "t1-code-quality": {
      "installed": true,
      "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
      "stacks": {
        "python": $HAS_PYTHON,
        "nextjs": $HAS_NEXTJS
      }
    }
  }
}
EOF

echo -e "  ${GREEN}WRITE${NC} .harness/manifest.json"
echo ""

# ═══════════════════════════════════════════════════
# Step 6: Auto-baseline ratchet
# ═══════════════════════════════════════════════════

echo -e "${BOLD}Step 6: Auto-baselining ratchet...${NC}"

if [ -f "$TARGET/.harness/t1-baseline.json" ]; then
    echo -e "  ${YELLOW}SKIP${NC}  Baseline already exists"
else
    cd "$TARGET"
    python3 "$TARGET/.harness/ratchet-t1.py" || echo -e "  ${YELLOW}WARN${NC} Ratchet baseline creation had issues (non-fatal)"
    cd - > /dev/null
fi

echo ""

# ═══════════════════════════════════════════════════
# Step 7: Update .gitignore
# ═══════════════════════════════════════════════════

echo -e "${BOLD}Step 7: Updating .gitignore...${NC}"

GITIGNORE="$TARGET/.gitignore"
touch "$GITIGNORE"

add_gitignore() {
    local entry="$1"
    if ! grep -qxF "$entry" "$GITIGNORE" 2>/dev/null; then
        echo "$entry" >> "$GITIGNORE"
        echo -e "  ${GREEN}ADD${NC}   $entry"
    fi
}

add_gitignore ".harness/t1-baseline.json"
add_gitignore ".harness/instance-metadata.json"

echo ""

# ═══════════════════════════════════════════════════
# Done
# ═══════════════════════════════════════════════════

echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN} T1 Code Quality installed!${NC}"
echo -e "  Files copied: $COPIED | Skipped: $SKIPPED"
echo ""
echo -e "  Next steps:"
echo -e "    1. Run validation:  ${CYAN}bash .harness/validate-t1.sh${NC}"
echo -e "    2. Check ratchet:   ${CYAN}python3 .harness/ratchet-t1.py${NC}"
echo -e "    3. Commit normally — pre-commit hook will run T1 gates"
echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
