# Reliability Principles

## Logging
- ALL logging via the language's standard logging framework (Python `logging`, Node `pino`/`winston`, Go `slog`)
- Structured JSON logging in production
- Include correlation_id in every log message for request tracing
- Log levels: DEBUG for development, INFO for normal operations, ERROR for failures
- NEVER use print() or console.log() in production code -- it bypasses the logging infrastructure

## Error Handling
- Fail fast: if something is wrong, raise or return immediately
- Specify exception types: `except ValueError as e:` not bare `except:`
- Log the error with context: `logger.error("Failed to process order %s: %s", order_id, e)`
- Return meaningful errors to API callers (4xx for client errors, 5xx for server errors)
- Never silently swallow errors -- every catch/except block must log

## Timeouts
- Set explicit timeouts on ALL external calls
- AI/ML API calls: 30 second timeout
- Database operations: 5 second timeout
- Third-party API calls: 10 second timeout
- HTTP client requests: 15 second timeout
- WebSocket connections: use keepalive pings every 30 seconds
- Document timeout values in this file for reference

## Idempotency
- Webhook handlers and event processors must be idempotent
- Use an idempotency store (database table with TTL, Redis key) to track processed events
- If an event was already processed (hash/ID exists), skip silently
- Design state mutations to be safely repeatable

## Graceful Degradation
- If a non-critical service fails, degrade gracefully rather than crashing
- If an AI/ML service fails, return a fallback response and log ERROR
- If the database fails during a read, serve from cache if available
- If a third-party API fails, queue the operation for retry
- Always communicate degraded state to the user (don't pretend everything is fine)

## Health Checks
- Expose a `/health` endpoint that returns HTTP 200 when the service is healthy
- Health checks should verify critical dependencies (database, cache, message queue)
- Return structured JSON: `{"status": "healthy", "dependencies": {"db": "ok", "cache": "ok"}}`
- Use health checks for load balancer routing and deployment readiness gates
