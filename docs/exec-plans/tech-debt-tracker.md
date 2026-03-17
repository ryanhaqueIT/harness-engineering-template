# Tech Debt Tracker

Known technical debt, prioritized by impact. Background agents scan for
deviations and open fix-up PRs on a regular cadence.

## Active Debt

| ID | Description | Impact | Status |
|----|-------------|--------|--------|
| TD-01 | [Description of first known debt item] | High/Med/Low | Open |
| TD-02 | [Description of second known debt item] | High/Med/Low | Open |

## Resolved Debt

| ID | Description | Resolved | Resolution |
|----|-------------|----------|------------|
| TD-R1 | [Example: Fixed flaky test in CI] | 2026-01-15 | Added retry logic and fixed race condition |

## How to Add Items

When you discover technical debt during implementation:
1. Add a row to the Active Debt table with a unique ID (TD-XX)
2. Describe the debt clearly and concisely
3. Rate impact: **High** (blocks features or causes bugs), **Med** (slows development), **Low** (cosmetic or minor)
4. Set status to **Open**

When you resolve technical debt:
1. Move the row from Active to Resolved
2. Change the ID prefix to TD-R
3. Add the resolution date and a brief description of the fix
