# Security Rules

## Authentication
- Authenticate all user-facing endpoints with your auth provider
- JWT verification on every API request (except /health and public webhooks)
- Tokens should expire within a reasonable window; use refresh tokens for renewal
- Never trust client-side auth alone; always verify server-side

## Secrets Management
- ALL secrets in a secret manager (AWS Secrets Manager, GCP Secret Manager, Vault) or environment variables
- NEVER in code, .env files committed to git, or documentation files
- OAuth client credentials: secret manager
- Encryption keys: secret manager
- Third-party API tokens: secret manager
- Rotate secrets on a regular cadence

## Data Protection
- Encrypt sensitive data at rest (OAuth tokens, PII, credentials)
- No PII in logs (mask email addresses, phone numbers, SSNs in log output)
- Scope all data access by tenant/user -- no cross-tenant access
- Use parameterized queries to prevent injection
- Validate and sanitize all file upload paths

## API Security
- Input validation on ALL API endpoints (request bodies, query params, path params)
- Rate limiting on auth endpoints (signup, login, password reset)
- CORS restricted to known frontend origins
- Webhook signature verification for all incoming webhooks
- Return generic error messages to clients (no stack traces, no internal details)

## Infrastructure Security
- Use least-privilege IAM roles for all services
- Enable audit logging for sensitive operations
- Keep dependencies updated (automated vulnerability scanning)
- No public access to databases or internal services
- Use TLS for all network communication
