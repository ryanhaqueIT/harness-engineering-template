End-to-end autonomous build. Takes a PRD or a prompt, walks PRD → spec QA → plan → seed → adversarial build → validate → fix (with loop detection) → review → commit. No human intervention required after invocation.

$ARGUMENTS may be:
- A path to a spec file: `docs/product-specs/foo.md` or `docs/exec-plans/active/foo.md`
- A natural-language goal: `"Add OAuth login with Google and GitHub"`
- Empty: resume an in-flight build

## Mental Model

`scripts/ship.py` is a finite state machine persisted to `.harness/ship_state.json`. Your job as the LLM is to:

1. Ask `ship.py` what state we are in.
2. Do the action that state requires (run a subagent, invoke a script, mark a feature).
3. Advance the state machine to the next state.
4. Loop until status is `done`, `escalated`, or `aborted`.

The state machine is the source of truth. The harness will not break if you crash mid-build — re-running `/ship` resumes from the saved state.

## MANDATORY Skill Invocations

Before running this command, invoke the relevant superpowers. They are not
suggestions — they enforce discipline the rest of the harness depends on:

| State entering | Skill to invoke first |
|----------------|------------------------|
| Any time you start /ship | `Skill("superpowers:using-superpowers")` |
| `building` | `Skill("superpowers:test-driven-development")` then `Skill("superpowers:subagent-driven-development")` |
| `fixing` (after first attempt) | `Skill("superpowers:systematic-debugging")` |
| `rescuing` | `Skill("codex:rescue")` for the parallel diagnosis |
| `adversarial_review` | `Skill("codex:rescue")` for the independent review |
| `committing` | `Skill("superpowers:verification-before-completion")` |

Skipping these is not a shortcut — it's how stuck builds happen.

## Workflow

### 0. Read the current state

```bash
python scripts/ship.py status
```

If `status: init`, start a new build with whatever was passed in `$ARGUMENTS`:

```bash
# Spec file
python scripts/ship.py start --prd <path>

# Inline goal
python scripts/ship.py start --prompt "<goal>"
```

If `status` is anything else and `$ARGUMENTS` is non-empty, the user wants to start fresh — call `ship.py abort` first.

Set the workflow flag so the stop hook knows we are in a long-running build:

```bash
python scripts/workflow.py set building --description "ship.py orchestrator"
```

### 1. Loop on the state machine

Repeat the following until status is `done`, `escalated`, or `aborted`:

```bash
python scripts/ship.py next-action --json
```

This returns JSON: `{status, next_action, next_feature, loop_status, fix_count, rescue_count}`. Then dispatch based on `status`:

| Status | What you do | Then advance to |
|--------|-------------|-----------------|
| `intake` | Verify the spec file exists (or create a stub from the prompt) | `spec_qa` |
| `spec_qa` | Run `python scripts/check_spec_quality.py <spec>`. Pipe output into `ship.py note` | `planning` on exit 0; `needs_spec_fix` on exit 1 |
| `needs_spec_fix` | Read the report in `.harness/ship_state.json` notes. Revise the spec to address each blocker. | `spec_qa` |
| `planning` | Spawn `planner` subagent (read `agents/planner.md`). Pass it the spec text. It writes to `docs/exec-plans/active/<slug>.md`. Record path via `ship.py set-plan <path>` | `seeding` |
| `seeding` | Read the new plan. For each milestone with a Demo statement, append a feature entry to `.harness/feature_list.json` (id, description, category, steps, passes:false). Use the existing JSON shape. | `building` |
| `building` | If `next_feature` is null → advance to `post_review`. Otherwise: **spawn `tester` agent which invokes codex** (cross-model adversarial — see `agents/tester.md`) to write failing tests, then spawn `executor` agent (Claude) to implement. The two-model split is the heart of the adversarial mechanic — same-model tests + impl share blind spots and defeat the purpose. | `validating` |
| `validating` | Run `bash scripts/validate.sh`. If exit 0 → `ship.py mark-feature <id> pass` then advance to `building`. If exit 1 → advance to `fixing` and `ship.py mark-feature <id> fail`. | `building` or `fixing` |
| `fixing` | First: `python scripts/loop_guard.py check --json`. If `loop: true`, advance to `rescuing`. Otherwise spawn `build-fixer` (max 2 attempts). After fix attempt, `ship.py record-fix`, then advance to `validating`. | `validating` or `rescuing` |
| `rescuing` | Run `python scripts/loop_guard.py rescue-request`. **Spawn TWO agents in parallel** (one message, multiple Agent tool calls): `researcher` (web-sourced) and `codex-reviewer` (independent model). Both read `.harness/rescue_request.md`. Compare outputs — if they agree, high confidence; if disagree, prefer the one whose evidence directly explains the fingerprint. Apply the targeted fix. `ship.py record-rescue`. Advance to `validating`. If fingerprint persists after one full rescue, advance to `escalated`. | `validating` or `escalated` |
| `post_review` | Spawn `post-build-reviewer`. Run `python scripts/check_spec_compliance.py`. If both clean → `adversarial_review`. Else → `fixing`. | `adversarial_review` or `fixing` |
| `adversarial_review` | Spawn `codex-reviewer` agent (it invokes `Skill("codex:rescue")` to get a different model to attempt to find a defect the tests miss). Parse codex's output: `NO DEFECT FOUND` → `committing`. `DEFECT: ... SEVERITY: blocker` → `fixing` with codex's report. `SEVERITY: warning` → `committing` with the warning logged. | `committing` or `fixing` |
| `committing` | First invoke `Skill("superpowers:verification-before-completion")`. Then `git add -A`, then commit with `feat(<area>): <summary>` and a body listing verified feature IDs, the codex review verdict, and a `Generated by ship.py` footer. | `done` |
| `done` | Print a summary: features verified, gates passed, commit SHA. Release workflow lock: `python scripts/workflow.py set none`. | (exit) |
| `escalated` | Print `.harness/rescue_request.md` plus the last 3 fingerprints from `.harness/loop_guard_state.json`. Tell the user what was tried. Release workflow lock. | (exit) |
| `aborted` | Release workflow lock. | (exit) |

### 2. Spawning subagents

The orchestrator does not call subagents itself — it tells you when to. Use the `Agent` tool with the appropriate prompt:

**Tester (CROSS-MODEL — uses codex, not Claude):**
```
Agent(subagent_type="general-purpose", prompt="""
You are the Adversarial Tester. Read agents/tester.md.

FEATURE: {feature_dict}

CRITICAL: Per agents/tester.md, the tester MUST be a DIFFERENT model than
the executor. Invoke Skill("codex:rescue") and hand codex the test-writing
prompt from the agent definition. The point of the adversarial pair is to
use codex's different blind spots — same-model TDD defeats the mechanism.

If codex is unavailable, fall back to Claude-as-tester and add a note to
ship.py: `python scripts/ship.py note "tester=claude-fallback"`. The
orchestrator will weight the later codex adversarial_review more heavily.

Place tests in the project's test directory. Run them to confirm RED.
""")
```

**Executor:**
```
Agent(subagent_type="general-purpose", prompt="""
You are the Executor. Read agents/executor.md.

FAILING TESTS: {paths from tester output}

Write the MINIMUM code to make them pass. Do not modify tests.
Run validate.sh to confirm gates pass.
""")
```

**Build-fixer:**
```
Agent(subagent_type="general-purpose", prompt="""
You are the Build Fixer. Read agents/build-fixer.md.

FAILING GATES: {output from validate.sh}

Apply the minimal fix. Maximum 2 attempts. If still failing, report.
""")
```

**Researcher (rescue path — spawn in parallel with codex-reviewer):**
```
Agent(subagent_type="general-purpose", prompt="""
You are the Researcher. Read agents/researcher.md.

RESCUE REQUEST: {contents of .harness/rescue_request.md}

Use web search to find the exact cause. Link sources.
Produce a 3-bullet root-cause analysis. Do NOT apply the fix yourself
— hand the analysis back so the orchestrator can route to build-fixer
with full context.

You run in parallel with the codex-reviewer agent. Two independent
diagnoses, compared at the end.
""")
```

**Codex Reviewer (rescue path AND adversarial_review):**
```
Agent(subagent_type="general-purpose", prompt="""
You are the Codex Reviewer. Read agents/codex-reviewer.md.

MODE: {"rescue" if status==rescuing else "adversarial"}

Invoke Skill("codex:rescue") with the appropriate prompt from your
agent definition. Pass back codex's verbatim output. Do NOT paraphrase
or apply fixes.
""")
```

Spawn researcher and codex-reviewer **in the same message** (two Agent
tool calls in one assistant turn) so they run concurrently.

**Post-build reviewer:**
```
Agent(subagent_type="general-purpose", prompt="""
You are the Post-Build Reviewer. Read agents/post-build-reviewer.md.

Review every file in `git diff main...HEAD`. Produce a compliance
matrix (wired / tested / traceable). Report only — do not modify code.
""")
```

### 3. Loop safety

If `fix_count + rescue_count` exceeds 12 for a single feature, escalate. Print the state, the last 5 fingerprints, and the failing gate details. The harness will not silently burn budget.

### 4. Final report

When status reaches `done`, print:

```
═══════════════════════════════════════════════════
 Ship Complete
═══════════════════════════════════════════════════
  Spec:           docs/exec-plans/active/<slug>.md
  Features:       X verified
  Gates:          25/25 passing
  Fix attempts:   N
  Rescues:        N
  Commit:         <sha>
═══════════════════════════════════════════════════
```

## Rules

- Always advance through `ship.py advance <state>` so the transition is recorded.
- Never skip the loop_guard check before a third fix attempt.
- Never modify tests during the build phase — only the executor's first pass writes implementation against the tester's spec.
- If you discover the spec needs revision mid-build, advance to `aborted`, fix the spec, restart with `/ship <new-spec>`. Do not silently change the spec.
- The state machine is the source of truth. If your understanding disagrees with `ship.py status`, ship.py wins.
