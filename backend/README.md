# CorePath Knowledge API

Initial backend scaffold for the shared specialist knowledge infrastructure.

## Requirements

- Python 3.11 or newer
- PostgreSQL is optional for liveness testing and required for readiness
- Docker is optional

## Local setup

From this directory:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

On Windows PowerShell, activate with:

```powershell
.venv\Scripts\Activate.ps1
```

The API exposes:

- `GET /health/live` — process liveness; does not require a database.
- `GET /health/ready` — dependency readiness; returns HTTP 503 until PostgreSQL is configured and reachable.
- `/docs` — interactive API documentation in development.

## Tests and lint

```bash
pytest
ruff check .
```

## Database migration

The initial SQL migration is in `../database/migrations/001_initial_knowledge_schema.sql`.

Review the migration and apply it to a disposable PostgreSQL database first. For example, using the PostgreSQL client:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f ../database/migrations/001_initial_knowledge_schema.sql
```

Do not apply this migration to production until it has been tested against the selected PostgreSQL version and hosting provider. The migration is not automatically executed by application startup.

## Configuration

Copy `.env.example` to `.env` and set a local `DATABASE_URL`. Never commit credentials. Production secrets must be supplied through the hosting platform's secret manager.

## Current limitations

This is an application foundation only. It does not yet implement source ingestion, research execution, retrieval, specialist authentication or production deployment. Those capabilities are separate subsequent milestones.


## Source registry API

Internal source-management routes require an HTTP bearer token configured as
`INTERNAL_API_TOKEN`. The current shared-token guard is an interim development
control, not the final per-bot identity and scoped-permission model.

- `GET /v1/libraries` — list the eleven specialist libraries.
- `GET /v1/libraries/{library_id}/sources` — list registered source metadata.
- `POST /v1/libraries/{library_id}/sources` — register source metadata.

The POST endpoint registers metadata only; it does not download or ingest a
book, paper or web page. Source ingestion and licence-aware processing are
separate subsequent capabilities.

Apply migrations in order to a disposable database:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f ../database/migrations/001_initial_knowledge_schema.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f ../database/migrations/002_source_library_registry.sql
```
