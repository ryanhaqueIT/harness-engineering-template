#!/usr/bin/env bash
# Pre-commit hook: runs validate.sh before allowing commit.
# If validate.sh fails, the commit is blocked.
#
# This hook is invoked by Claude Code before any git commit.
# It enforces THE RULE: nothing gets committed until validate.sh exits 0.

set -euo pipefail

# Read hook input from stdin — only run validation on git commit commands
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
if ! echo "$COMMAND" | grep -q '^git commit'; then
    exit 0
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"

if [ ! -f "${REPO_ROOT}/scripts/validate.sh" ]; then
    echo "ERROR: scripts/validate.sh not found."
    echo "Run setup.sh to bootstrap the project first."
    exit 1
fi

echo "Running pre-commit validation gate..."
bash "${REPO_ROOT}/scripts/validate.sh"
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "COMMIT BLOCKED: validate.sh exited with code $EXIT_CODE"
    echo "Fix all failures above, then try again."
    exit $EXIT_CODE
fi
