Bootstrap a target repository with the full harness engineering suite.

## Usage

The user provides a path to a target repository:
```
/bootstrap /path/to/target-repo
```

If no path is provided, ask for one. Never run against this bootstrap repo itself.

## Workflow

Execute the four playbooks in strict sequential order. Read each playbook file before executing it — do not work from memory.

1. Read `playbooks/00-discover.md` and execute discovery against the target repo. Build a repo profile.
2. Read `playbooks/01-analyze.md` and perform deep analysis. Derive all configuration values.
3. Read `playbooks/02-generate.md` and generate the full harness into the target repo.
4. Read `playbooks/03-verify.md` and validate everything works.

Carry the repo profile forward through every phase — it is the shared context.

## Important

- The harness scripts live in THIS repo under `scripts/`. Copy them into the target.
- The documentation templates live in THIS repo under `docs/`, `agents/`, `PLANS.md`. Use them as the model for what you generate.
- NEVER delete existing source code in the target repo.
- NEVER overwrite existing user customizations without asking.
- If the target repo already has a harness (validate.sh exists), ask before overwriting.
- At the end, report what was created, what was skipped, and any issues found.
