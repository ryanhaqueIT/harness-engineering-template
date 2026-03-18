# Tier 4: Product Verification Gates

> Status: **Skeleton** — not yet implemented. This README explains the concept for stakeholder alignment.

## The Problem

Engineers build features. Product managers write requirements. But the bridge between them — *did we actually build what was specified?* — is usually a manual review or a Jira status update. Nobody mechanically verifies the product works as described.

## The Solution: PRD Bridge via feature_list.json

Requirements from Jira/Confluence/PRDs are extracted into a structured `feature_list.json`:

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
