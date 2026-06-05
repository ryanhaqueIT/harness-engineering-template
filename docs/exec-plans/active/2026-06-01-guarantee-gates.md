# Guarantee Gates — Design Spec

**Date:** 2026-06-01
**Branch:** `feat/guarantee-gates`
**Status:** ACTIVE

## Problem

The harness markets behavioral enforcement, but several of its flagship gates are
**PROXIED, not GUARANTEED** — they trust a self-report or check an artifact's
existence rather than re-deriving the fact they claim to enforce. A sufficiently
motivated (or careless) agent can satisfy the gate without satisfying the intent.

Three concrete holes:

1. **`stop_verification.py` trusts `passes: true`.** The Stop gate counts features
   where `f.get("passes")` is truthy and blocks exit only when `passing < total`.
   Nothing re-runs the feature. An agent can flip `passes: true` in
   `.harness/feature_list.json` with zero evidence and the gate is satisfied. The
   "evidence over claims" rule in AGENTS.md is enforced by *honor system*, not by
   the hook.

2. **The Stop gate is unwired.** `.claude/settings.json` declares `"Stop": []`, so
   `stop_verification.py` never runs at all. Even the proxied check is dead code in
   the live harness — a *hoped-for* gate masquerading as a guaranteed one.

3. **`check_tdd.py` checks existence, not meaning.** Gate X10 verifies that a test
   *file* exists at a candidate path (and, in `--strict`, that it was committed
   first). It explicitly "does NOT look inside files." An empty `test_foo.py`, or
   one that asserts nothing, passes. The test could never have failed, so it proves
   nothing about the code.

The unifying defect: a gate that *proxies* a property (a flag, a filename, a commit
timestamp) is only as trustworthy as the thing producing the proxy. To **guarantee**
a property, the gate must re-derive it from ground truth — run the command, observe
the failure, inspect the output — inside the gate itself.

## Solution — 4 Components

### A. Re-derivation Stop gate (`scripts/stop_verification.py`, rewrite)

Replace the `passes: true` trust with re-execution. For each feature carrying a
`verify` block, run `verify.cmd` and confirm `verify.expect` appears in the combined
stdout/stderr. A feature is "verified" **only** if its command actually produces the
expected output *now*, regardless of the stored `passes` flag.

- Block Stop when any feature with a `verify` block fails re-derivation (in
  `verifying`/`shipping`/`none` states; `building` warns as today).
- Features without a `verify` block fall back to the legacy `passes` check (so an
  empty feature list and template repos still behave).
- Honor `stop_hook_active` to prevent infinite loops; preserve the
  `researching`/`planning` free-exit paths.
- **Wire it:** add the Stop hook entry to `.claude/settings.json` so the gate is
  live. *(Done in a later serial step — this PR must not touch `settings.json`.)*

### B. `scripts/check_mutation.py` (new) — ungameable TDD

Make TDD *meaningful*, not merely *present*. Apply a small semantic mutation to an
application source file (e.g. flip a boolean default, swap `==`→`!=`, replace a
return value), then run that file's mapped test suite. The mutation must make a
mapped test **fail**. If every test still passes under mutation, the tests don't
constrain the code — the gate fails.

- Reuses `check_tdd.py`'s impl→test mapping (`candidate_test_paths`) to know which
  tests to run per source file.
- Always restores the source file (try/finally; never leave a mutated tree).
- Surviving mutants are reported as violations; exit non-zero.
- Complements X10: X10 proves a test *exists* before the code; X-mut proves the
  test *bites*.

### C. `.claude/hooks/shell-guard.sh` (new) — destructive-command denylist

A `PreToolUse` hook on `Bash` that **DENYLISTS** known-destructive commands before
they execute. Reads the hook JSON on stdin, extracts `tool_input.command`, matches
it against a denylist (e.g. `rm -rf /`, `rm -rf ~`, `git push --force` to protected
refs, `:(){ :|:& };:`, `dd of=/dev/`, `mkfs`, `chmod -R 777 /`, history/`.git`
deletion), and emits a block decision (`permissionDecision: deny` with a reason) on
match. Default is allow — this is a denylist, not an allowlist, so it never blocks
ordinary work. Append to the existing `PreToolUse` array in `settings.json` in the
later serial step.

### D. `scripts/check_tiers.py` (new) — gate honesty classifier

Classify every gate by enforcement tier so the harness can't lie about its own
guarantees:

- **guaranteed** — re-derives ground truth (e.g. component A, B, validate.sh sub-gates).
- **proxied** — trusts a flag/artifact (e.g. legacy `passes`, X10 file-existence).
- **hoped-for** — declared but unwired (e.g. a Stop hook with `"Stop": []`).

Cross-references declared gates against `.claude/settings.json` wiring. With
`--strict`, **fail (exit non-zero) if any gate declared `guaranteed` is actually
unwired or downgraded to hoped-for.** This turns "we guarantee X" into a checkable
claim and prevents regressions like the dead Stop hook from recurring silently.

## New `feature_list` verify-block schema

Each feature in `.harness/feature_list.json` MAY carry an optional `verify` block.
Its presence is what upgrades a feature from proxied (`passes`) to guaranteed
(re-derived) enforcement.

```json
{
  "id": "feature-key",
  "description": "...",
  "passes": false,
  "verify": {
    "cmd": "<shell command to run>",
    "expect": "<substring that must appear in the command's output>"
  }
}
```

- `cmd` — shell command executed from the repo root; combined stdout+stderr captured.
- `expect` — substring that must appear in that output for the feature to count as
  verified. Exact-substring match (no regex) to keep the contract trivial to author
  and impossible to misread.
- Backward compatible: features without `verify` use the legacy `passes` check, so
  existing/template feature lists are unaffected.

## Conventions / constraints

- Python 3.11+, type hints, module docstring per script; exit `0`=pass / non-zero=fail.
- Match the style of `scripts/check_tdd.py` (argparse CLI, `--strict`, `--summary`,
  `--files` override; `REPO_ROOT` from `__file__`).
- Tests live in `scripts/tests/`. **Iron Law:** failing test first, confirm it fails
  for the right reason, then implement to green.
- This PR does **not** edit `.claude/settings.json`, `scripts/validate.sh`, or
  `AGENTS.md` — wiring of the Stop hook, the `shell-guard` PreToolUse entry, and the
  new validate.sh gates happens in a later serial step.
