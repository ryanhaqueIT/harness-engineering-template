# Harness Engineering — A Complete Deep Dive

## The Core Problem

When you use AI agents to write code, you face a scaling problem that doesn't exist in traditional development. In a normal team, if you have five developers, you also have five people reviewing each other's work. The reviewer acts as a human gate — they catch bugs, enforce patterns, and maintain quality. But when you have five AI agents writing code simultaneously, you — the single human — become the reviewer for all of them. You can't read all that code. You become the bottleneck.

Harness engineering is a fundamentally different philosophy. Instead of reviewing the code the agent writes, you design the *system that constrains what the agent can write*. You stop being a code reviewer and start being a systems engineer. You build an invisible fence around the codebase, and any code that doesn't meet the standard physically cannot enter the repository. The agent keeps rewriting until the code passes every gate, or it asks for help. No human review needed.

The entire system rests on one rule, stated at the very top of the governing document `AGENTS.md`:

> **`./scripts/validate.sh` must exit 0 before every commit. No exceptions.**

That single sentence is the foundation everything else is built on. Every mechanism, every hook, every agent, every script — they all exist to make that rule unfakeable and inescapable.

---

## The Architecture: Three Layers of Enforcement

Think of the harness as three concentric rings of defense. The innermost ring is the validation gates themselves — the actual checks that inspect code. The middle ring is the hook system — the triggers that ensure those checks actually run at the right moments. The outer ring is the agent governance system — the rules, roles, and workflows that structure how AI agents approach work.

### Ring 1: The Validation Gates (`scripts/validate.sh`)

The heart of the system is a single bash script, `validate.sh`, that acts as a universal gateway. When it runs, it auto-detects what kind of code exists in your repository (Python backend? TypeScript frontend? Terraform infrastructure?) and runs the appropriate checks for each stack. There are 25 gates organized into a layered pyramid, and this structure is deliberate — earlier layers are cheaper and faster to run, so they catch the obvious mistakes before the expensive checks run.

**Layer 1 — Deterministic Checks (Gates B1, B2, F1-F3):** These are the simplest and fastest. Does the code lint cleanly? Is it properly formatted? These are non-negotiable baseline hygiene checks. For Python, it runs `ruff` (or falls back to `flake8`). For TypeScript, it runs `eslint` and `prettier`. If a tool isn't installed, the gate is skipped rather than failed — this is important because it means the harness works progressively. You don't need every tool installed on day one.

**Layer 2 — Structural Checks (Gates B4-B6, B8, X1-X2):** This is where harness engineering starts doing things that normal linters cannot. Gate B4, the import boundary checker, uses Python's `ast` module to parse the actual abstract syntax tree of your code. It's not doing regex matching — it's reading the real import structure and comparing it against a dependency graph that was derived during the bootstrap phase. If your project has a rule that says "routers cannot import the database layer directly — they must go through the service layer," this gate enforces it mechanically. The agent literally cannot cheat by renaming an import or hiding it behind indirection, because the AST parser traces the real dependency path.

Gate B5 is the golden principles checker, and it's one of the most interesting scripts in the whole system. Open up `scripts/check_golden_principles.py` and you'll see it doesn't just check for style — it checks for security vulnerabilities using CWE classifications. It detects `print()` calls in production code (you should use `logger.info()` with structured logging), but it also detects CWE-636 (fail-open catch blocks that silently swallow authentication errors, effectively granting access when auth fails), CWE-209 (leaking stack traces in error responses), and CWE-306 (mutation endpoints like POST/PUT/DELETE that have no authentication dependency). All of this is done through AST parsing, which means the checker reads the actual code structure, not text patterns. You can't fool it by reformatting the code.

Gate B6 checks architecture invariants — files that are too long (God files over 300 lines), modules that access the database from the wrong layer, and AI library imports in places they shouldn't be.

Gate X2 scans every source file for hardcoded secrets using regex patterns for known API key formats (AWS keys starting with `AKIA`, OpenAI keys starting with `sk-`, Google API keys starting with `AIza`, and PEM private key headers).

**Layer 3 — Tests (Gates B3, F5):** Unit and integration tests must pass. For Python that's `pytest`, for JavaScript it's `jest` or `vitest`. Standard stuff, but the point is that it's mandatory — not optional, not "we'll write tests later."

**Layer 4 — Build and Functional (Gates F4, F6-F7):** The frontend must successfully build (Next.js, Vite, or whatever framework is detected). Gate F6 does HTTP smoke tests against the running UI. Gate F7 runs Playwright browser tests that actually open a headless browser and interact with the page — clicking buttons, filling forms, and asserting that the right content appears.

**Layer 5 — Infrastructure (Gates I1-I2):** If you have Terraform or Pulumi code, it must be properly formatted and validate successfully.

**Layer 6 — Observability (Gate O1):** This is remarkable — if you have a local observability stack running (VictoriaLogs and VictoriaMetrics via Docker Compose), the harness queries your actual log store for ERROR and PANIC entries, and queries your metrics store for p95 latency thresholds. Your code doesn't just need to compile and pass tests — it needs to run without generating error logs and with acceptable latency.

**Layer 7 — PRD Enforcement (Gates X5, X6, X7, R1):** This is the crown jewel of the system. Gate X5 reads `.harness/feature_list.json` — a JSON file where each feature from the product requirements document is listed with specific testable steps. Gate X6 goes further: it starts the actual application, then mechanically executes each feature's verification steps. For API features, it sends real HTTP requests and checks the response body. For UI features, it opens a browser and drives the interface. The agent that wrote the code is NOT the one deciding if it passes — the test runner is. This separation is crucial because it prevents the agent from marking its own homework.

Gate R1 is the ratchet, and it enforces a beautiful principle: **quality can only go up, never down.** The file `.harness/baseline.json` stores a snapshot of violation counts — how many lint errors, how many format violations, how many import boundary violations, how many God files, and so on. Every time validate.sh runs, the ratchet compares the current violation count against the baseline. If the current count is higher than the baseline, the commit is blocked. This means that over time, the codebase can only get cleaner. You start wherever you are on day one, and you can never regress.

The way the `check()` function works inside validate.sh is elegantly simple. It takes a gate name and a command, runs the command, and if it exits 0 it increments the PASS counter, otherwise it increments the FAIL counter. Critically, the script does NOT use `set -e` (exit on error) — it deliberately continues running all gates even after a failure, so the agent gets a complete report of everything that's broken, not just the first failure. At the end, if FAIL is greater than zero, the script exits with code 1. Otherwise, it exits 0. That's it — and that exit code is what gates the entire commit process.

---

### Ring 2: The Hook System (`.claude/settings.json`)

Having validation gates is useless if nobody runs them. The hook system makes it impossible to skip them. In `.claude/settings.json`, you'll find six hook trigger points, each firing at a specific moment in the agent's workflow:

**PreToolUse hooks** fire *before* the agent does something. There are two:

The **pre-commit hook** intercepts every Bash command the agent tries to run. It reads the command from stdin, and if it detects `git commit`, it runs `validate.sh` first. If validation fails, it exits with code 2, which blocks the commit entirely. The agent sees a big banner: "COMMIT BLOCKED: validate.sh failed. Fix all issues above, then retry. THE RULE: validate.sh must exit 0 before every commit. No exceptions." The agent cannot commit without passing every gate.

The **enforce-locations hook** fires on every Write or Edit operation. It ensures that plans go in `docs/exec-plans/active/`, specs go in `docs/product-specs/`, and other files go where they belong. This prevents the agent from dumping files in random locations.

**PostToolUse hooks** fire *after* the agent does something. There are also two:

The **post-edit hook** runs immediately after any file edit. Instead of waiting until commit time to discover violations, it runs the golden principles checker, architecture checker, and import boundary checker right away. This gives the agent immediate feedback — "you just wrote a `print()` statement, fix it now before you write more code." This closes an important gap: without this hook, a subagent could write 50 files full of violations before anyone notices at commit time.

The **loop detection hook** is inspired by DeerFlow's LoopDetectionMiddleware. It hashes each tool call (tool name + arguments) and tracks the last 20 calls in a sliding window stored in `.harness/loop_state.json`. If the same exact tool call appears 3 times, it warns the agent: "you're looping, try a different approach." At 5 identical calls, it hard-blocks: "LOOP HARD-STOP. You MUST try a completely different approach." This prevents the agent from getting stuck retrying the same broken fix endlessly, which is a very common failure mode for AI coding agents. Note that read-only tools (Read, Glob, Grep, WebSearch) are excluded from loop detection — it's fine to read the same file multiple times.

**The Stop hook** fires when the agent tries to finish its work and exit. The `stop_verification.py` script reads the current workflow state and the feature list. If the agent is in "researching" or "planning" mode, it lets it exit freely — no need to verify features when you're just doing research. But if the agent is in "verifying" or "shipping" mode and there are unverified features in the feature list, it blocks the exit: "STOP BLOCKED: 3/5 features verified. You must start the app, run verification steps, and flip passes:true only after real verification." The agent cannot claim it's done until every feature actually works in the running application.

**The PreCompact hook** fires before Claude Code compresses its context window (which happens as conversations get very long). Before the agent loses its memory, the hook tells the LLM to write a continuation snapshot to `.harness/continuation.md` — capturing the current task, progress, pending decisions, next steps, and any recurring mistakes. This way, when the agent resumes after compaction, it has a breadcrumb trail to pick up where it left off.

**The SessionStart hook** does the reverse — when a new session begins, it checks if a continuation snapshot exists and is fresh (less than 2 hours old). If so, it injects that context into the conversation, telling the agent "resume from the Next Steps section, do NOT restart from scratch."

**The SubagentStop hook** runs `validate.sh` every time a subagent finishes its work. This is critical because subagents are autonomous — they spin up, do work, and return results. Without this hook, a subagent could write code that violates every rule and return "done" to the parent agent. With this hook, every subagent must pass all 25 gates before it's allowed to report completion.

---

### Ring 3: Agent Governance

The third ring is about structuring *how* agents work, not just constraining *what* they produce. The `agents/` directory contains eight specialized agent definitions, each with a narrow role and strict boundaries:

The **tester agent** writes tests first, following adversarial TDD. It writes tests that are *hard* to pass — not just happy paths, but error cases and edge cases. It has a mutation resistance checklist: "Can `return True` pass this test? Can `return {}` pass it? Can `return 200` pass it?" If so, the test is too weak. The tester produces failing tests and hands them to the executor.

The **executor agent** takes those failing tests and writes the *minimum code* to make them pass. It operates in the classic TDD cycle — RED (receive failing tests), GREEN (write simplest code that passes), REFACTOR (clean up). It's explicitly forbidden from modifying tests, adding unrequested features, or touching files outside its scope.

The **build-fixer agent** handles failures with a disciplined approach. It checks infrastructure first (is the database running? are dependencies installed? are env vars set?) before touching code. It gets a maximum of 2 fix attempts before it must escalate — it cannot keep flailing.

The **post-build-reviewer** is read-only. It cannot modify code at all. It produces a compliance matrix: "is this code wired correctly? is it tested? is it traceable to a feature requirement?" Evidence-based, never subjective.

The **entropy cleaner** scans for drift, tech debt, and accumulated issues — TODO/FIXME markers, orphan files, dead code, and documentation that has drifted from reality.

All of these agents are governed by `AGENTS.md`, which sits at the top of the authority hierarchy. When any instruction source conflicts — whether it's a Claude Code skill, a slash command, or external documentation — AGENTS.md wins. This prevents the agents from being led astray by conflicting instructions.

---

## The Bootstrap Process: How It All Gets Set Up

The bootstrap is a four-phase process that transforms any repository — existing or brand new — into a harnessed project. Think of it as a doctor's visit for your codebase.

**Phase 0 (Discover)** scans everything. It detects the language (Python, TypeScript, Go, Rust, PHP, Java), the framework (FastAPI, Next.js, Django, Express), the package manager, the database library, the AI libraries, the module structure, the API endpoints, the frontend pages, and any existing CI configuration. The detection is done through file signatures — `pyproject.toml` means Python, `next.config.ts` means Next.js, `go.mod` means Go. It also determines if this is a "brownfield" project (existing code, 5+ source files) or "greenfield" (new project). For brownfield projects, it maps what exists. For greenfield, it asks the user what they want to build.

**Phase 1 (Analyze)** traces how modules actually import each other. It builds a dependency DAG (directed acyclic graph) by parsing the AST of every source file. From this DAG, it derives the import boundary rules — which modules are allowed to import which other modules. It also derives architecture constants: the maximum file size threshold, which module contains database access, which patterns indicate database imports, which modules are allowed to use AI libraries, and which modules should have test coverage. These are all specific to YOUR project, not generic defaults.

**Phase 2 (Generate)** copies the 22+ enforcement scripts into your project and configures them with the values derived in Phase 1. It writes `AGENTS.md` with your specific module dependency rules. It seeds `.harness/feature_list.json` from the endpoints and pages discovered in Phase 0. It copies CI workflows, documentation templates, and agent definitions. Every generated file has an idempotency watermark — if you re-run bootstrap, it detects which files have been manually modified by the user and doesn't overwrite them.

**Phase 3 (Verify)** runs everything to make sure it works. It syntax-checks all Python scripts (`compile()`), validates all bash scripts (`bash -n`), runs `validate.sh` to see the initial pass/fail/skip breakdown, initializes the ratchet baseline (capturing the current violation counts as the floor), runs the maturity scorecard (targeting at least Grade B+), and verifies that `AGENTS.md` and `CLAUDE.md` are consistent.

---

## The Feature List: How PRD Requirements Become Mechanical Proof

This is the mechanism that separates harness engineering from "just having a CI pipeline." The file `.harness/feature_list.json` acts as a contract between what the human asked for and what the agent built.

Before writing any code, the agent seeds this file from the product spec. Each feature gets an ID, a description, a priority, and a list of testable steps. For example, an invoice creation feature might have steps like "Send POST /api/invoices with 3 Widgets at $10", "Verify HTTP 201", "Verify response.subtotal equals 30.00." These steps are **locked** — the agent implementing the code cannot edit the descriptions, remove features, or reorder them.

Every feature starts with `"passes": false`. The agent can only flip it to `true` AFTER executing each step against the running application and seeing it succeed. Gate X6 automates this by sending real HTTP requests and driving a real browser. If the tax calculation is wrong — say 15% instead of 10% — the expected value from the feature list won't match the actual value from the running app, and the commit is blocked. The agent that wrote the code cannot grade its own homework.

The stop hook enforces this further: if the agent tries to exit with unverified features, it's blocked. You physically cannot claim completion without evidence.

---

## The Ratchet: Quality Can Only Go Up

The ratchet is stored in `.harness/baseline.json` and tracks eight metrics: lint errors, format errors, import violations, architecture violations, golden principle violations, TODO/FIXME count, God file count, and test coverage ratio.

When you bootstrap a project, the current values become the baseline. From that point forward, every run of `validate.sh` compares the current values to the baseline. If any metric is *worse* than the baseline, the commit is blocked. If you fix violations and the numbers go down, the baseline updates to the new lower value. This creates a ratchet effect — violations can only decrease over time, never increase.

For an existing codebase that has 50 lint errors, the ratchet doesn't demand you fix all 50 on day one. It just demands you never create a 51st one. Over time, as you naturally fix errors while working on features, the count drops, and each drop becomes the new floor.

---

## The End-to-End Flow

Putting it all together, here is what happens when you ask a harnessed project to build a feature:

You write a product requirement. The agent generates an execution plan in `docs/exec-plans/active/`. The agent seeds the feature list with locked, testable steps. The tester agent writes failing tests (adversarial TDD). The executor agent writes minimum code to pass those tests. After every edit, the post-edit hook runs project-specific checks in real time. When the agent tries to commit, the pre-commit hook runs all 25 validation gates. If any fail, the commit is blocked and the agent fixes the issue. When gates pass, the agent boots the app and runs live feature verification against the running application. If all features pass, the agent can commit. If it tries to exit without finishing, the stop hook blocks it. And the ratchet ensures that the codebase is at least as clean after the change as it was before.

No human reviewed the code. But the code was verified by an AST parser that checked every import, a security scanner that checked for secrets and CWE vulnerabilities, a test suite that checked every function, a browser that drove every page, an HTTP client that tested every endpoint, and a ratchet that confirmed quality didn't regress. That's the harness.

---

## Key Insight

The fundamental architectural insight of harness engineering is the **separation of specification from implementation**. The feature list is written before code, its steps are locked, and the agent that implements the code is not the one deciding if it works. This mirrors a principle from formal verification: the specification and the proof must be independent. If the same entity writes both the code and the test, the test will inevitably confirm what was written rather than what was intended. By separating these concerns mechanically — through locked feature steps, independent test runners, and AST-based enforcement — the system achieves a level of assurance that human review cannot match at scale.
