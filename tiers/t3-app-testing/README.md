# Tier 3: App Testing Gates

> Status: **Skeleton** — not yet implemented. This README explains the concept for stakeholder alignment.

## The Problem

Every team boots their app differently: some use `docker-compose up`, some use `npm run dev`, some have a 47-step wiki page. When a CI gate or AI agent needs to test the running app, it can't — because there's no standard way to start it.

## The Solution: boot.sh Contract

Every repo provides a `boot.sh` that:
1. Starts the application (however it needs to)
2. Waits until it's ready (health check loop)
3. Writes `instance-metadata.json` with connection details

```json
{
  "base_url": "http://localhost:3000",
  "api_url": "http://localhost:8000",
  "health_endpoint": "/health",
  "ready": true,
  "started_at": "2026-03-18T10:00:00Z"
}
```

## Gate Categories

### T3.1 Boot Gate
- Run `boot.sh`
- Verify `instance-metadata.json` was created
- Verify health endpoint returns 200

### T3.2 API Smoke Tests
- Hit key API endpoints with known-good requests
- Verify response shapes match expected schemas
- Configurable endpoint list in `.harness/t3/smoke-tests.json`

### T3.3 UI Legibility
- Screenshot key pages
- Verify no blank pages, no giant error messages
- Check text is readable (contrast ratios)

### T3.4 E2E Critical Paths
- Playwright-based end-to-end tests
- Cover the 3-5 most critical user flows
- Configurable in `.harness/t3/e2e-paths.json`

## Enterprise Value

T3 is where the harness starts testing *behavior*, not just *code*. The boot.sh contract means any automation (CI, AI agents, QA) can start and test any repo the same way.

## Implementation References

These scripts on the `master` branch contain logic that will be adapted for T3:
- `scripts/boot_worktree.sh` — worktree-based app booting
- `scripts/playwright_gate.py` — Playwright-based UI testing
- `scripts/check_ui_legibility.sh` — UI legibility checks

## Planned Files

```
tiers/t3-app-testing/
├── README.md           ← you are here
├── install.sh          (placeholder)
└── validate-t3.sh      (placeholder)
```
