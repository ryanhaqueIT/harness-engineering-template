# Core Technical Beliefs

These are opinionated technical decisions that guide every implementation choice.
They are not up for debate during implementation -- they are locked decisions.

## 1. The Spec Is The Product

Code is an implementation detail. The spec (docs/product-specs/) defines what the product does.
If the code works but doesn't match the spec, the code is wrong.
If the spec is wrong, update the spec FIRST, then update the code.

## 2. Configuration Is Not Code

Configuration (environment variables, feature flags, user data) is loaded at runtime from
external sources. It is NEVER hardcoded, NEVER generated at build time, NEVER approximated.
If configuration can't be loaded, the service should fail fast with a clear error.

## 3. Data Access Is Centralized

All database access goes through a dedicated data layer. No other module may import the
database client directly. This makes it possible to:
- Mock the data layer in tests without touching the DB client
- Change the database without touching business logic
- Enforce access patterns and query boundaries

## 4. External API Calls Are Functions, Not Services

Calls to external APIs (AI models, third-party services) are functions that run inline
in the calling process. They are NOT separate microservices. This means: no network
round-trips between internal components. The function calls the API, gets the response,
and returns it. Keep it simple.

## 5. One Service Does One Thing Well

Prefer a single backend service that handles all API routes, webhooks, and background tasks.
This simplifies deployment, reduces latency, and eliminates inter-service communication.
Split only when there is a clear scaling or isolation requirement, not for organizational reasons.

## 6. Tests Test Behavior, Not Implementation

A good test: "POST /api/users returns 201 with a user object containing an id field"
A bad test: "UserService._validate_email() calls regex.match 3 times"

Tests verify what the USER sees, not how the code is structured internally.
When we refactor, tests don't break.

## 7. Corrections Are Cheap, Waiting Is Expensive

Merge fast. Fix forward. A small bug that ships and gets fixed in 30 minutes
is better than a perfect PR that blocks for 3 hours of review.

This doesn't mean quality doesn't matter -- it means the harness (validate.sh,
CI, agent review) catches issues fast enough that blocking is wasteful.
