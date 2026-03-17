# Quality Score -- Grading Rubric for Every Change

Every change (PR, milestone, feature) is evaluated against this rubric.
Both the writing agent and the reviewing agent use this to determine "good enough."

## Code Quality (1-5)

| Score | Meaning |
|-------|---------|
| 5 | Clean, minimal, follows all golden principles. No unnecessary code. Every function typed. Structured logging. |
| 4 | Works correctly, follows principles, minor style nits. |
| 3 | Works but has issues: missing type hints, inconsistent patterns, slightly too coupled. |
| 2 | Works but violates a golden principle or has unclear logic. |
| 1 | Violates architecture boundaries, hardcoded values, no error handling. |

## Test Quality (1-5)

| Score | Meaning |
|-------|---------|
| 5 | Happy path + edge cases + error cases. Mocks only external services. Meaningful assertions. |
| 4 | Happy path + 1-2 edge cases. Good assertions. |
| 3 | Happy path only. Basic assertions. |
| 2 | Tests exist but are trivial or don't test real behavior. |
| 1 | Tests missing or meaningless (assert True). |

**Rule:** If a test needs more than 3 mocks, the code is too coupled. Refactor the code, don't add more mocks.

## Architecture Compliance (1-5)

| Score | Meaning |
|-------|---------|
| 5 | Respects all module boundaries. One concern per file. Clear separation. |
| 4 | Minor boundary stretch but justified and documented. |
| 3 | Mild coupling between layers but functional. |
| 2 | Business logic leaking into routers or DB access outside the data layer. |
| 1 | Major violations -- circular imports, God files, spaghetti dependencies. |

## Security (pass/fail)

- [ ] No secrets in code (API keys, passwords, tokens)
- [ ] Input validated at API boundaries
- [ ] Credentials encrypted at rest
- [ ] No path traversal in file operations
- [ ] No injection vectors (SQL, NoSQL, command)

## Reliability (pass/fail)

- [ ] Structured logging with logger.info/error (no print)
- [ ] Correlation IDs in log messages
- [ ] Graceful error handling (no bare except, no silent swallowing)
- [ ] Timeouts on all external calls
- [ ] Idempotent operations where possible

## Minimum Bar for Merge

- Code Quality: >= 3
- Test Quality: >= 3
- Architecture: >= 4
- Security: all pass
- Reliability: all pass
- validate.sh: exit 0
