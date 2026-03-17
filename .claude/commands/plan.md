Generate an ExecPlan following the template in PLANS.md.

## Steps

1. Read `PLANS.md` to load the ExecPlan template and all formatting rules.
2. Read `AGENTS.md` for architecture constraints, golden principles, and module boundaries.
3. Ask the user for the following inputs before generating:
   - **Purpose**: What can users do after this change that they could not before?
   - **Context**: Which modules, files, or systems are involved?
   - **Acceptance criteria**: Observable behaviors that prove the feature works.
4. Generate a complete ExecPlan following every rule in PLANS.md:
   - All required sections (Progress, Surprises, Decision Log, Outcomes, Purpose, Context, Plan of Work, Concrete Steps, Validation, Idempotence)
   - Full repository-relative file paths
   - Concrete commands with expected output
   - Each milestone independently verifiable
5. Save the plan to `docs/exec-plans/active/{feature-name}.md` using kebab-case for the filename.
6. Confirm the file was created and show the Purpose and Milestone summary.

## Rules

- Never skip the user input step -- always ask before generating.
- Follow PLANS.md formatting rules exactly (two newlines after headings, prose-first narrative).
- Include validation commands for every milestone (e.g., pytest, curl, validate.sh).
- Reference specific files and functions by their full path.
