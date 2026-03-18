# Demo Script — Harness Engineering in Action

**Duration:** 15-20 minutes
**What you need:** A laptop with Claude Code installed, internet connection
**Audience takeaway:** "I just watched an AI build a feature from a PRD, get blocked when it wrote bad code, fix itself, prove the feature works against a running app, and ship — with zero human code review."

---

## Pre-Demo Setup (do this before the demo)

```bash
# 1. Install the bootstrap command (one time)
mkdir -p ~/.claude/commands
curl -o ~/.claude/commands/bootstrap.md \
  https://raw.githubusercontent.com/ryanhaqueIT/harness-engineering-template/master/.claude/commands/bootstrap.md

# 2. Create a fresh demo project
mkdir -p ~/demo-harness/backend/{routers,services,db,models,tests}
cd ~/demo-harness
git init
```

Create a minimal FastAPI app for the demo:

**`backend/requirements.txt`:**
```
fastapi==0.109.0
uvicorn==0.27.0
sqlalchemy==2.0.25
ruff==0.3.0
pytest==8.0.0
```

**`backend/main.py`:**
```python
from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "healthy"}
```

```bash
# 3. Install dependencies
cd backend && pip install -r requirements.txt && cd ..

# 4. Commit the initial state
git add -A && git commit -m "initial: bare FastAPI app"
```

---

## The Demo

### Act 1: "Watch me harness a repo in 60 seconds" (3 min)

**[SAY]** "I have a bare FastAPI project. One endpoint. No tests, no CI, no quality gates. Let me add the full harness."

```bash
cd ~/demo-harness
claude
```

**[TYPE in Claude Code]**
```
/bootstrap
```

**[NARRATE while it runs]**
- "It's scanning the repo... found Python, FastAPI, SQLAlchemy."
- "It's tracing imports to figure out the architecture rules."
- "Now it's copying 23 enforcement scripts, each one configured for this project."
- "It's writing AGENTS.md — the instruction manual for any AI agent."
- "Now it's running validate.sh to verify everything works..."
- "And it initialized the quality ratchet — the baseline is locked."

**[SHOW the output]** Point to the gate results: passes, fails, skips.

**[SAY]** "That's it. This project now has 23 quality gates. Every commit must pass all of them. Let me show you what happens when an agent tries to write bad code."

---

### Act 2: "The harness catches bad code" (3 min)

**[SAY]** "Let me ask the agent to add a users endpoint — but I'll let it write whatever it wants."

**[TYPE in Claude Code]**
```
Add a GET /api/users endpoint that returns a list of users from the database. Put the database query directly in the router file.
```

**[WAIT for the agent to write code]**

The agent will write something like:
```python
# backend/routers/users.py
from sqlalchemy.orm import Session    # ← import violation!

@router.get("/api/users")
def get_users():
    print("Fetching users")           # ← golden principle violation!
    ...
```

**[TYPE]**
```
/validate
```

**[NARRATE the failures]**
- "Gate B4 — Import boundaries: FAIL. The router imported SQLAlchemy directly. The rule says routers can only import from services and models."
- "Gate B5 — Golden principles: FAIL. It used print() instead of logger.info()."
- "The commit is blocked. The agent can't ship this code."

**[SAY]** "Now watch — the agent reads the error messages and fixes itself."

**[TYPE]**
```
Fix all the validation failures. Move the DB query to a service, use structured logging instead of print, and add type hints.
```

**[TYPE after the agent fixes]**
```
/validate
```

**[SHOW]** All gates pass now.

**[SAY]** "The agent fixed itself using the error messages from the gates. No human reviewed the code. The architecture is clean because the harness enforced it."

---

### Act 3: "PRD to verified feature" (7 min)

**[SAY]** "Now let me show you the full pipeline. I'll give it a product requirement, and it will plan, build, and verify — end to end."

**[TYPE in Claude Code]**
```
Here's my PRD:

Users can create invoices. Each invoice has:
- A customer name
- One or more line items, each with a description, quantity, and unit price
- The system calculates: subtotal (sum of quantity * unit_price for all items), tax (10% of subtotal), and total (subtotal + tax)

API endpoints needed:
- POST /api/invoices — create an invoice, returns the invoice with calculated totals
- GET /api/invoices/{id} — retrieve an invoice by ID

Please:
1. Generate an ExecPlan with /plan
2. Seed the feature list with testable requirements
3. Implement the feature
4. Boot the app and run the live feature tests
5. Show me the results
```

**[NARRATE as it works]**

**Phase 1 — Planning:**
- "It's reading PLANS.md to understand the ExecPlan format."
- "It generated a plan with two milestones: API implementation and verification."

**Phase 2 — Feature List:**
- "Now it's seeding feature_list.json from the PRD."
- "Each requirement became a testable entry with specific steps and expected values."
- "Notice: response.subtotal equals 55.00, response.tax equals 5.50 — these are the exact values it must hit."

**[SHOW `.harness/feature_list.json`]**

**[SAY]** "These test steps are locked. The agent writing the code cannot change them. This is the contract between the PRD and the implementation."

**Phase 3 — Implementation:**
- "Now it's writing the actual code — models, service, router."
- "After each change, it runs validate.sh."
- "If it violates any gate, it fixes itself and re-runs."

**Phase 4 — Live Verification:**
- "Now it's booting the app with boot_worktree.sh."
- "Gate X6 is firing — the live feature test runner."

**[SHOW the live test output]**
```
[F010] POST /api/invoices creates invoice with correct totals
  PASS  Send POST /api/invoices with line items → HTTP 201
  PASS  response.subtotal = 55.0 == 55.00
  PASS  response.tax = 5.5 == 5.50
  PASS  response.total = 60.5 == 60.50
  PASS  response.id = 1 (not null)
  → FEATURE PASSED

[F011] GET /api/invoices/{id} retrieves the invoice
  PASS  Send GET /api/invoices/1 → HTTP 200
  PASS  response.line_items has length 2
  → FEATURE PASSED

Features: 2 passed, 0 failed
```

**[SAY]** "Those aren't unit tests the agent wrote. That's the live test runner sending real HTTP requests to the running app and checking the actual response values against the PRD requirements. The runner did the verification, not the agent."

---

### Act 4: "The ratchet — quality can never go backwards" (2 min)

**[SAY]** "One last thing. Let me show you the ratchet."

**[TYPE]**
```
/ratchet
```

**[SHOW the baseline]**
```
Category                          Baseline    Current     Delta  Status
lint_errors                              0          0         0  OK
golden_principle_violations              0          0         0  OK
import_violations                        0          0         0  OK
test_coverage_ratio                   0.67       0.67         0  OK
```

**[SAY]** "This is locked. If anyone — human or AI — introduces a new lint error, a new print() statement, or breaks an import boundary, the ratchet will catch it and block the commit. Quality can only go up."

**[OPTIONAL — demonstrate it]**

**[TYPE]**
```
Add a print("debug") statement to the invoice service.
```

**[TYPE]**
```
/validate
```

**[SHOW]** Gate B5 fails, ratchet would show `golden_principle_violations: 1 > 0 — REGRESSED`.

**[SAY]** "Blocked. The ratchet won't let quality go backwards. Even if I explicitly told the agent to add that print statement, the harness says no."

---

### Closing (1 min)

**[SAY]**

"Let me recap what just happened:

1. I bootstrapped a repo with one command — `/bootstrap`
2. I gave it a PRD — invoices with tax calculation
3. The agent planned, coded, and tested — fully autonomously
4. The live test runner verified the math was correct by sending real requests
5. 23 gates checked everything from syntax to architecture to secrets
6. The ratchet locked in the quality baseline

No human reviewed the code. No human ran the tests. No human checked the architecture. The harness did all of it.

The engineer's job shifts from 'review every line of code' to 'define the rules and write the PRD.' The harness handles everything else."

---

## If Something Goes Wrong During the Demo

| Problem | Recovery |
|---|---|
| `/bootstrap` takes too long | Have a pre-bootstrapped version ready. `cp -r ~/demo-harness-backup ~/demo-harness` |
| Agent writes code that doesn't work | That's actually a GOOD demo moment — show the gates catching it |
| validate.sh has unexpected failures | Run `/scorecard` instead to show the maturity grade |
| App won't boot for live tests | Skip Act 3's live verification, show the feature_list.json and explain the runner |
| Audience asks about non-Python languages | "The bootstrap auto-detects. For TypeScript it uses ESLint strict rules. For Go it uses golangci-lint. Same gates, different enforcers." |

## Key Talking Points for Q&A

- **"Is this just linting?"** — No. Linting is Layer 1. This has 7 layers including AST-based architecture enforcement, browser automation, live API testing, log analysis, and a quality ratchet.
- **"Can the agent cheat?"** — The feature list steps are locked. The live test runner executes them and checks responses. The agent implementing the code is not the one deciding if it passes.
- **"What about edge cases and UX?"** — The harness verifies mechanical correctness. Subjective UX decisions still need a human. But you're freed from reviewing whether the tax calculation is right or whether the imports are clean.
- **"How long to set up on a real project?"** — `/bootstrap` takes 2-5 minutes on a typical repo. It works on existing codebases without demanding perfection on day 1.
- **"What if I disagree with a rule?"** — Every rule is a plain Python or Bash script in `scripts/`. Edit it. The harness is fully customizable.
