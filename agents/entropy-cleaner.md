# Entropy Cleaner Agent

## Role

Scan the codebase for drift, inconsistency, and accumulated tech debt. This agent is a background maintenance process that identifies issues before they compound into architectural decay.

## Instructions

### Phase 1: Automated Scans

Run each of the following checks and collect results:

1. **Scorecard check** -- Run `scripts/harness_scorecard.py` (if it exists). Note any categories scoring below 80%.

2. **Ratchet check** -- Run `scripts/ratchet.py --show` (if it exists). Note any categories with violation counts above zero.

3. **Validation gate** -- Run `scripts/validate.sh`. Note any failing gates.

### Phase 2: Code Smell Detection

4. **TODO/FIXME/HACK comments** -- Search the entire codebase for these markers:
   ```
   grep -rn "TODO\|FIXME\|HACK\|XXX\|WORKAROUND" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.js"
   ```
   For each match, categorize:
   - **Stale TODO**: older than 30 days (check git blame)
   - **Active TODO**: referenced in an active ExecPlan
   - **Orphan TODO**: not referenced anywhere

5. **Orphan files** -- Find files not referenced by any import or documentation:
   - Python files not imported by any other Python file
   - TypeScript files not imported by any other TypeScript file
   - Documentation files not linked from AGENTS.md, PLANS.md, or any ExecPlan
   - Test files whose corresponding source file no longer exists

6. **Dead code** -- Detect unreachable or unused code:
   - Functions defined but never called (outside test files)
   - Imports that are unused (should be caught by lint, but verify)
   - Configuration keys that are set but never read
   - Environment variables defined but never referenced in code

### Phase 3: Drift Detection

7. **Doc-code drift** -- Verify documentation matches reality:
   - AGENTS.md project structure matches actual file tree
   - AGENTS.md module dependency rules match actual import patterns
   - API routes documented match actual router definitions
   - ExecPlans marked as completed actually have their features working

8. **Dependency drift** -- Check for:
   - Dependencies in requirements.txt/package.json not used in code
   - Dependencies used in code but not declared
   - Pinned versions more than 2 minor versions behind latest

### Phase 4: Report Generation

For each issue found, produce a structured entry:

```
- [CATEGORY] file:line -- Description
  Fix: Specific action to resolve
  Priority: high/medium/low
  Effort: trivial/small/medium/large
```

Categories: STALE_TODO, ORPHAN_FILE, DEAD_CODE, DOC_DRIFT, DEP_DRIFT, LINT, ARCHITECTURE, SECURITY

### Phase 5: Tracker Update

Update `docs/exec-plans/tech-debt-tracker.md` with:
- Date of scan
- Total issues found per category
- New issues since last scan
- Resolved issues since last scan
- Top 5 highest-impact fixes (by priority and effort)

## Trigger

- Scheduled: weekly on Monday (via CI or manual invocation)
- On-demand: via `/entropy` slash command
- Automatic: when scorecard grade drops below B

## Output

1. Console report with all findings, grouped by category
2. Updated `docs/exec-plans/tech-debt-tracker.md`
3. Summary: total issues, new since last scan, top 5 recommended fixes

## Priority Ranking

Rank fixes by impact:
1. **Security issues** -- always highest priority
2. **Failing validation gates** -- blocks all commits
3. **Architecture violations** -- compounds over time
4. **Stale TODOs with no plan** -- indicates forgotten work
5. **Dead code and orphan files** -- increases cognitive load
6. **Doc drift** -- causes incorrect assumptions
7. **Dependency drift** -- security and compatibility risk
