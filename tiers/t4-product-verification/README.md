# Tier 4: Product Verification Gates

> Status: **Skeleton** — not yet implemented. This README explains the concept for stakeholder alignment.

## The Problem

Engineers build features. Product managers write requirements. But the bridge between them — *did we actually build what was specified?* — is usually a manual review or a Jira status update. Nobody mechanically verifies the product works as described.

## The Inputs: PRD + ERD

Every product needs two artifacts to be fully specified:

- **PRD (Product Requirements Document)** — defines *what* the product does: features, user flows, acceptance criteria. This feeds `feature_list.json`.
- **ERD (Entity Relationship Diagram)** — defines *how* the data is structured: entities, relationships, constraints. This informs T3's API smoke tests (correct response shapes) and T2's architectural rules (which modules own which data).

Together, the PRD and ERD are the complete specification. T4 verifies the product against the PRD. The ERD ensures the data model underneath is correct.

## The Solution: PRD Bridge via feature_list.json

Requirements from the PRD are extracted into a structured `feature_list.json`:

```json
{
  "features": [
    {
      "id": "F001",
      "description": "Health endpoint returns 200 with JSON status",
      "steps": [
        "Send GET /health",
        "Verify HTTP 200 response",
        "Verify JSON body contains {\"status\": \"healthy\"}"
      ],
      "passes": false
    }
  ]
}
```

Each feature has **immutable steps** — the exact verification procedure. No interpretation, no judgment calls. Either the step passes or it doesn't.

## Gate Categories

### T4.1 Feature Completeness
- Parse `feature_list.json`
- Check that all features have been verified at least once
- Report coverage: X of Y features passing

### T4.2 API Verification
- For features with API steps: execute them against the running app
- Compare actual responses to expected responses
- Uses instance-metadata.json from T3 boot

### T4.3 UI Verification
- For features with UI steps: use Playwright to navigate and verify
- Screenshot evidence for each step
- Stored in `.harness/evidence/`

## Enterprise Value

T4 closes the loop between product requirements and code. Stakeholders can see exactly which features are verified, which are broken, and which haven't been tested yet. It's the mechanical answer to "are we done?"

## Implementation References

These scripts on the `master` branch contain logic that will be adapted for T4:
- `scripts/check_features.py` — feature list validation
- `scripts/check_features_live.py` — live feature verification
- `.harness/feature_list.json` — example feature list (kept in place as reference)

## Planned Files

```
tiers/t4-product-verification/
├── README.md           ← you are here
├── install.sh          (placeholder)
└── validate-t4.sh      (placeholder)
```
