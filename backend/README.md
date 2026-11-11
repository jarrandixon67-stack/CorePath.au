# CorePath Knowledge API

FastAPI foundation for shared specialist knowledge infrastructure. Source registration stores metadata; it does not download or ingest a book, paper or web page.

## Requirements

- Python 3.11 or newer.
- PostgreSQL for database-backed routes and integration tests. CI uses PostgreSQL 16.
- The PostgreSQL `psql` client is optional for database inspection.
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

Export `DATABASE_URL` into the shell first; the migration command does not load the API's `.env` file automatically. From this `backend/` directory, apply to a fresh disposable database:

```bash
python -m app.migrations
python -m app.migrations --check
```

Repeat application skips recorded files. The runner records filenames, versions and SHA-256 checksums in `schema_migrations`, validates existing history before applying anything, and applies the pending batch plus its history in one transaction. A failure rolls back the batch. Migration runners coordinate with a PostgreSQL advisory lock.

`--check` is read-only: exit code 0 means up to date, 1 means valid pending migrations and 2 means an error. Applying migrations returns 0 on success and 2 on error. Use `--directory /path/to/release/migrations` when SQL files are stored outside the default checkout layout.

The original six migration files remain unchanged; versions 007–008 extend the release:

| Version | Purpose |
|---|---|
| 001 | Initial knowledge schema and specialist seeds |
| 002 | Source-library associations |
| 003 | Categories and source verification |
| 004 | Human/AI principals and role assignments |
| 005 | Executive Administrator role |
| 006 | Delegated administrator action grants |
| 007 | Specialist run records, execution leases and English section-search index |
| 008 | Coordinator runs/tasks, internal Personal AI service role and coordinate grant |

Migrations are explicitly run, not executed during API startup. If an existing database was set up by running SQL directly, the runner refuses to automatically baseline it. Do not drop data or fabricate history to get past that check; use a reviewed adoption plan. Applied files must never be edited. See the [deployment procedure](../docs/knowledge-infrastructure/deployment.md) for release, backup, recovery and existing-database handling.

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

Database-dependent tests skip when `DATABASE_URL` is absent from the process environment. For the full suite, export a connection string to a fresh disposable test database, run the migration command above and run the same checks. Migration tests use individually generated schemas in that disposable database. The source-registry test writes records and assumes empty source tables; use a fresh database for each full run. Never point tests at production.

The [GitHub Actions workflow](../.github/workflows/knowledge-infrastructure-ci.yml) provisions PostgreSQL, applies migrations, validates seed data and runs the full suite and code checks.

## Separate specialist runtime

All eleven [specialists](../specialists/README.md) run in `specialists.main:app` on a separate port/process. Their signed Coordinator/specialist capabilities and database service grants do not upgrade this knowledge API's shared-token routes. Use a distinct least-privilege runtime database login. They retrieve only eligible prepared sections and save review-required drafts, with no profile access, member chat or peer execution.

## Coordinator service

The separate [Coordinator](../coordinator/README.md) runs as `coordinator.main:app` on port 8003, with its own signed Personal AI capabilities and restricted database account. It plans research, calls the specialist service through a trusted token-exchange contract and returns traceable draft reports. `python -m coordinator.evaluate` validates synthetic routing fixtures; only an explicitly configured `--live` run calls a model. Neither service upgrades the knowledge API's shared-token routes or provisions human identity.

## Current limitations

The knowledge API does not yet implement source ingestion, production identity and sessions, human endpoint-level role authorisation or production deployment. The separate specialist service provides initial scoped retrieval and draft execution; live model quality remains unverified. The [frontend](../frontend/README.md) remains a separate demonstration. See [implementation status](../docs/knowledge-infrastructure/implementation-status.md) for verified evidence and remaining work.
