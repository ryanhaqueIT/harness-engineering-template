# Adversarial TDD Build

Orchestrate the RED → GREEN → REFACTOR cycle using separate agents for testing
and implementation. This prevents the conflict of interest where the same agent
writes both tests and code.

## Workflow

### Step 1: Identify the target feature

Read `.harness/feature_list.json` and find the next feature where `passes: false`.
If no features remain, report completion.

Display the feature to the user:
```
Building: [FEATURE_ID] — [description]
Steps: [list the verification steps]
```

### Step 2: RED — Write failing tests (Tester Agent)

Spawn the adversarial tester agent:

```
Agent(subagent_type="general-purpose", prompt="
You are the Adversarial Tester. Read agents/tester.md for your full instructions.

FEATURE TO TEST:
  ID: {feature_id}
  Description: {description}
  Steps: {steps}

PROJECT CONTEXT:
  - Read AGENTS.md for project structure and conventions
  - Check existing test files for the test framework in use (pytest/jest/vitest)
  - Check existing source files for the implementation patterns

Write failing tests for this feature following ALL instructions in agents/tester.md.
Place tests in the project's standard test directory.
Run the tests to CONFIRM they fail (RED phase — failures expected).
")
```

### Step 3: GREEN — Implement to pass tests (Executor Agent)

Spawn the executor agent:

```
Agent(subagent_type="general-purpose", prompt="
You are the Executor. Read agents/executor.md for your full instructions.

FAILING TESTS:
  {list the test files created in Step 2}

PROJECT CONTEXT:
  - Read AGENTS.md for project structure, module boundaries, and conventions
  - Check existing source files for implementation patterns
  - Do NOT read the feature spec — only the tests are your specification

Write the MINIMUM implementation code to make all tests pass.
Follow ALL instructions in agents/executor.md.
Run the tests to CONFIRM they pass (GREEN phase).
Run lint/format commands to ensure code quality.
")
```

### Step 4: VERIFY — Run validation gates

Run `bash scripts/validate.sh` to check all gates.

If validation fails:
1. Spawn the build-fixer agent (read agents/build-fixer.md)
2. Provide the failing gate output and relevant files
3. Build-fixer gets maximum 2 attempts
4. If still failing after 2 attempts, report to user and stop

### Step 5: COMMIT — Record the work

If all gates pass:
1. Stage the new/modified files
2. Commit with message: `feat({feature_id}): {short description}`
3. Report completion with evidence:
   - Which tests were written
   - Which files were implemented
   - Which gates passed

### Step 6: NEXT — Advance to next feature

Check if more features remain in feature_list.json.
If yes, repeat from Step 1.
If no, report all features complete.

## Rules

- NEVER let the tester see the implementation
- NEVER let the executor see the feature spec (only tests)
- NEVER skip the validation gate step
- NEVER modify tests during the GREEN phase
- If the tester and executor are the same session, maintain strict separation
- Each feature gets its own commit
