# Execution Plans (ExecPlans)

This document describes the requirements for an execution plan ("ExecPlan"), a design document that a coding agent can follow to deliver a working feature or system change. Treat the reader as a complete beginner to this repository: they have only the current working tree and the single ExecPlan file you provide. There is no memory of prior plans and no external context.

## How to Use ExecPlans

When authoring an executable specification (ExecPlan), follow this file to the letter. Be thorough in reading and applying every rule. ExecPlans are living documents -- update them continuously as you work.

## When to Create an ExecPlan

Create an ExecPlan for any task that:
- Takes more than 30 minutes to implement
- Spans multiple files or modules
- Requires design decisions
- Has acceptance criteria beyond "it compiles"

Store active plans in `docs/exec-plans/active/`. Move completed plans to `docs/exec-plans/completed/`.

## Required Sections

Every ExecPlan MUST contain these sections:

### Living Document Sections (update continuously)

1. **Progress** -- Checkbox list with ISO timestamps. Every stopping point documented.
   ```
   - [x] (2026-01-15T10:30Z) Created API scaffold with health endpoint
   - [x] (2026-01-15T11:45Z) Database client with async CRUD helpers
   - [ ] WebSocket handler (in progress: webhook done, WS pending)
   - [ ] External API integration
   ```
   Timestamps measure velocity. Split partially-completed tasks into done/remaining.

2. **Surprises & Discoveries** -- Unexpected behaviors with concise evidence.
   ```
   - External API returns ~30% malformed JSON on tool calls. Workaround: client-side
     retry with text nudge. Source: vendor developer guide.
   ```

3. **Decision Log** -- Decisions with rationale, author, and date.
   ```
   - (2026-01-15) Using Vendor A over Vendor B -- simpler API, lower cost, reference
     implementation exists. See design-docs/001-vendor-selection.md for full rationale.
   ```

4. **Outcomes & Retrospective** -- Summary at major milestones and at completion.

### Structural Sections (write upfront, refine as you go)

5. **Purpose / Big Picture** -- User-visible outcomes. What can users DO after this change that they couldn't before? How will you demonstrate it works?

6. **Context and Orientation** -- Repository state assuming zero prior knowledge. Define every term of art. Include full repository-relative file paths. Name functions and modules precisely.

7. **Plan of Work** -- Prose describing the edits, organized into milestones. Each milestone:
   - Brief opening paragraph describing scope
   - What will exist at completion that didn't before
   - Commands to run and expected observable results
   - Each milestone independently verifiable

8. **Concrete Steps** -- Exact commands with working directory and expected output transcripts.
   ```
   $ cd backend && python -m pytest tests/services/test_user.py -v
   tests/services/test_user.py::test_create_user ... PASSED
   tests/services/test_user.py::test_get_user_not_found ... PASSED
   2 passed in 0.34s
   ```

9. **Validation and Acceptance** -- Observable behavior a human can verify. NOT internal attributes.
   - Good: "Navigating to localhost:8000/health returns HTTP 200 with body {"status":"healthy"}"
   - Bad: "Added HealthCheck class to main.py"

10. **Idempotence and Recovery** -- Steps must be safely repeatable. For risky steps, provide rollback procedures.

## Self-Containment Rules

- Repeat assumptions; do not reference "prior milestones" without restating context
- Do not point to external blogs or documentation; embed required knowledge
- Name files with full repository-relative paths (e.g., `backend/services/user_service.py`)
- Define non-obvious terms with examples showing where they manifest in the codebase
- Include full context from any incorporated prior plans

## Formatting Rules

- Two newlines after every heading
- Prose-first narrative (avoid checklists outside Progress section)
- Use indented code blocks for commands/diffs/code (not nested triple backticks)
- Keep plan files in `docs/exec-plans/active/` during work
- Move to `docs/exec-plans/completed/` when done

## Agent Responsibilities During Execution

- Update all living sections continuously, not just at completion
- Never prompt users for next steps; proceed autonomously
- Resolve ambiguities independently
- Commit frequently with descriptive messages
- Record design decisions with reasoning in the Decision Log
- If you change course, document why in Decision Log and reflect in Progress

## ExecPlan Template

Copy this template to `docs/exec-plans/active/your-plan-name.md`:

```markdown
# ExecPlan: [Feature Name]

## Purpose / Big Picture

[What can users DO after this change that they couldn't before?]

## Context and Orientation

[Repository state. Define terms. Full file paths. Module names.]

## Plan of Work

### Milestone 1: [Name]

[Scope paragraph. What exists at completion. Commands to verify.]

### Milestone 2: [Name]

[Scope paragraph. What exists at completion. Commands to verify.]

## Concrete Steps

[Exact commands, working directory, expected output.]

## Validation and Acceptance

[Observable behaviors a human can verify.]

## Idempotence and Recovery

[How to safely re-run steps. Rollback procedures for risky operations.]

---

## Progress

- [ ] [First task]
- [ ] [Second task]

## Surprises & Discoveries

[None yet]

## Decision Log

[None yet]

## Outcomes & Retrospective

[To be completed at end]
```
