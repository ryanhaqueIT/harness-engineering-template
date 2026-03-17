#!/usr/bin/env bash
# review_pr.sh — Multi-agent PR review loop (harness engineering Layer 6).
#
# Runs mechanical gates (validate.sh + heuristic checks) then optionally
# invokes Claude Code for AI-powered review.
#
# Usage:
#   ./scripts/review_pr.sh                  # Review current branch diff vs main
#   ./scripts/review_pr.sh feature/foo      # Review a specific branch
#   ./scripts/review_pr.sh --pr 42          # Review PR #42 (requires gh CLI)
#   ./scripts/review_pr.sh --ai             # Include Claude Code AI review
#
# Exit codes:
#   0 — LGTM, all checks pass
#   1 — Issues found, review the output

set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

REPO_ROOT="$(git rev-parse --show-toplevel)"
ISSUES=0
WARNINGS=0
BASE_BRANCH="main"
TARGET_BRANCH=""
PR_NUMBER=""
AI_REVIEW=false

# ─── Parse arguments ────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case "$1" in
        --pr)
            PR_NUMBER="$2"
            shift 2
            ;;
        --ai)
            AI_REVIEW=true
            shift
            ;;
        --base)
            BASE_BRANCH="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: review_pr.sh [branch|--pr NUMBER] [--ai] [--base BRANCH]"
            echo ""
            echo "Options:"
            echo "  branch        Branch to review (default: current branch)"
            echo "  --pr NUMBER   Review a GitHub PR by number"
            echo "  --ai          Include Claude Code AI review"
            echo "  --base BRANCH Base branch to diff against (default: main)"
            exit 0
            ;;
        *)
            TARGET_BRANCH="$1"
            shift
            ;;
    esac
done

# ─── Resolve the diff ───────────────────────────────────────────────────

echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${CYAN} PR Review — harness engineering Layer 6${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo ""

if [ -n "$PR_NUMBER" ]; then
    echo "Reviewing PR #${PR_NUMBER}..."
    if ! command -v gh &>/dev/null; then
        echo -e "${RED}Error: gh CLI required for --pr mode. Install from https://cli.github.com${NC}"
        exit 1
    fi
    DIFF=$(gh pr diff "$PR_NUMBER" 2>/dev/null)
    if [ -z "$DIFF" ]; then
        echo -e "${RED}Error: Could not fetch diff for PR #${PR_NUMBER}${NC}"
        exit 1
    fi
    CHANGED_FILES=$(echo "$DIFF" | grep '^diff --git' | sed 's|.*b/||' | sort)
elif [ -n "$TARGET_BRANCH" ]; then
    echo "Reviewing branch: ${TARGET_BRANCH} against ${BASE_BRANCH}..."
    DIFF=$(git diff "origin/${BASE_BRANCH}...${TARGET_BRANCH}" 2>/dev/null)
    CHANGED_FILES=$(git diff --name-only "origin/${BASE_BRANCH}...${TARGET_BRANCH}" 2>/dev/null)
else
    echo "Reviewing current branch against ${BASE_BRANCH}..."
    DIFF=$(git diff "origin/${BASE_BRANCH}...HEAD" 2>/dev/null)
    if [ -z "$DIFF" ]; then
        DIFF=$(git diff HEAD 2>/dev/null)
    fi
    if [ -z "$DIFF" ]; then
        DIFF=$(git diff 2>/dev/null)
    fi
    CHANGED_FILES=$(echo "$DIFF" | grep '^diff --git' | sed 's|.*b/||' | sort)
fi

if [ -z "$DIFF" ]; then
    echo -e "${YELLOW}No diff found. Nothing to review.${NC}"
    exit 0
fi

FILE_COUNT=$(echo "$CHANGED_FILES" | grep -c . || true)
echo "Changed files: ${FILE_COUNT}"
echo ""

# ─── Gate 1: validate.sh ────────────────────────────────────────────────

echo -e "── ${CYAN}Gate 1: validate.sh${NC}"
if [ -f "${REPO_ROOT}/scripts/validate.sh" ]; then
    if bash "${REPO_ROOT}/scripts/validate.sh" > /tmp/validate_output.txt 2>&1; then
        echo -e "   ${GREEN}PASS — all validate.sh gates clear${NC}"
    else
        echo -e "   ${RED}FAIL — validate.sh returned non-zero${NC}"
        tail -5 /tmp/validate_output.txt | sed 's/^/   /'
        ISSUES=$((ISSUES + 1))
    fi
else
    echo -e "   ${YELLOW}SKIP — scripts/validate.sh not found${NC}"
fi
echo ""

# ─── Gate 2: Golden principles scan on changed files ────────────────────

echo -e "── ${CYAN}Gate 2: Golden principles (changed files only)${NC}"
while IFS= read -r file; do
    [ -z "$file" ] && continue
    [ ! -f "${REPO_ROOT}/${file}" ] && continue

    # Check for print() in Python files
    if [[ "$file" == *.py ]]; then
        PRINTS=$(grep -n 'print(' "${REPO_ROOT}/${file}" 2>/dev/null | grep -v '# noqa' | grep -v 'test_' || true)
        if [ -n "$PRINTS" ]; then
            echo -e "   ${RED}ISSUE: ${file} — print() found (use logger instead)${NC}"
            echo "$PRINTS" | head -3 | sed 's/^/      /'
            ISSUES=$((ISSUES + 1))
        fi

        # Check for bare except
        BARE_EXCEPT=$(grep -n 'except:' "${REPO_ROOT}/${file}" 2>/dev/null || true)
        if [ -n "$BARE_EXCEPT" ]; then
            echo -e "   ${RED}ISSUE: ${file} — bare except: found (catch specific exceptions)${NC}"
            echo "$BARE_EXCEPT" | head -3 | sed 's/^/      /'
            ISSUES=$((ISSUES + 1))
        fi
    fi

    # Check for hardcoded secrets (all file types)
    SECRETS=$(grep -nE '(AKIA[A-Z0-9]{16}|sk-[a-zA-Z0-9]{40,}|BEGIN (RSA |EC )?PRIVATE KEY)' "${REPO_ROOT}/${file}" 2>/dev/null || true)
    if [ -n "$SECRETS" ]; then
        echo -e "   ${RED}CRITICAL: ${file} — possible hardcoded secret${NC}"
        ISSUES=$((ISSUES + 1))
    fi
done <<< "$CHANGED_FILES"

if [ "$ISSUES" -eq 0 ]; then
    echo -e "   ${GREEN}PASS — no golden principle violations in changed files${NC}"
fi
echo ""

# ─── Gate 3: Test coverage check ────────────────────────────────────────

echo -e "── ${CYAN}Gate 3: Test coverage${NC}"
MISSING_TESTS=0
while IFS= read -r file; do
    [ -z "$file" ] && continue

    # Only check source files, skip tests/configs/docs
    if [[ "$file" == *.py ]] && [[ "$file" != *test_* ]] && [[ "$file" != *__init__* ]] && [[ "$file" == backend/* ]] && [[ "$file" != *tests/* ]]; then
        # Derive expected test path
        BASENAME=$(basename "$file" .py)
        EXPECTED_TEST="backend/tests/test_${BASENAME}.py"

        # Also check in subdirectories
        SUBDIR=$(dirname "$file" | sed 's|^backend/||')
        EXPECTED_TEST_ALT="backend/tests/${SUBDIR}/test_${BASENAME}.py"

        if [ ! -f "${REPO_ROOT}/${EXPECTED_TEST}" ] && [ ! -f "${REPO_ROOT}/${EXPECTED_TEST_ALT}" ]; then
            echo -e "   ${YELLOW}WARNING: ${file} — no matching test file found${NC}"
            echo "      Expected: ${EXPECTED_TEST} or ${EXPECTED_TEST_ALT}"
            WARNINGS=$((WARNINGS + 1))
            MISSING_TESTS=$((MISSING_TESTS + 1))
        fi
    fi
done <<< "$CHANGED_FILES"

if [ "$MISSING_TESTS" -eq 0 ]; then
    echo -e "   ${GREEN}PASS — all changed source files have test mirrors${NC}"
fi
echo ""

# ─── Gate 4: File size check ────────────────────────────────────────────

echo -e "── ${CYAN}Gate 4: Architecture (file size)${NC}"
while IFS= read -r file; do
    [ -z "$file" ] && continue
    [ ! -f "${REPO_ROOT}/${file}" ] && continue

    if [[ "$file" == *.py ]] || [[ "$file" == *.ts ]] || [[ "$file" == *.tsx ]]; then
        LINE_COUNT=$(wc -l < "${REPO_ROOT}/${file}" 2>/dev/null || echo 0)
        if [ "$LINE_COUNT" -gt 300 ]; then
            echo -e "   ${YELLOW}WARNING: ${file} — ${LINE_COUNT} lines (threshold: 300). Consider splitting.${NC}"
            WARNINGS=$((WARNINGS + 1))
        fi
    fi
done <<< "$CHANGED_FILES"

echo -e "   ${GREEN}DONE${NC}"
echo ""

# ─── Gate 5: Import boundary spot check ─────────────────────────────────

echo -e "── ${CYAN}Gate 5: Import boundaries (changed files)${NC}"
if [ -f "${REPO_ROOT}/scripts/check_imports.py" ]; then
    if python "${REPO_ROOT}/scripts/check_imports.py" > /tmp/imports_output.txt 2>&1; then
        echo -e "   ${GREEN}PASS — import boundaries clean${NC}"
    else
        echo -e "   ${RED}FAIL — import boundary violations${NC}"
        cat /tmp/imports_output.txt | tail -10 | sed 's/^/      /'
        ISSUES=$((ISSUES + 1))
    fi
else
    echo -e "   ${YELLOW}SKIP — scripts/check_imports.py not found${NC}"
fi
echo ""

# ─── Gate 6: AI Review (optional) ───────────────────────────────────────

if [ "$AI_REVIEW" = true ]; then
    echo -e "── ${CYAN}Gate 6: Claude Code AI Review${NC}"
    if command -v claude &>/dev/null && [ -n "${ANTHROPIC_API_KEY:-}" ]; then
        # Gather context
        CONTEXT=""
        [ -f "${REPO_ROOT}/AGENTS.md" ] && CONTEXT="AGENTS.md:\n$(cat "${REPO_ROOT}/AGENTS.md")\n\n"
        [ -f "${REPO_ROOT}/docs/QUALITY_SCORE.md" ] && CONTEXT="${CONTEXT}QUALITY_SCORE.md:\n$(cat "${REPO_ROOT}/docs/QUALITY_SCORE.md")\n\n"

        echo "$DIFF" | head -c 80000 > /tmp/review_diff.txt

        claude --print "You are a code reviewer. Review this diff against the project standards below.
For each issue: file:line | severity (critical/warning/info) | fix instruction.
If clean: say LGTM.

STANDARDS:
${CONTEXT}

DIFF:
$(cat /tmp/review_diff.txt)" > /tmp/ai_review.txt 2>/dev/null

        if [ -s /tmp/ai_review.txt ]; then
            echo ""
            cat /tmp/ai_review.txt | sed 's/^/   /'
        else
            echo -e "   ${YELLOW}AI review returned empty output${NC}"
        fi
    else
        echo -e "   ${YELLOW}SKIP — claude CLI not found or ANTHROPIC_API_KEY not set${NC}"
    fi
    echo ""
fi

# ─── Results ─────────────────────────────────────────────────────────────

echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo " Review Summary"
echo " Files reviewed: ${FILE_COUNT}"
echo " Issues:         ${ISSUES}"
echo " Warnings:       ${WARNINGS}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"

if [ "$ISSUES" -gt 0 ]; then
    echo -e "${RED}CHANGES REQUESTED — ${ISSUES} issue(s) must be fixed${NC}"
    exit 1
elif [ "$WARNINGS" -gt 0 ]; then
    echo -e "${YELLOW}APPROVED WITH NOTES — ${WARNINGS} warning(s) to consider${NC}"
    exit 0
else
    echo -e "${GREEN}LGTM — all checks pass${NC}"
    exit 0
fi
