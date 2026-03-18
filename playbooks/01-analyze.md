# Phase 1: Analyze

Using the repo profile from Phase 0, derive all configuration values needed to generate the harness. This phase transforms raw detection data into specific settings for each enforcement script.

## Step 1: Derive Import Boundary Rules

This is the most critical analysis. The output becomes the `RULES` dict in `check_imports.py`.

### For brownfield repos (has existing code):

1. For each module identified in the profile, scan its Python/TypeScript files for import statements.
2. Record which other modules each module imports from.
3. Build a dependency graph: `module_A → {module_B, module_C}`.
4. Verify the graph is a DAG (no circular dependencies). If cycles exist, note them as issues to fix.
5. Determine the intended layering. Common patterns:

   **Layered architecture** (most common):
   ```
   routers/controllers → services → db/repositories → models/schemas
   ```
   The rule: each layer may only import from layers below it.

   **Hexagonal/Clean architecture**:
   ```
   adapters → application/usecases → domain/entities
   ```

   **MVC**:
   ```
   controllers → models (via services if they exist)
   views → controllers
   ```

6. Construct the RULES dict. Example output:
   ```python
   RULES = {
       "routers": {"services", "models", "auth", "middleware"},
       "services": {"db", "models", "auth"},
       "db": {"models"},
       "models": set(),  # leaf layer
       "auth": {"db", "models"},
       "agent": {"services", "db"},
   }
   ```

### For greenfield repos:

Prescribe a standard layered architecture based on the detected framework:

| Framework | Prescribed Layers |
|-----------|------------------|
| FastAPI | routers → services → db → models |
| Express/NestJS | controllers → services → repositories → models |
| Django | views → services → models (Django ORM in models) |
| Go (Chi/Gin) | handlers → services → repositories → models |
| Laravel | Controllers → Services → Repositories → Models |

### For TypeScript/JavaScript:

The import checker uses regex-based scanning (not Python AST). The rules are the same format but applied to `import ... from` and `require()` statements. The agent should configure `check_imports.py` with the `source_root` pointing to the TypeScript source directory.

## Step 2: Derive Architecture Constants

These fill the configuration section of `check_architecture.py`:

| Constant | How to Derive |
|----------|---------------|
| `MAX_LINES` | Default 300. If the repo has many files over 300 lines already, start at 500 and note in the ratchet that it should decrease over time. |
| `DB_MODULE` | From profile: `db_module` (e.g., `"db"`, `"repositories"`) |
| `DB_IMPORT_PATTERNS` | From profile: `db_library` wrapped in a list (e.g., `["sqlalchemy"]`, `["prisma"]`) |
| `AI_ALLOWED_MODULES` | From profile: `ai_modules` as a set (e.g., `{"agent", "llm"}`) |
| `AI_IMPORT_PATTERNS` | From profile: `ai_libraries` (e.g., `["openai", "anthropic"]`) |
| `TESTABLE_MODULES` | All modules that contain business logic: services, db, agent. Exclude routers, models, config, utils. |
| `BACKEND` path | `Path(__file__).resolve().parent.parent / "{{source_root}}"` |

## Step 3: Derive Golden Principles Configuration

The golden principles checker needs to know the source root. The checks themselves are universal for Python:
- No `print()` in production code
- No hardcoded secrets
- Type hints on all public functions
- No bare `except:`

For non-Python primary languages, note which checks need alternative implementation:

| Language | print() equivalent | Secret scan | Type hints | Bare catch |
|----------|-------------------|-------------|------------|------------|
| Python | `print()` → `logger.info()` | Same regex patterns | Return type required | `except:` → `except SomeError:` |
| TypeScript | `console.log()` → `logger.info()` | Same regex patterns | Return type via tsc strict | `catch {}` → `catch (e: Error)` |
| Go | `fmt.Println()` → `slog.Info()` | Same regex patterns | N/A (typed language) | N/A (explicit error returns) |
| PHP | `echo`/`var_dump()` → `Log::info()` | Same regex patterns | Return type declarations | `catch (\Exception)` required |

## Step 4: Seed Feature List

From the discovered API endpoints and frontend pages, construct a starter `.harness/feature_list.json`:

### Functional features (from endpoints):

For each discovered endpoint, create an entry:
```json
{
  "id": "F001",
  "category": "functional",
  "priority": 1,
  "description": "{{METHOD}} {{PATH}} returns expected response",
  "steps": [
    "Send {{METHOD}} {{PATH}}",
    "Verify HTTP {{EXPECTED_STATUS}} response",
    "Verify response body contains expected fields"
  ],
  "passes": false,
  "verified_by": null,
  "verified_at": null
}
```

Always include the health endpoint as F001 (priority 1).

### UI features (from pages):

For each discovered frontend page:
```json
{
  "id": "F0XX",
  "category": "ui",
  "priority": N,
  "description": "{{PAGE}} renders with expected content",
  "steps": [
    "Navigate to {{PAGE}}",
    "Verify page contains expected elements",
    "Verify no console errors"
  ],
  "passes": false
}
```

### Standard features (always include):

- **Security**: Protected endpoints reject unauthenticated requests (if auth detected)
- **Reliability**: API returns structured error responses with correlation ID
- **Observability**: Application logs structured JSON to stdout

## Step 5: Derive Three-Tier Boundaries

Based on the detected stack, define what agents should Always/Ask/Never do:

### Always (do without asking):
- Run `scripts/validate.sh` before committing
- Fix lint and format errors
- Update AGENTS.md when adding modules or commands
- Write tests for new code
- Use structured logging (no print/console.log)
- Follow the module dependency rules

### Ask First (propose and wait):
- Adding new dependencies
- Changing public API contracts
- Modifying database schemas or migrations
- Changing authentication/authorization logic
- Modifying CI workflows
- Adding new top-level modules
- Changing infrastructure configuration

### Never (absolute prohibition):
- Delete existing tests
- Skip validate.sh or bypass pre-commit hooks
- Commit secrets, API keys, or credentials
- Push directly to main/master
- Disable linters or type checkers
- Put business logic in routers/controllers
- Import database libraries outside the data access layer
- Use `print()`/`console.log()` in production code

Customize based on what was detected — e.g., if the repo uses Django, add "Never: raw SQL outside migrations and managers."

## Step 6: Derive UI Legibility Pages

From the discovered frontend pages, build the PAGES array for `check_ui_legibility.sh`:

```bash
PAGES=("/" "/login" "/dashboard")
```

If no frontend was detected, this will be empty and the UI legibility gate will be skipped.

Also determine the HOME_KEYWORDS for the home page check based on the project type.

## Step 7: Identify Custom Requirements

**This is the step where you ASK the customer.** Before proceeding to generation, present your analysis and ask:

1. "I detected these module boundaries: [show rules]. Do these look correct? Any adjustments?"
2. "Do you have any custom golden rules beyond the standard set? For example:
   - Maximum function length
   - Required docstrings
   - Specific naming conventions
   - Domain-specific rules (e.g., 'all prices must use Decimal, never float')"
3. "Are there any modules that should be excluded from checks? (e.g., generated code, vendor code)"
4. "Do you want the observability stack (Victoria Logs + Metrics)? It requires Docker."

Record any custom requirements. These will be added as additional checks in Phase 2.

## Step 8: Quality Baseline Assessment

If the repo has existing code, do a quick assessment:

1. Count source files (excluding tests, __pycache__, node_modules, .venv)
2. Count test files
3. Estimate lint errors (if linter is available, run it and count)
4. Count TODO/FIXME/HACK comments
5. Identify god files (over 300 lines)
6. Compute test-to-source ratio

This informs:
- Initial ratchet baseline values
- Whether to start with strict or relaxed lint rules
- Whether MAX_LINES should be higher initially (if many large files exist)

## Output: Analysis Results

Add these derived values to the profile:

```yaml
# Import rules (for check_imports.py)
import_rules:
  routers: ["services", "models", "auth"]
  services: ["db", "models"]
  db: ["models"]
  models: []

# Architecture constants (for check_architecture.py)
max_lines: 300
db_module: "db"
db_import_patterns: ["sqlalchemy"]
ai_allowed_modules: ["agent"]
ai_import_patterns: ["openai"]
testable_modules: ["services", "db", "agent"]

# UI legibility
pages_to_check: ["/", "/login", "/dashboard"]
health_endpoint: "/health"

# Feature list seed
feature_count: 8
features: [...]  # The full seeded feature list

# Boundaries
boundaries_always: [...]
boundaries_ask: [...]
boundaries_never: [...]

# Custom requirements
custom_golden_rules: []
excluded_paths: []
want_observability: true

# Quality baseline
source_files: 42
test_files: 15
estimated_lint_errors: 23
todo_count: 7
god_files: 2
test_coverage_ratio: 0.36
```

Proceed to Phase 2 with the complete profile + analysis.
