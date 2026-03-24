#!/usr/bin/env bash
# Pre-commit gate: blocks ALL git commits unless validate.sh passes.
# Two-layer defense: this Claude Code hook + .git/hooks/pre-commit.
#
# Bulletproof version: works without jq, handles edge cases.

set -euo pipefail

# Read hook input from stdin — only run validation on git commit commands
INPUT=$(cat)

# Parse command: try jq first, fallback to grep
COMMAND=""
if command -v jq &>/dev/null; then
    COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
else
    # Fallback: extract git commit from raw JSON input
    COMMAND=$(echo "$INPUT" | grep -oP '"command"\s*:\s*"([^"]*git commit[^"]*)"' | head -1 || true)
fi

# Only gate on commit commands
if ! echo "$COMMAND" | grep -q 'git commit'; then
    exit 0
fi

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
VALIDATE="${REPO_ROOT}/scripts/validate.sh"

if [ ! -f "$VALIDATE" ]; then
    echo "COMMIT BLOCKED: scripts/validate.sh not found." >&2
    echo "Run bootstrap to set up the harness first." >&2
    exit 2
fi

echo "Running pre-commit validation gate..."
if ! bash "$VALIDATE"; then
    echo "" >&2
    echo "============================================" >&2
    echo "  COMMIT BLOCKED: validate.sh failed." >&2
    echo "  Fix all issues above, then retry." >&2
    echo "  THE RULE: validate.sh must exit 0" >&2
    echo "  before every commit. No exceptions." >&2
    echo "============================================" >&2
    exit 2
fi
