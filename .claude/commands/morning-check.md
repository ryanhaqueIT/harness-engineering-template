Morning health check — run daily to catch issues early.

## Steps

1. Run `bash scripts/validate.sh` from the repo root. Report any gate failures with the gate ID and error message.
2. Run `python scripts/ratchet.py` from the repo root. Check for quality regressions against the baseline.
3. Run `python scripts/harness_scorecard.py` from the repo root. Report the current grade.
4. Run `git log --oneline -10` to summarize recent changes.
5. If any gate failed or quality regressed:
   - Identify **what** broke (gate ID, metric name)
   - Identify **when** it broke by checking `git log --oneline -20` and correlating with the failure
   - Suggest a **specific fix** (not generic advice — name the file and change needed)
6. If everything passes, report a clean bill of health with the current grade and gate pass count.

## Output Format

```
MORNING CHECK — [DATE]
Grade: [A/B/C/D/F]  |  Gates: [X/Y passed]  |  Ratchet: [OK/REGRESSED]

[If issues found:]
ISSUES:
  1. [Gate ID] — [description] — broke in [commit hash] — fix: [specific action]

[Recent changes summary — 1 line per commit]
```

## Usage

Run on-demand:
```
/morning-check
```

Or schedule for daily runs:
```
/loop every morning run /morning-check
```

This is designed to be the first thing you run each day. It catches regressions before they compound.
