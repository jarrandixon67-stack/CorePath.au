# CorePath Knowledge API

FastAPI foundation for shared specialist knowledge infrastructure. Source registration stores metadata; it does not download or ingest a book, paper or web page.

## Requirements

- Python 3.11 or newer.
- PostgreSQL for database-backed routes and integration tests. CI uses PostgreSQL 16.
- The PostgreSQL `psql` client to apply migrations.
- Docker is optional.

## Local setup

Run from this `backend/` directory:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`.

To explore the API without a database, leave `DATABASE_URL` unset and run:

```bash
uvicorn app.main:app --reload
```

Liveness is available without PostgreSQL; readiness and database-backed routes return HTTP 503. A configured but unreachable database can prevent application startup while its connection pool waits.

For database-backed development, copy `.env.example` to `.env`, replace the example database credentials and internal token, apply all migrations below to a disposable local database, then start the API. Configuration loads `.env` from the working directory.

## Configuration

| Variable | Purpose |
|---|---|
| `APP_NAME` | API display name |
| `APP_ENV` | Environment label |
| `LOG_LEVEL` | Configured logging-level value |
| `DATABASE_URL` | PostgreSQL connection string; optional for database-independent checks |
| `INTERNAL_API_TOKEN` | Temporary bearer token for internal knowledge routes |
| `DB_POOL_MIN_SIZE` | Minimum pool size; defaults to 1 |
| `DB_POOL_MAX_SIZE` | Maximum pool size; defaults to 5 and must be at least the minimum |

Never commit `.env` or real credentials. Production secrets must be supplied through the hosting platform's secret manager. The shared token is an interim development control; production identities and action-level permissions remain unfinished. Never place the token in browser JavaScript.

## Database migrations

Apply migrations once, in filename order, to a new disposable database. Export `DATABASE_URL` into the shell first; `psql` does not load the API's `.env` file automatically.

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f ../database/migrations/001_initial_knowledge_schema.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f ../database/migrations/002_source_library_registry.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f ../database/migrations/003_library_categories_and_verification.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f ../database/migrations/004_identity_and_library_access.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f ../database/migrations/005_executive_administrator_role.sql
```

Migrations are not automatically run at application startup. Migration tracking and a production deployment procedure remain pending. Do not blindly rerun these scripts against an existing database or apply them to production before testing the selected PostgreSQL version and hosting service.

## API routes

| Method | Route | Purpose |
|---|---|---|
| GET | `/health/live` | Process liveness |
| GET | `/health/ready` | Database readiness |
| GET | `/docs` | Interactive API documentation |
| GET | `/v1/libraries` | List specialist libraries |
| GET | `/v1/libraries/{library_id}/sources` | List registered source metadata |
| POST | `/v1/libraries/{library_id}/sources` | Register source metadata and a library association |
| PUT | `/v1/libraries/{library_id}/sources/{source_id}` | Link an existing source to another library |
| GET | `/v1/libraries/{library_id}/overview` | Get source, verification and finding counts plus categories |
| POST | `/v1/libraries/{library_id}/categories` | Create a category in a library |
| PATCH | `/v1/libraries/{library_id}/sources/{source_id}/verification` | Update source verification status and record an audit event |

All `/v1/` routes require `Authorization: Bearer <INTERNAL_API_TOKEN>`. They currently share the same access level; database role records do not yet enforce caller-specific permissions.

## Tests and lint

With no database configured:

```bash
pytest
ruff check .
ruff format --check .
```

Database-dependent tests skip when `DATABASE_URL` is absent from the process environment. For the full suite, export a connection string to a fresh disposable test database, apply all five migrations and run the same commands. The source-registry test writes records and assumes empty source tables; use a fresh database for each full run. Never point tests at production.

The [GitHub Actions workflow](../.github/workflows/knowledge-infrastructure-ci.yml) provisions PostgreSQL, applies migrations, validates seed data and runs the full suite and code checks.

## Current limitations

The API does not yet implement source ingestion, retrieval, research execution, production identity and sessions, endpoint-level role authorisation or production deployment. The [frontend](../frontend/README.md) remains a separate demonstration. See [implementation status](../docs/knowledge-infrastructure/implementation-status.md) for verified evidence and remaining work.
