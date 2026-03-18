# Phase 0: Discover

Scan the target repository and build a structured profile. This profile is the shared context for all subsequent phases. Be thorough — everything you miss here becomes a misconfiguration in Phase 2.

## Step 1: Determine Brownfield vs Greenfield

Scan the target repo root and one level of subdirectories for source files. Exclude config files, dotfiles, LICENSE, README, lock files, and generated directories (node_modules, .venv, dist, build, target, __pycache__).

- **5+ source files** → Brownfield. Map existing code.
- **<5 source files** → Greenfield. Ask the user:
  1. What are you building? (API, web app, CLI, library, monorepo)
  2. What language and framework?
  3. What CI provider?
  4. Any architectural preferences or constraints?

## Step 2: Detect Languages and Frameworks

Scan for these signals. Run ALL applicable checks — a repo may have multiple languages.

| Signal | Detection Method |
|--------|------------------|
| **Python** | `requirements.txt`, `pyproject.toml`, `setup.py`, `Pipfile`, `*.py` files |
| **TypeScript/JavaScript** | `package.json`, `tsconfig.json`, `*.ts`, `*.tsx`, `*.js`, `*.jsx` files |
| **Go** | `go.mod`, `go.sum`, `*.go` files |
| **Rust** | `Cargo.toml`, `*.rs` files |
| **PHP** | `composer.json`, `*.php` files |
| **Java/Kotlin** | `pom.xml`, `build.gradle`, `*.java`, `*.kt` files |

For framework detection:

| Framework | Detection |
|-----------|-----------|
| FastAPI | `from fastapi` in imports, `uvicorn` in dependencies |
| Django | `manage.py`, `django` in dependencies |
| Flask | `from flask` in imports |
| Express | `express` in package.json dependencies |
| NestJS | `@nestjs/core` in package.json dependencies |
| Next.js | `next.config.js`, `next.config.ts`, `next.config.mjs` |
| Vite/React | `vite.config.ts`, `react` in dependencies |
| Vue/Nuxt | `nuxt.config.ts`, `vue` in dependencies |
| Angular | `angular.json` |
| Laravel | `artisan` file, `laravel/framework` in composer.json |
| Rails | `Gemfile` with `rails`, `config/routes.rb` |
| Gin/Chi | `github.com/gin-gonic/gin` or `github.com/go-chi/chi` in go.mod |

## Step 3: Detect Toolchain

| Tool | Detection |
|------|-----------|
| **Package manager** | `package-lock.json` (npm), `yarn.lock` (yarn), `pnpm-lock.yaml` (pnpm), `poetry.lock` (poetry), `Pipfile.lock` (pipenv) |
| **Build system** | `Makefile`, `build.gradle`, `CMakeLists.txt`, `Taskfile.yml`, `justfile`, npm scripts |
| **Test framework** | `pytest.ini`, `jest.config.*`, `vitest.config.*`, `.mocharc.*`, `phpunit.xml`, test directories |
| **Linter** | `.eslintrc.*`, `ruff.toml`, `pyproject.toml [tool.ruff]`, `.golangci.yml`, `phpstan.neon`, `biome.json` |
| **Formatter** | `.prettierrc.*`, `ruff` format config, `.editorconfig` |
| **Type checker** | `tsconfig.json` (tsc), `mypy.ini`, `pyrightconfig.json` |
| **CI provider** | `.github/workflows/` (GitHub Actions), `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci/`, `bitbucket-pipelines.yml` |

Record the exact commands:
- `build_cmd`: e.g., `npm run build`, `go build ./...`, `python -m build`
- `test_cmd`: e.g., `pytest tests/`, `npm test`, `go test ./...`
- `lint_cmd`: e.g., `ruff check .`, `npx eslint .`, `golangci-lint run`
- `format_cmd`: e.g., `ruff format .`, `npx prettier --write .`, `gofmt -w .`
- `type_check_cmd`: e.g., `npx tsc --noEmit`, `pyright`, `mypy .`

## Step 4: Map Module Structure

Identify top-level modules in the backend/source directory. Look for these common patterns:

| Directory Name | Likely Responsibility |
|---------------|----------------------|
| `routers/`, `routes/`, `controllers/`, `handlers/`, `api/` | HTTP request handling |
| `services/`, `domain/`, `usecases/`, `core/`, `business/` | Business logic |
| `db/`, `repositories/`, `dal/`, `store/`, `data/` | Data access |
| `models/`, `schemas/`, `types/`, `entities/` | Data structures |
| `auth/`, `security/` | Authentication/authorization |
| `agent/`, `llm/`, `ai/` | AI/ML integration |
| `config/`, `settings/` | Configuration |
| `middleware/` | Request middleware |
| `utils/`, `helpers/`, `lib/`, `common/` | Shared utilities |
| `migrations/` | Database migrations |

Record each module with its path and responsibility.

## Step 5: Detect Database and AI Libraries

Scan import statements across ALL source files (not just the root):

**Database libraries** (record which module contains the imports):
- Python: `sqlalchemy`, `pymongo`, `motor`, `psycopg2`, `asyncpg`, `google.cloud.firestore`, `boto3.dynamodb`, `prisma`, `tortoise`, `peewee`, `django.db`
- TypeScript: `prisma`, `typeorm`, `sequelize`, `mongoose`, `knex`, `drizzle`
- Go: `database/sql`, `gorm.io`, `go.mongodb.org`, `github.com/jackc/pgx`

**AI/ML libraries** (record which modules import them):
- `openai`, `anthropic`, `google.genai`, `langchain`, `llama_index`, `transformers`, `torch`, `tensorflow`

Record:
- `db_module`: the directory that contains DB imports (e.g., `"db"`, `"repositories"`)
- `db_library`: the library name (e.g., `"sqlalchemy"`)
- `ai_modules`: list of directories that import AI libraries
- `ai_libraries`: list of AI library names found

## Step 6: Detect Config Module

Look for:
- Files named `config.py`, `settings.py`, `config.ts`, `env.ts` in the source root
- Usage of `os.environ`, `os.getenv` (Python) or `process.env` (Node) outside config files

Record:
- `config_module`: the file/directory that centralizes config (e.g., `"config"`, `"settings"`)
- `has_env_leakage`: true if `os.environ`/`process.env` is used outside config files

## Step 7: Discover API Endpoints

Scan for route decorators/registrations to seed the feature list:

| Framework | Pattern |
|-----------|---------|
| FastAPI | `@router.get("/path")`, `@app.post("/path")`, `@router.put`, `@router.delete` |
| Flask | `@app.route("/path")`, `@blueprint.route` |
| Django | `urlpatterns` entries, `path("route", view)` |
| Express | `router.get("/path")`, `app.post("/path")`, `Router().get` |
| NestJS | `@Get("/path")`, `@Post("/path")`, `@Controller("/prefix")` |
| Go (Chi/Gin) | `r.Get("/path")`, `r.Post("/path")`, `router.GET`, `router.POST` |

Record each endpoint: method, path, handler function name.

Also detect the health endpoint specifically: look for `/health`, `/healthz`, `/api/health`, `/_health`.

## Step 8: Discover Frontend Pages

For frontend apps, detect routable pages:

| Framework | Detection |
|-----------|-----------|
| Next.js (app router) | Files in `app/*/page.tsx` |
| Next.js (pages router) | Files in `pages/*.tsx` |
| React Router | `<Route path="/..."` in source, `createBrowserRouter` entries |
| Vue Router | `routes` array in `router/index.ts` |
| Angular | `Routes` in `app-routing.module.ts` |

Record the list of pages for UI legibility checks (e.g., `["/", "/login", "/dashboard", "/settings"]`).

## Step 9: Detect Existing Harness

Check if the target repo already has harness artifacts:

| Artifact | Check |
|----------|-------|
| validate.sh | `scripts/validate.sh` exists |
| Import checker | `scripts/check_imports.py` exists |
| Golden principles | `scripts/check_golden_principles.py` exists |
| Architecture checker | `scripts/check_architecture.py` exists |
| Feature list | `.harness/feature_list.json` exists |
| Ratchet baseline | `.harness/baseline.json` exists |
| AGENTS.md | `AGENTS.md` exists |
| CLAUDE.md | `CLAUDE.md` exists |
| Claude Code dir | `.claude/` directory exists |
| Observability | `docker-compose.observability.yml` exists |

Record `has_harness: true` if validate.sh exists. This triggers idempotent merge behavior in Phase 2.

## Step 10: Detect Deployment and Infrastructure

| Signal | Detection |
|--------|-----------|
| Docker | `Dockerfile`, `docker-compose.yml`, `docker-compose.yaml` |
| Terraform | `terraform/main.tf`, `infrastructure/main.tf`, `*.tf` files |
| Pulumi | `pulumi/Pulumi.yaml` |
| AWS | `cdk.json`, `serverless.yml`, `sam.template.yaml` |
| GCP | `app.yaml`, `cloudbuild.yaml` |
| Vercel | `vercel.json` |
| Kubernetes | `k8s/`, `kubernetes/`, `*.yaml` with `kind: Deployment` |

## Output: Repo Profile

Assemble all findings into a structured profile. This is carried forward to Phase 1.

```yaml
project_name: ""
greenfield: false
has_existing_code: true
has_harness: false

# Stack
languages: []
primary_language: ""
framework: ""
frontend_framework: ""

# Toolchain
package_manager: ""
build_cmd: ""
test_cmd: ""
lint_cmd: ""
format_cmd: ""
type_check_cmd: ""
test_framework: ""
ci_provider: ""

# Structure
source_root: ""          # "backend", "src", "app", "."
frontend_root: ""        # "frontend", "client", "web", ""
infra_root: ""           # "terraform", "infrastructure", ""
modules: []              # [{name, path, responsibility}]

# Architecture
db_module: ""
db_library: ""
ai_modules: []
ai_libraries: []
config_module: ""
has_env_leakage: false

# Discovered content
api_endpoints: []        # [{method, path, handler}]
health_endpoint: ""      # "/health"
frontend_pages: []       # ["/", "/login", "/dashboard"]

# Deployment
has_docker: false
infra_tool: ""
cloud_provider: ""

# Existing harness
existing_artifacts: []   # ["AGENTS.md", ".claude/"]

# Quality baseline (filled in Phase 1)
estimated_lint_errors: 0
estimated_test_count: 0
estimated_source_files: 0
```

Proceed to Phase 1 with this profile.
