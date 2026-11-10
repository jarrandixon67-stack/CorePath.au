# CorePath knowledge infrastructure

Early implementation of CorePath's shared knowledge infrastructure for eleven specialist domains. This repository contains a Python/FastAPI API, PostgreSQL schema migrations and a static Intelligence Centre interface prototype.

The full product vision and requirements live in the separate [CorePath repository](https://github.com/jarrandixon67-stack/CorePath). This repository currently covers the knowledge foundation; it does not implement the full life-optimisation platform.

## Repository map

| Location | Contents |
|---|---|
| [backend/](backend/README.md) | API setup, configuration, endpoints and tests |
| [database/migrations/](database/migrations/) | Six ordered PostgreSQL migrations |
| [frontend/](frontend/README.md) | Static, interactive design prototype |
| [docs/](docs/README.md) | Architecture, data model, decisions and implementation status |
| [CI workflow](.github/workflows/knowledge-infrastructure-ci.yml) | Migration, seed, test, lint and format checks |

## Current capabilities

- Database schema and seed records for eleven specialist libraries.
- Internal API routes for libraries, categories, source metadata and source verification.
- Source records shared between libraries without duplicating their metadata.
- Database identity, role and administrator action-grant records.
- A tested deny-by-default permissions engine; identity loading and endpoint-level enforcement remain pending.
- Liveness and database-readiness endpoints.
- Explicit database migration runner with history, checksum validation and transactional application.

The frontend uses illustrative data and does not save form submissions or call the API. Source ingestion, retrieval, research automation, production authentication and deployment remain unfinished. See [implementation status](docs/knowledge-infrastructure/implementation-status.md) for evidence and the next implementation sequence.

For ongoing development, start with the [build handover](docs/HANDOVER.md) and [deployment procedure](docs/knowledge-infrastructure/deployment.md).

The initial [private Founder workspace](https://corepath-founder.inquisitiveblade1.chatgpt.site) uses ChatGPT sign-in. It is a separate owner-private portal; it does not yet connect to this knowledge API or provision PostgreSQL roles. See its [access and maintenance notes](docs/FOUNDER-WORKSPACE.md).

## Local development

Use Python 3.11 or newer. Follow the [backend setup](backend/README.md#local-setup) to create a virtual environment and install the API. PostgreSQL is optional for liveness checks and database-independent tests; the source-registry integration test requires a disposable database with all six migrations applied.

Open [frontend/index.html](frontend/index.html) in a browser to explore the independent design prototype. No frontend build tools are required.

## Access boundary

The API currently uses a temporary shared internal bearer token. Keep credentials out of Git and browser JavaScript. The schema's role records do not yet enforce user or library permissions in the API. External access requires the identity, session and authorisation work described in the [architecture](docs/knowledge-infrastructure/architecture.md).

Repository commits and passing tests do not establish production deployment or readiness. Keep individual Life Profile data outside this knowledge repository.
