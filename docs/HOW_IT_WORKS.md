# Harness Engineering — How It Works

## The One-Sentence Version

You give it a product requirement. It generates a plan, writes the code, tests every feature against the running app, and blocks the commit if anything doesn't work. No human reviews the code.

## The Problem It Solves

Traditional development:
```
Developer writes code → Another developer reviews it → Hopefully catches bugs → Merge
```

This doesn't scale with AI agents. If you have 5 agents writing code simultaneously, who reviews it all? You become the bottleneck.

Harness engineering flips it:
```
Agent writes code → 23 automated gates verify it → Blocks if anything fails → Merge
```

No bottleneck. The gates are the reviewer. They're faster, more consistent, and never get tired.

## How to Set It Up (2 minutes)

**One time on your machine:**
```bash
mkdir -p ~/.claude/commands
curl -o ~/.claude/commands/bootstrap.md \
  https://raw.githubusercontent.com/ryanhaqueIT/harness-engineering-template/master/.claude/commands/bootstrap.md
```

**For any project you want to harness:**
```bash
cd ~/your-project
claude
/bootstrap
```

That's it. The agent scans your project, figures out the stack, and sets up everything. Works on new projects and existing codebases.

## What `/bootstrap` Actually Does

Think of it as a 4-step doctor's visit for your codebase:

**Step 1 — Checkup:** Scans every file. Detects language (Python, TypeScript, Go), framework (FastAPI, Next.js), database library, API endpoints, frontend pages, existing tests, existing CI.

**Step 2 — Diagnosis:** Traces how modules import each other. Figures out the architecture rules. Determines what should be allowed and what shouldn't (e.g., "the API layer should never talk to the database directly").

**Step 3 — Treatment:** Copies 23 enforcement scripts into your project. Configures them for YOUR specific architecture. Writes documentation, CI pipelines, and the feature tracking system.

**Step 4 — Follow-up:** Runs all 23 gates to verify the setup works. Creates a quality baseline. Reports a maturity grade.

After this, your project has an invisible fence: every commit must pass all 23 gates.

## How a PRD Becomes Verified Code

This is the full pipeline. Seven steps, no human review.

### Step 1: You Provide a PRD

You write what you want built. Example:

> "Users can create invoices. Each invoice has line items with quantity and unit price. The system calculates subtotal, applies 10% tax, and returns the total."

### Step 2: Agent Generates a Plan

Run `/plan`. The agent reads your PRD and produces an execution plan with:
- Milestones (what to build in what order)
- Concrete steps (exact files to create, exact commands to run)
- Acceptance criteria (how to verify each milestone works)

### Step 3: Agent Seeds the Feature List

Before writing any code, the agent creates `.harness/feature_list.json` — a list of testable requirements derived from the PRD:

```json
{
  "id": "F010",
  "description": "POST /api/invoices creates invoice with correct totals",
  "steps": [
    "Send POST /api/invoices with 3 Widgets at $10 and 1 Gadget at $25",
    "Verify HTTP 201",
    "Verify response.subtotal equals 55.00",
    "Verify response.tax equals 5.50",
    "Verify response.total equals 60.50"
  ],
  "passes": false
}
```

**These steps are locked.** The agent writing the code cannot change them. They are the contract between "what you asked for" and "what was built."

### Step 4: Agent Writes the Code

The agent implements the feature, running `validate.sh` after every change. If it writes bad code:

- Used `print()` instead of `logger.info()`? **Blocked** (golden principles gate)
- Imported the database library in the API layer? **Blocked** (import boundary gate)
- Created a 500-line file? **Blocked** (architecture gate)
- Hardcoded an API key? **Blocked** (secret scan gate)

The agent fixes the violation and tries again. This loop repeats until the code is clean.

### Step 5: Agent Boots the App and Runs Live Tests

The agent starts the application locally, then Gate X6 fires. It **mechanically executes** each feature step:

```
Sending POST /api/invoices...          → Got HTTP 201 ✓
Checking response.subtotal == 55.00... → 55.00 ✓
Checking response.tax == 5.50...       → 5.50 ✓
Checking response.total == 60.50...    → 60.50 ✓
```

For UI features, it opens a headless browser and actually clicks buttons, fills forms, and reads the page — just like a QA tester would.

**If the tax calculation is wrong (say 15% instead of 10%):**
```
Checking response.tax == 5.50...       → Got 8.25 ✗ FAIL
COMMIT BLOCKED
```

The agent didn't decide it passed. The test runner checked the actual math against the expected value from the PRD. The agent can't cheat.

### Step 6: All 23 Gates Must Pass

Before the commit goes through, `validate.sh` runs all 23 gates:

| What's Checked | How |
|---|---|
| Code compiles and lints | Ruff, ESLint, TypeScript |
| Architecture rules followed | AST parser traces every import |
| No secrets in code | Regex scan for API keys, passwords |
| Unit tests pass | Pytest, Jest |
| UI works in a real browser | Playwright drives the app |
| No error logs, latency is OK | Queries actual log and metric stores |
| **Every PRD feature works** | **Sends real requests, checks real responses** |
| Quality hasn't gotten worse | Ratchet compares against baseline |

If ANY gate fails, the commit is blocked. The agent must fix it.

### Step 7: Ship

The code is verified. Not by a human glancing at a diff, but by:
- An AST parser that checked every import
- A test suite that checked every function
- A browser that drove every page
- An HTTP client that tested every API endpoint
- A ratchet that confirmed quality didn't regress

## The Three Guarantees

**1. No bad code gets in.** 23 gates check everything from syntax to architecture to secrets. The checks use AST parsing — they read the actual code structure, not just text patterns. You can't fool them.

**2. Quality only goes up.** The ratchet saves today's violation count. If tomorrow's count is higher, the commit is blocked. Over time, the codebase can only get cleaner.

**3. Features must actually work.** The feature list tracks every PRD requirement. The live test runner sends real requests to the running app and checks real responses. The agent implementing the code is not the one deciding if it passes — the test runner is.

## What You Still Need to Do

| Task | Who Does It | When |
|---|---|---|
| Write PRDs | You (the human) | When you want something built |
| Run `/bootstrap` on a new repo | You (one time) | When starting a project |
| Review the feature list | You (optional) | After the agent seeds it from the PRD |
| Fix issues the harness can't catch | You (rare) | Subjective design decisions, UX judgment calls |

Everything else — planning, coding, testing, enforcement, quality tracking — is handled by the harness and the AI agent.

## FAQ

**Q: What if the agent writes tests that match wrong code?**
The agent doesn't write the feature test steps. Those come from the PRD, seeded before implementation. The live test runner executes them independently.

**Q: What if I disagree with a gate?**
Edit the relevant script in `scripts/`. The rules are plain Python and Bash — fully customizable. For example, if you want to allow `print()` in development scripts, add an exception to `check_golden_principles.py`.

**Q: Does it work with existing projects?**
Yes. The bootstrap scans your existing code, sets rules based on your actual architecture, and baselines your current quality. It doesn't demand perfection on day 1 — it prevents things from getting worse.

**Q: What AI agents does it work with?**
Claude Code (fully automatic via `/bootstrap`), Codex, Cursor, Copilot, Windsurf (via `bootstrap.sh` + playbooks). The enforcement scripts work regardless of which agent wrote the code.

**Q: What languages does it support?**
Python (full AST enforcement), TypeScript/JavaScript (lint-based enforcement), Go, PHP, Rust (linter config). The bootstrap auto-detects and configures for your stack.
