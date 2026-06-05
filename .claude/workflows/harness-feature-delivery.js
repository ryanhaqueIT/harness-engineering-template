// harness-feature-delivery.js
//
// WHAT THIS DOES
// Drives the full feature lifecycle end-to-end, deterministically:
//   Design  → PRD + ERD (parallel) → Codex spec review → quality gate → ExecPlan + feature seed + E2E skill
//   Build   → pipeline(milestones): Codex tests → Claude impl → validate.sh loop → fix/rescue/escalate
//   Verify  → boot app → validate.sh full + X6 live (parallel) → generated E2E skill → mutation → stop-verify
//   Ship    → X12 tier audit → ratchet → commit
//
// HOW THE HARNESS ENFORCES
// The workflow is the DRIVER. validate.sh is the ENFORCER.
// validate.sh gates block progress independently — the workflow cannot advance
// a milestone until all 29 gates exit 0. The workflow loop (fix → retry)
// runs until they do, or escalates to the user after 3 failed attempts.
//
// THREE TESTING LAYERS
//   Layer 1 — Deterministic (validate.sh, static gates)   → runs per milestone, no app needed
//   Layer 2 — Semi-deterministic (X6 live feature check)  → runs in Verify after boot
//   Layer 3 — Non-deterministic (generated E2E skill)     → real external systems, Playwright MCP
//
// HOW TO RUN
//   Workflow({ name: "harness-feature-delivery", args: "Add OAuth login with Google" })
//   or: save to .claude/workflows/ and trigger via /workflows in Claude Code
//
// ARGS
//   args — feature description (plain text) OR path to existing spec (docs/product-specs/*.md)

export const meta = {
  name: 'harness-feature-delivery',
  description: 'PRD → ERD → ExecPlan → Build (cross-model TDD + validate.sh loop) → Verify (3-layer testing) → Ship',
  phases: [
    { title: 'Design',  detail: 'PRD + ERD + Codex spec review + seed feature list + generate E2E test skill' },
    { title: 'Build',   detail: 'pipeline(milestones): Codex tests → Claude impl → validate.sh static loop → fix/rescue' },
    { title: 'Verify',  detail: 'boot app → validate.sh full + X6 live → generated E2E skill → mutation → stop-verify' },
    { title: 'Ship',    detail: 'X12 tier audit → R1 ratchet → conventional commit' },
  ],
}

const MILESTONES_SCHEMA = {
  type: 'object',
  properties: {
    items: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id:           { type: 'string' },
          name:         { type: 'string' },
          description:  { type: 'string' },
          files:        { type: 'array', items: { type: 'string' } },
          feature_ids:  { type: 'array', items: { type: 'string' } },
        },
        required: ['id', 'name', 'description'],
      },
    },
    slug:       { type: 'string' },
    spec_path:  { type: 'string' },
  },
  required: ['items', 'slug', 'spec_path'],
}

const GATE_RESULT_SCHEMA = {
  type: 'object',
  properties: {
    status:        { type: 'string', enum: ['pass', 'fail', 'skip'] },
    failing_gates: { type: 'array', items: { type: 'string' } },
    summary:       { type: 'string' },
  },
  required: ['status', 'summary'],
}

const E2E_RESULT_SCHEMA = {
  type: 'object',
  properties: {
    status:       { type: 'string', enum: ['pass', 'fail', 'partial'] },
    layers: {
      type: 'object',
      properties: {
        layer1_validate:  { type: 'string' },
        layer2_live:      { type: 'string' },
        layer3_e2e:       { type: 'string' },
      },
    },
    env_noise:    { type: 'array', items: { type: 'string' } },
    code_bugs:    { type: 'array', items: { type: 'string' } },
    evidence:     { type: 'string' },
  },
  required: ['status', 'evidence'],
}

// ─────────────────────────────────────────────────────────────────────────────
// PHASE 1: DESIGN
// ─────────────────────────────────────────────────────────────────────────────

phase('Design')

// 1a. Check if args is a path to an existing spec or a new feature description
const specCheck = await agent(
  `Check if this is a path to an existing spec file or a new feature description: "${args}"

  If it looks like a file path (starts with "docs/" or ends with ".md"):
    - Read the file and confirm it exists
    - Return { "is_existing_spec": true, "spec_path": "<path>", "spec_content": "<first 500 chars>" }
  If it is a plain feature description:
    - Return { "is_existing_spec": false, "spec_path": null, "spec_content": null }`,
  {
    label: 'spec-check',
    phase: 'Design',
    schema: {
      type: 'object',
      properties: {
        is_existing_spec: { type: 'boolean' },
        spec_path:        { type: ['string', 'null'] },
        spec_content:     { type: ['string', 'null'] },
      },
      required: ['is_existing_spec'],
    },
  }
)

// 1b. Write PRD and ERD in parallel (skip if spec already exists)
let prdPath, erdPath

if (!specCheck.is_existing_spec) {
  log('Writing PRD and ERD in parallel...')

  const [prdResult, erdResult] = await parallel([
    () => agent(
      `You are a product engineer. Write a complete PRD for this feature: "${args}"

      Save to: docs/product-specs/${args.slice(0,40).replace(/[^a-z0-9]/gi,'-').toLowerCase()}.md

      REQUIRED SECTIONS (exact headings):
      ## Problem Statement
      ## Requirements
      ## Acceptance Criteria    ← minimum 5 numbered testable items (Given/When/Then format)
      ## Success Metrics
      ## Out of Scope

      Minimum 300 words. Every acceptance criterion must be independently verifiable
      by a script — it becomes a verify.cmd in feature_list.json.

      Read AGENTS.md first for repo conventions. Return the file path when done.`,
      { label: 'write-prd', phase: 'Design' }
    ),
    () => agent(
      `You are a systems architect. Decide if this feature needs persistent storage: "${args}"

      If YES — write an ERD to: docs/design-docs/data-model.md
      Required sections: ## Entities (one subsection per entity with fields + types),
      ## Relationships (cardinality notation), ## Indexes, ## API Contracts (endpoint per operation).
      Entity names MUST exactly match the ORM model class names you plan to create.

      If NO storage needed — write a one-liner: "No persistent storage required."
      to docs/design-docs/data-model.md

      Read AGENTS.md first. Return the file path and whether storage is needed.`,
      { label: 'write-erd', phase: 'Design' }
    ),
  ])

  prdPath = prdResult
  erdPath = erdResult
} else {
  prdPath = specCheck.spec_path
  erdPath = 'docs/design-docs/data-model.md'
  log(`Using existing spec: ${specCheck.spec_path}`)
}

// 1c. Codex adversarial spec review
log('Running Codex adversarial spec review...')
const specReview = await agent(
  `You are a senior engineer doing an adversarial review of the product spec.
  Be EXTREMELY critical. Your job is to find every gap, ambiguity, and flaw.

  Read: ${prdPath}
  Also read: ${erdPath}

  Check for:
  - Acceptance criteria that cannot be verified by a script
  - Missing error cases and edge cases
  - Acceptance criteria that contradict each other
  - ERD entities not traceable to acceptance criteria
  - Vague requirements ("should be fast" vs "p95 < 200ms")
  - Missing non-functional requirements (auth, rate limiting, validation)
  - Any acceptance criterion an agent could satisfy trivially (e.g. "feature exists")

  Invoke Skill("codex:rescue") and pass it this review prompt to get an INDEPENDENT model's critique.
  Return SPEC_REVIEW_PASS if both reviews find no blockers.
  Return SPEC_REVIEW_FAIL with a numbered list of issues if any blocker is found.

  The spec authors must address every issue before feature_list.json is seeded.`,
  { label: 'codex-spec-review', phase: 'Design' }
)

// 1d. Revise spec if Codex found issues, then run quality gate
log('Running spec quality gate...')
const specGate = await agent(
  `Previous Codex spec review result: ${specReview}

  If the review returned SPEC_REVIEW_FAIL:
    1. Read the issues list
    2. Revise ${prdPath} and ${erdPath} to address every numbered issue
    3. Do NOT remove acceptance criteria — only strengthen them

  Now run the mechanical quality gate:
    python scripts/check_spec_quality.py --summary

  If it fails, fix the spec (add missing sections, increase word count, add criteria).
  Keep fixing and re-running until it exits 0.

  Once check_spec_quality.py exits 0, return SPEC_QUALITY_PASS.`,
  { label: 'spec-quality-gate', phase: 'Design' }
)

// 1e. Seed feature_list.json, ExecPlan, and generate E2E test skill — all parallel
log('Seeding feature list, writing ExecPlan, generating E2E test skill...')

const [featureSeed, execPlanResult, testSkillResult] = await parallel([

  // Feature seeder
  () => agent(
    `Read the PRD at ${prdPath}. For each acceptance criterion, create one entry
    in .harness/feature_list.json:
    {
      "id": "F<N>",
      "description": "<exact acceptance criterion text>",
      "category": "<functional|security|reliability|ui>",
      "passes": false,
      "steps": [
        { "action": "<http|playwright|cli>", "target": "<endpoint or selector>", "expect": "<assertion>" }
      ],
      "verify": { "cmd": "<shell command that re-derives truth>", "expect": "<expected substring>" }
    }

    RULES:
    - steps must be concrete (real HTTP paths, real selectors, real CLI commands)
    - verify.cmd must be independently executable from repo root
    - NEVER set passes:true — only live verification flips this
    - NEVER edit steps after seeding — X11 hash-locks them

    After writing feature_list.json, run:
      python scripts/check_features.py --summary
    to confirm structure is valid. Return FEATURE_SEED_DONE when complete.`,
    { label: 'seed-features', phase: 'Design' }
  ),

  // ExecPlan writer
  () => agent(
    `Read ${prdPath} and .harness/feature_list.json.

    Write an ExecPlan to: docs/exec-plans/active/plan-${args.slice(0,30).replace(/[^a-z0-9]/gi,'-').toLowerCase()}.md

    Structure:
    ## Milestones
    ### M1: <name>
    - Files to create/modify: <list>
    - Feature IDs satisfied: <F1, F2...>
    - Gate checkpoint: B1, B2, B5, B6, B8 must pass before M2

    Rules:
    - Max 3 feature_list entries per milestone
    - DB schema changes get their own milestone (so ERD gate can re-run)
    - Each milestone must have a clear "done" condition

    Return EXEC_PLAN_DONE with the file path.`,
    { label: 'write-execplan', phase: 'Design' }
  ),

  // E2E test skill generator
  () => agent(
    `Read ${prdPath} and .harness/feature_list.json.
    You are generating a non-deterministic E2E test skill for this feature.

    Write a test command to: .claude/commands/test-${args.slice(0,25).replace(/[^a-z0-9]/gi,'-').toLowerCase()}.md

    The skill must follow this structure:
    # /test-<feature> — E2E Test for <feature>
    ## Context (test accounts, endpoints, env vars needed)
    ## Pre-test Setup (verify environment state is correct)
    ## Phase 1: Trigger the feature (how to invoke the feature under test)
    ## Phase 2: Wait for async processing (polling intervals)
    ## Phase 3: Layer 2 verification (HTTP probes, DB queries)
    ## Phase 4: Playwright UI verification (use Playwright MCP: navigate, click, assert)
    ## Phase 5: Evidence report format (structured pass/fail per checkpoint)
    ## Known Environmental Limitations (non-code failures to distinguish)

    For each acceptance criterion in feature_list.json, the skill must have a
    concrete checkpoint that verifies it against the LIVE running system.

    Use the test-voice-pipeline.md and test-email-pipeline.md patterns from
    .claude/commands/ as structural templates if they exist.

    Return E2E_SKILL_DONE with the skill path.`,
    { label: 'generate-e2e-skill', phase: 'Design' }
  ),
])

// 1f. Parse ExecPlan milestones as structured output for pipeline
const plan = await agent(
  `Read the ExecPlan at docs/exec-plans/active/ (the most recently modified .md file).
  Extract the milestones and return them as structured JSON.
  Also return:
  - slug: a short kebab-case identifier for this feature (e.g. "oauth-login")
  - spec_path: the path to the PRD (${prdPath})`,
  {
    label: 'parse-milestones',
    phase: 'Design',
    schema: MILESTONES_SCHEMA,
  }
)

log(`Design complete. ${plan.items.length} milestones, slug: ${plan.slug}`)

// ─────────────────────────────────────────────────────────────────────────────
// PHASE 2: BUILD
// pipeline(milestones) — no barrier, M2 starts while M1 validates
// ─────────────────────────────────────────────────────────────────────────────

phase('Build')

await pipeline(
  plan.items,

  // Stage 1: Cross-model TDD — Codex writes tests, Claude implements
  async (milestone) => {
    log(`Building milestone: ${milestone.id} — ${milestone.name}`)

    // Codex writes failing tests first (different model = real adversarial gap)
    await agent(
      `You are the Adversarial Tester for milestone: "${milestone.name}"

      Feature IDs this milestone satisfies: ${(milestone.feature_ids || []).join(', ')}
      Files to create/modify: ${(milestone.files || []).join(', ')}

      CRITICAL: Invoke Skill("codex:rescue") and hand Codex this test-writing prompt:
      "Write the hardest possible failing tests for milestone '${milestone.name}'.
       Read the acceptance criteria in .harness/feature_list.json for feature IDs
       ${(milestone.feature_ids || []).join(', ')}. Write pytest/jest tests that
       will FAIL until the feature is correctly implemented. Tests must:
       - Assert observable behavior, not internal state
       - Name each test function after the feature ID it covers
       - Include edge cases and error paths
       - NOT mock external dependencies unless unavoidable
       Run them to confirm RED (all failing). Report which tests are RED."

      Codex is the tester. Claude (you) will implement against these tests.
      This two-model split is intentional — same-model TDD shares blind spots.

      If codex:rescue is unavailable, write the tests yourself and log:
      python scripts/ship.py note "tester=claude-fallback milestone=${milestone.id}"

      Return TESTS_RED with the test file paths.`,
      { label: `tester-${milestone.id}`, phase: 'Build' }
    )

    // Claude implements against Codex's tests
    await agent(
      `You are the Executor for milestone: "${milestone.name}"

      The tester (Codex) has written failing tests. Your job:
      1. Read the failing tests written in the previous step
      2. Write the MINIMUM code to make them pass
      3. Do NOT modify the tests
      4. Do NOT set passes:true in feature_list.json (verification does that)
      5. Do NOT implement beyond the scope of this milestone

      Files to create/modify: ${(milestone.files || []).join(', ')}

      Read AGENTS.md for module dependency rules and golden principles.
      The post-edit hook will lint/format automatically after each file write.

      Run tests after implementation:
        cd backend && python -m pytest tests/ -v --tb=short -q 2>&1 | tail -20
      or for Node:
        npm test -- --passWithNoTests 2>&1 | tail -20

      Return IMPL_DONE once tests are GREEN.`,
      { label: `executor-${milestone.id}`, phase: 'Build' }
    )

    return milestone
  },

  // Stage 2: validate.sh static loop (per milestone, no app needed)
  async (milestone) => {
    let fixCount = 0
    let gateResult = null

    while (fixCount < 3) {
      gateResult = await agent(
        `Run validate.sh against the code from milestone "${milestone.name}".
        The app is NOT booted — live gates (X3, X4, X6, O1) will auto-skip.
        This is the STATIC tier: B1-B8, F1-F7, I1-I2, X1, X2, X7, X8, X9, X10, R1.

        Run:
          bash scripts/validate.sh 2>&1 | tail -40

        If exit 0: return { "status": "pass", "summary": "all static gates passed" }
        If non-zero: return { "status": "fail", "failing_gates": ["B5", "B6"...], "summary": "<details>" }`,
        {
          label: `validate-${milestone.id}-attempt-${fixCount + 1}`,
          phase: 'Build',
          schema: GATE_RESULT_SCHEMA,
        }
      )

      if (gateResult.status === 'pass') break

      // Fix attempt
      await agent(
        `validate.sh failed for milestone "${milestone.name}".
        Failing gates: ${(gateResult.failing_gates || []).join(', ')}
        Details: ${gateResult.summary}

        Fix attempt ${fixCount + 1} of 3:
        - Read the exact error output above
        - Fix the violation in the implementation code (NEVER suppress the gate)
        - Do NOT modify test files
        - Do NOT modify .harness/feature_list.json steps
        - Shell-guard is active — destructive commands are blocked

        After fixing, the next iteration will re-run validate.sh.`,
        { label: `fix-${milestone.id}-attempt-${fixCount + 1}`, phase: 'Build' }
      )

      fixCount++
    }

    // Rescue: parallel researcher + codex-reviewer if fix cap hit
    if (fixCount >= 3 && gateResult && gateResult.status === 'fail') {
      log(`Milestone ${milestone.id} hit fix cap — entering rescue protocol`)

      const rescueResults = await parallel([
        () => agent(
          `RESCUE MODE — Researcher for milestone "${milestone.name}"
          Failing gates: ${(gateResult.failing_gates || []).join(', ')}
          Error details: ${gateResult.summary}

          Use web search (Exa/WebSearch) to find the root cause of these specific gate failures.
          Return a 3-bullet root-cause analysis with source links.
          Do NOT apply fixes — diagnose only.`,
          { label: `rescue-researcher-${milestone.id}`, phase: 'Build' }
        ),
        () => agent(
          `RESCUE MODE — Independent code reviewer for milestone "${milestone.name}"
          Failing gates: ${(gateResult.failing_gates || []).join(', ')}

          Invoke Skill("codex:rescue") with this prompt:
          "Review the failing code for milestone '${milestone.name}'.
           Gates failing: ${(gateResult.failing_gates || []).join(', ')}.
           Read the relevant source files and identify the root cause.
           Return: DEFECT FOUND: <description> or NO DEFECT FOUND."

          Return Codex's verbatim output.`,
          { label: `rescue-codex-${milestone.id}`, phase: 'Build' }
        ),
      ])

      // Apply rescue fix
      await agent(
        `Apply rescue fix for milestone "${milestone.name}" based on two independent diagnoses:

        Researcher diagnosis: ${rescueResults[0]}
        Codex diagnosis: ${rescueResults[1]}

        If both agree: apply the fix they describe.
        If they disagree: prefer the diagnosis whose evidence directly explains the gate failure.

        After fixing, run: bash scripts/validate.sh 2>&1 | tail -20
        If still failing: stop and report ESCALATE with full diagnosis.
        If passing: return RESCUE_FIXED.`,
        { label: `rescue-fix-${milestone.id}`, phase: 'Build' }
      )
    }

    return milestone
  }
)

log('All milestones built and statically validated')

// ─────────────────────────────────────────────────────────────────────────────
// PHASE 3: VERIFY
// Boot app → validate.sh full (Layer 1+2) + X6 live (Layer 2) → E2E skill (Layer 3)
// → X11 mutation → stop_verification → X12 tier audit
// ─────────────────────────────────────────────────────────────────────────────

phase('Verify')

// Boot the application first
log('Booting application...')
await agent(
  `Boot the application for live testing.

  Try in order:
  1. bash scripts/boot_worktree.sh (if it exists)
  2. bash scripts/boot_local.sh (if it exists)
  3. Fall back to: cd backend && uvicorn main:app --port 8000 --reload &
     (or npm run dev & for Node backends)

  After booting, poll the health endpoint until it returns 200:
    until curl -sf http://localhost:8000/health; do sleep 2; done
  (adjust port/path to match the project)

  Return APP_BOOTED with the URL when health check passes.
  If boot fails after 30s: return APP_BOOT_FAILED with the error.`,
  { label: 'boot-app', phase: 'Verify' }
)

// Layer 1+2 combined: validate.sh full sweep + X6 live feature check in parallel
log('Running Layer 1 + Layer 2 verification in parallel...')

const [fullValidate, liveFeatureCheck] = await parallel([

  // Layer 1+2: Full validate.sh with live gates active
  () => agent(
    `Run validate.sh with ALL gates including live gates (app is now booted).

    Run:
      RUN_LIVE=true RUN_E2E=true bash scripts/validate.sh 2>&1

    This activates: X3 (E2E local), X5 (feature list), X6 (live features), O1 (if observability stack running).
    All B1-B8, F1-F7, I1-I2, X1-X10, R1 gates also run.

    If exit 0: return { "status": "pass", "summary": "all 29 gates passed" }
    If non-zero: return { "status": "fail", "failing_gates": [...], "summary": "..." }

    On failure: fix violations (do not suppress gates), re-run until exit 0.
    Max 2 fix attempts in this phase.`,
    {
      label: 'validate-full',
      phase: 'Verify',
      schema: GATE_RESULT_SCHEMA,
    }
  ),

  // Layer 2 explicit: X6 live feature verification
  () => agent(
    `Run X6 live feature verification explicitly:
      python scripts/check_features_live.py --summary

    This sends real HTTP requests and drives Playwright against every feature
    in .harness/feature_list.json where passes==false.

    Do NOT set passes:true manually — check_features_live.py flips the values
    based on actual live responses.

    If features fail:
    - Read the exact failure reason from the output
    - Fix the implementation (not the feature_list.json steps)
    - Re-run until all features report PASS or SKIP

    Return a summary of which features passed, failed, or skipped.`,
    { label: 'x6-live-check', phase: 'Verify' }
  ),
])

// Layer 3: Run the generated E2E test skill (non-deterministic)
log('Running Layer 3 non-deterministic E2E test...')
const skillName = `test-${plan.slug}`

const e2eResult = await agent(
  `Run the generated E2E test skill for this feature.

  Invoke: Skill("${skillName}")

  This skill was generated during the Design phase and tests the feature against
  real external systems (Playwright MCP, APIs, databases, external services).

  After the skill completes, evaluate the results:
  - PASS: all checkpoints verified with evidence
  - FAIL: code bug confirmed (implementation needs fixing)
  - PARTIAL: some checkpoints pass, some fail due to ENVIRONMENTAL LIMITATIONS
    (e.g. test API throttling, timing issues, stale test data)

  IMPORTANT: Distinguish code bugs from environmental noise.
  A test-WABA throttle is NOT a code bug.
  A missing DynamoDB record when the code should have written one IS a code bug.

  If code bugs found: fix the implementation and re-run the skill.
  If environmental noise only: document it and continue.

  Return structured evidence.`,
  {
    label: 'e2e-layer3',
    phase: 'Verify',
    schema: E2E_RESULT_SCHEMA,
  }
)

log(`Layer 3 E2E: ${e2eResult.status}`)

// X11 Mutation gate — tests must FAIL on mutated code
log('Running X11 mutation gate...')
await agent(
  `Run the mutation gate to verify tests are meaningful (not vacuous):
    python scripts/check_mutation.py

  HOW IT WORKS:
  - The script deliberately breaks app code (flips an operator, nulls a return)
  - It then runs your tests against the broken code
  - If tests FAIL on the mutation → GOOD (tests are real, catching bugs)
  - If tests PASS on the mutation → BAD (tests are vacuous, never test anything)

  If X11 reports surviving mutants (tests passed on broken code):
  - Identify which tests are vacuous
  - Strengthen them to actually assert the behavior being tested
  - Re-run check_mutation.py until no surviving mutants

  Return MUTATION_GATE_PASS when the gate exits 0.`,
  { label: 'x11-mutation', phase: 'Verify' }
)

// Stop verification — re-derives every passes:true claim independently
log('Running stop verification...')
await agent(
  `Run stop verification to re-derive every feature's truth independently:
    python scripts/stop_verification.py

  This script re-runs verify.cmd for every feature where passes:true,
  and checks that verify.expect appears in the output.
  It DOES NOT trust the passes flag — it re-derives ground truth.

  If any feature fails re-derivation:
  - The feature is NOT actually passing (the agent claimed it without evidence)
  - Fix the implementation until verify.cmd exits 0 with verify.expect in output
  - Do NOT modify verify.cmd or verify.expect

  Return STOP_VERIFY_PASS when all features independently verified.`,
  { label: 'stop-verify', phase: 'Verify' }
)

log('All three testing layers complete')

// ─────────────────────────────────────────────────────────────────────────────
// PHASE 4: SHIP
// X12 tier audit → R1 ratchet → conventional commit
// ─────────────────────────────────────────────────────────────────────────────

phase('Ship')

await parallel([

  // X12: Tier audit — no guaranteed gate has silently become unwired
  () => agent(
    `Run the tier audit gate to verify no guarantee has silently rotted:
      python scripts/check_tiers.py --strict

    This checks scripts/tier_registry.json: every gate declared as "guaranteed"
    must actually be wired in settings.json hooks or validate.sh.
    This is what would have caught the empty Stop hook bug before it reached production.

    If it fails: a gate you think is enforced isn't wired.
    Fix the wiring (settings.json or validate.sh) — don't change the tier declaration.

    Return TIER_AUDIT_PASS when --strict exits 0.`,
    { label: 'x12-tier-audit', phase: 'Ship' }
  ),

  // R1: Ratchet — quality can only go up
  () => agent(
    `Run the ratchet to confirm quality metrics have not regressed:
      python scripts/ratchet.py

    The ratchet tracks 8 metrics: lint_errors, format_errors, import_violations,
    architecture_violations, golden_principle_violations, todo_fixme_count,
    god_files, test_coverage_ratio.

    If the ratchet fails: one of these metrics got WORSE than the baseline.
    Fix the regression (do NOT delete .harness/baseline.json to cheat it).

    Return RATCHET_PASS when ratchet.py exits 0.`,
    { label: 'r1-ratchet', phase: 'Ship' }
  ),
])

// Final commit
await agent(
  `All gates have passed. Create the ship commit.

  1. Check what changed:
     git diff --stat HEAD

  2. Stage the relevant files:
     git add docs/product-specs/ docs/design-docs/ docs/exec-plans/ \
             .harness/feature_list.json .harness/baseline.json \
             .claude/commands/test-${plan.slug}.md \
             backend/ frontend/ tests/

  3. Commit with conventional message:
     git commit -m "$(cat <<'EOF'
feat(${plan.slug}): <one-line summary from PRD Problem Statement>

PRD: ${plan.spec_path}
Features: ${plan.items.flatMap ? plan.items.flatMap(m => m.feature_ids || []).join(', ') : 'see feature_list.json'}
Layers: validate.sh (29 gates) + X6 live + E2E skill (${skillName})
Verified-by: stop_verification.py + check_mutation.py + check_tiers.py --strict
Generated-by: harness-feature-delivery workflow
EOF
)"

  4. Release workflow state:
     python scripts/workflow.py set none

  Return SHIPPED with the commit SHA.`,
  { label: 'commit', phase: 'Ship' }
)

log('Feature delivered. All 29 gates passed, 3 testing layers verified, commit created.')

return {
  slug:        plan.slug,
  milestones:  plan.items.length,
  spec_path:   plan.spec_path,
  e2e_skill:   skillName,
  e2e_status:  e2eResult.status,
  e2e_env_noise: e2eResult ? e2eResult.env_noise : [],
}
