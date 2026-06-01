#!/usr/bin/env bash
# Shell-guard: PreToolUse Bash DENYLIST hook.
#
# Reads a PreToolUse JSON payload on stdin, extracts the proposed shell
# command, and blocks (exit 2) ONLY when it matches a conservative list of
# unambiguously destructive patterns. Everything else is allowed (exit 0).
#
# Denylist philosophy: favor false-negatives over false-positives. It is far
# worse to block legitimate dev work than to miss one exotic foot-gun, so the
# patterns below are deliberately narrow and target the canonical disasters.
#
# Bulletproof version: works without jq, handles edge cases.

set -euo pipefail

# Read hook input from stdin.
INPUT=$(cat)

# Parse the command: try jq first, fall back to grep.
COMMAND=""
if command -v jq &>/dev/null; then
    COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
else
    # Fallback: pull the "command" field out of the raw JSON with sed.
    # (grep -P / PCRE is not portable across locales, so we avoid it here.)
    COMMAND=$(echo "$INPUT" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\(\(\\.\|[^"\\]\)*\)".*/\1/p' | head -1 || true)
    # Un-escape the common JSON escapes so our regexes see real characters.
    COMMAND=${COMMAND//\\\"/\"}
    COMMAND=${COMMAND//\\\\/\\}
fi

# Nothing to inspect — allow.
if [ -z "$COMMAND" ]; then
    exit 0
fi

# block <reason> — print why and exit 2 (deny).
block() {
    echo "SHELL-GUARD BLOCKED: $1" >&2
    echo "  Command: $COMMAND" >&2
    echo "  This command matches a destructive-pattern denylist." >&2
    echo "  If you are certain this is safe, run it outside the agent." >&2
    exit 2
}

# Case-insensitive matching for the rules below.
shopt -s nocasematch

# 1. rm with both recursive and force flags (in any order) targeting a
#    dangerous root: filesystem root, root glob, home, parent dir, or a
#    top-level system directory. Relative paths (./build, node_modules) are
#    intentionally NOT matched.
#    Matches: rm -rf /, rm -fr /*, rm -rf ~, rm -rf .., sudo rm -rf /usr
_RM_FLAGS='-[a-z]*r[a-z]*f[a-z]*|-[a-z]*f[a-z]*r[a-z]*'
_SYS_DIRS='/usr|/var|/etc|/bin|/sbin|/lib|/lib64|/boot|/opt|/root|/home|/dev|/proc|/sys'
if [[ "$COMMAND" =~ rm[[:space:]]+($_RM_FLAGS)[[:space:]]+(-[a-z]*[[:space:]]+)*(/|/\*|~|\.\.)([[:space:]]|/|$) ]]; then
    block "recursive force-remove of a critical path (/, ~, .., or root glob)"
fi
if [[ "$COMMAND" =~ rm[[:space:]]+($_RM_FLAGS)[[:space:]]+(-[a-z]*[[:space:]]+)*($_SYS_DIRS)([[:space:]]|/|$) ]]; then
    block "recursive force-remove of a system directory"
fi

# 2. Fork bomb.
if [[ "$COMMAND" =~ :\(\)\{[[:space:]]*:\|:\&[[:space:]]*\}\;: ]]; then
    block "fork bomb"
fi

# 3. Remote script piped straight into a shell (curl/wget ... | sh/bash).
if [[ "$COMMAND" =~ (curl|wget)[[:space:]].*\|[[:space:]]*(sudo[[:space:]]+)?(sh|bash|zsh) ]]; then
    block "piping a downloaded script directly into a shell"
fi

# 4. chmod -R 777 on root, or chmod 777 on a system path.
if [[ "$COMMAND" =~ chmod[[:space:]]+(-[a-z]*[[:space:]]+)*777[[:space:]]+(/|/etc|/bin|/usr|/var|/boot|/lib|/sbin) ]]; then
    block "chmod 777 on a system path"
fi
if [[ "$COMMAND" =~ chmod[[:space:]]+-[a-z]*r[a-z]*[[:space:]]+777[[:space:]]+/ ]]; then
    block "recursive chmod 777 starting at root"
fi

# 5. Raw disk destruction: dd onto a block device, mkfs, redirect into /dev/sd*.
if [[ "$COMMAND" =~ dd[[:space:]].*of=/dev/(sd|nvme|hd|vd|disk) ]]; then
    block "dd writing directly to a block device"
fi
if [[ "$COMMAND" =~ mkfs(\.[a-z0-9]+)?[[:space:]] ]]; then
    block "filesystem creation (mkfs) — will erase a device"
fi
if [[ "$COMMAND" =~ \>[[:space:]]*/dev/(sd|nvme|hd|vd|disk) ]]; then
    block "redirecting output onto a raw block device"
fi

# 6. Destructive git remote operations.
#    Force-push (--force / -f / leading-+ refspec) and hard reset against a remote.
if [[ "$COMMAND" =~ git[[:space:]]+push([[:space:]]+[^|]*)?[[:space:]](--force|-f)([[:space:]]|$) ]]; then
    block "git push --force can overwrite remote history"
fi
if [[ "$COMMAND" =~ git[[:space:]]+push[[:space:]]+[^|]*[[:space:]]\+[a-z] ]]; then
    block "git push with a '+' refspec force-overwrites the remote"
fi
if [[ "$COMMAND" =~ git[[:space:]]+reset[[:space:]]+--hard[[:space:]]+[a-z0-9._/-]*/ ]]; then
    block "git reset --hard onto a remote-tracking ref"
fi

# 7. find / ... -delete starting at the filesystem root.
if [[ "$COMMAND" =~ find[[:space:]]+/[[:space:]].*-delete ]]; then
    block "find starting at / with -delete will wipe the system"
fi

shopt -u nocasematch

# No denylist pattern matched — allow the command.
exit 0
