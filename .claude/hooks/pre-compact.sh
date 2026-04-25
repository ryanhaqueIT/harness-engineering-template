#!/usr/bin/env bash
# PreCompact hook: Save continuation snapshot before context compression.
#
# This hook fires as an AGENT-TYPE hook — Claude synthesizes current state
# into .harness/continuation.md before context is lost.
#
# The SessionStart logic (in pre-commit.sh or a separate hook) reads this
# file on recovery and injects it into context if fresh (< 2 hours old).
#
# This is the single most valuable recovery mechanism for long builds.
# Without it, context compaction causes the agent to restart from scratch.

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
CONTINUATION="${REPO_ROOT}/.harness/continuation.md"
HARNESS_DIR="${REPO_ROOT}/.harness"

# Ensure .harness directory exists
mkdir -p "$HARNESS_DIR"

# Write the continuation snapshot prompt
# This will be executed as an agent-type hook — the LLM reads this prompt
# and writes the continuation file.
cat << 'PROMPT'
You are about to lose your conversation context due to compaction.
Write a continuation snapshot to .harness/continuation.md that will help you
resume work after context is restored.

Read the current state of the project and write the following sections:

## Current State
- What feature/task are you working on?
- What is the overall progress (X of Y tasks complete)?
- What branch are you on?

## Work in Progress
- Which files are you actively editing?
- What is the state of each file (complete, partial, not started)?
- What specific function/section were you working on?

## Pending Decisions
- Any unresolved questions that need user input?
- Any design decisions you were considering?

## Next Steps
1. What should happen immediately after recovery?
2. What is the next task in sequence?
3. What commands need to be run?

## Correction Summary
List any recurring errors or violations seen during this session:
- What patterns triggered gate failures?
- What fixes were applied?
- What should be avoided going forward?

IMPORTANT: Add a timestamp line at the top:
Snapshot: {current ISO 8601 timestamp}

Write this to .harness/continuation.md using the Write tool.
PROMPT
