Check and report on the feature list status.

1. Read `.harness/feature_list.json`
2. For each feature with `passes: false`:
   - Report the feature ID, description, category, and priority
   - Show the verification steps
3. Pick the highest-priority failing feature
4. Implement it
5. Verify it using the steps listed (run tests, curl endpoints, drive browser if UI feature)
6. Only after successful verification, update the feature's `passes` to `true`, `verified_by` to "claude", and `verified_at` to current ISO timestamp
7. NEVER edit feature descriptions or remove features
8. NEVER flip passes to true without actually verifying
9. Commit your changes
10. Report: "Feature [ID] verified. [X/Y] features now passing."
