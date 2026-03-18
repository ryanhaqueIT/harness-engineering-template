Bootstrap the current repository with the full harness engineering suite (22 gates, 7-layer testing pyramid).

## Usage

Run from inside any repository you want to harness:
```
/bootstrap
```

No arguments needed. The harness is deployed into the current working directory.

## Step 0: Fetch the Harness Source

The harness scripts and playbooks live in the harness-engineering-template repo. Before starting, ensure you have a local copy:

1. Check if `~/.harness` exists (the cached clone).
2. If it does NOT exist, clone it:
   ```bash
   git clone https://github.com/ryanhaqueIT/harness-engineering-template.git ~/.harness
   ```
3. If it DOES exist, pull latest:
   ```bash
   git -C ~/.harness pull --ff-only 2>/dev/null || true
   ```

All playbooks and scripts are read from `~/.harness/`. All output is written to the CURRENT directory.

## Step 1: Execute Playbooks

Read and execute each playbook from `~/.harness/playbooks/` in strict sequential order. Do not work from memory — read the file first.

1. Read `~/.harness/playbooks/00-discover.md` — Scan THIS repo (the current working directory). Build a repo profile.
2. Read `~/.harness/playbooks/01-analyze.md` — Derive import rules, architecture constants, feature seed, boundaries. Ask the user about custom requirements.
3. Read `~/.harness/playbooks/02-generate.md` — Copy scripts from `~/.harness/scripts/` into this repo. Configure them. Write AGENTS.md, CLAUDE.md, CI, docs.
4. Read `~/.harness/playbooks/03-verify.md` — Run validate.sh, init ratchet, run scorecard, verify consistency.

Carry the repo profile forward through every phase.

## Key Rules

- Scripts are COPIED from `~/.harness/scripts/` into the current repo's `scripts/` directory.
- Documentation is MODELED after `~/.harness/docs/`, `~/.harness/PLANS.md`, `~/.harness/agents/` — adapt for this project.
- NEVER delete existing source code.
- NEVER overwrite user customizations without asking.
- If this repo already has a harness (validate.sh exists), ask before overwriting.
- At the end, report what was created, what was skipped, and any issues found.

## Installation (one-time, on any machine)

To make `/bootstrap` available globally in Claude Code:
```bash
mkdir -p ~/.claude/commands
curl -o ~/.claude/commands/bootstrap.md https://raw.githubusercontent.com/ryanhaqueIT/harness-engineering-template/master/.claude/commands/bootstrap.md
```

Then `/bootstrap` works from any repo, on any machine.
