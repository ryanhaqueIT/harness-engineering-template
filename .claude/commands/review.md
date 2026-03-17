Review the current git diff against harness engineering quality standards.

Follow this procedure exactly:

1. Read AGENTS.md for golden principles and module dependency rules.
2. Read docs/QUALITY_SCORE.md for the grading rubric.
3. Run `git diff --staged` to see staged changes. If empty, run `git diff` for unstaged changes. If both empty, run `git diff HEAD~1` for the last commit.
4. For each changed file, score against the rubric:
   - **Code Quality (1-5):** Type hints, structured logging, no print(), no hardcoded values, clean logic.
   - **Test Quality (1-5):** Happy path + edge cases + error cases. Mocks only external services.
   - **Architecture (1-5):** Module boundaries respected, one concern per file, no God files.
5. Run the security checklist (pass/fail):
   - No secrets in code (API keys, passwords, tokens)
   - Input validated at API boundaries
   - No injection vectors (SQL, NoSQL, command)
   - No path traversal in file operations
6. Run the reliability checklist (pass/fail):
   - Structured logging with logger.info/error (no print)
   - Correlation IDs in log messages
   - Graceful error handling (no bare except, no silent swallowing)
   - Timeouts on all external calls
7. If any score is below the minimum bar (Code >= 3, Test >= 3, Architecture >= 4) or any checklist fails:
   - List specific issues with `file:line` and fix instructions
   - State verdict: **CHANGES REQUESTED**
8. If all scores meet the bar and checklists pass:
   - State verdict: **LGTM**

Output the full scorecard at the end:
```
Code Quality:  X/5
Test Quality:  X/5
Architecture:  X/5
Security:      pass/fail
Reliability:   pass/fail
Verdict:       LGTM / CHANGES REQUESTED
```
