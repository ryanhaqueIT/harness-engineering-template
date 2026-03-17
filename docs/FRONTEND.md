# Frontend Conventions

> For agents building the frontend application.

## Stack

- {{FRONTEND_FRAMEWORK}} with {{FRONTEND_ROUTER}}
- TypeScript strict mode
- {{CSS_FRAMEWORK}}
- {{PRIMARY_FONT}} font

## File Structure

```
frontend/
  {{FRONTEND_STRUCTURE}}
```

## Conventions

- **Routing**: one page file per route. Define small helper components inline in the page file.
- **Server vs Client**: prefer server-side rendering by default. Only opt into client-side rendering when the page needs interactive state (forms, event handlers).
- **Data fetching**: server components call API functions directly. No useEffect for initial data loads.
- **API client**: all backend calls go through a single API client module. Two patterns:
  - `fetchApi<T>(path)` -- throws on HTTP error
  - `fetchApiSafe<T>(path, fallback)` -- returns fallback on any error (demo mode)
- **Styling**: use the project's CSS framework. See `docs/DESIGN.md` for the color palette and component patterns.
- **Naming**: PascalCase for components, camelCase for functions.
- **Error handling**: show user-friendly error states. Never show raw error messages or stack traces.

## Routes

| Path | Component | Type | Purpose |
|------|-----------|------|---------|
| `/` | `page.tsx` | {{DEFAULT_RENDER_TYPE}} | {{HOME_PAGE_DESC}} |
| {{ROUTE_2}} | {{ROUTE_2_FILE}} | {{ROUTE_2_TYPE}} | {{ROUTE_2_DESC}} |
| {{ROUTE_3}} | {{ROUTE_3_FILE}} | {{ROUTE_3_TYPE}} | {{ROUTE_3_DESC}} |

## API Functions

| Function | Method | Endpoint | Fallback |
|----------|--------|----------|----------|
| `list{{ENTITY}}s()` | GET | `/api/{{ENTITY_PLURAL}}` | MOCK_DATA |
| `get{{ENTITY}}(id)` | GET | `/api/{{ENTITY_PLURAL}}/:id` | MOCK_DATA lookup |
| `create{{ENTITY}}(payload)` | POST | `/api/{{ENTITY_PLURAL}}` | throws |
| `update{{ENTITY}}(id, data)` | PUT | `/api/{{ENTITY_PLURAL}}/:id` | throws |
| `delete{{ENTITY}}(id)` | DELETE | `/api/{{ENTITY_PLURAL}}/:id` | throws |

## Testing

- Use {{FRONTEND_TEST_FRAMEWORK}} for component tests
- Test user interactions, not implementation details
- Mock API calls, not internal component state
- Every page should have at least one smoke test that verifies it renders without errors
