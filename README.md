# CorePath knowledge infrastructure

Early implementation of CorePath's shared knowledge infrastructure for eleven specialist domains. This repository contains a Python/FastAPI API, PostgreSQL schema migrations and a static Intelligence Centre interface prototype.

The full product vision and requirements live in the separate [CorePath repository](https://github.com/jarrandixon67-stack/CorePath). This repository currently covers the knowledge foundation; it does not implement the full life-optimisation platform.

## Repository map

| Location | Contents |
|---|---|
| [backend/](backend/README.md) | API setup, configuration, endpoints and tests |
| [database/migrations/](database/migrations/) | Eight ordered PostgreSQL migrations |
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

The frontend uses illustrative data and does not save form submissions or call the API. Source ingestion, research scheduling, production authentication and deployment remain unfinished. The separate [specialist runtime](specialists/README.md) implements bounded library retrieval and draft research execution; it is not connected to the prototype. See [implementation status](docs/knowledge-infrastructure/implementation-status.md) for evidence and the next implementation sequence.

For ongoing development, start with the [build handover](docs/HANDOVER.md) and [deployment procedure](docs/knowledge-infrastructure/deployment.md).

The initial [private Founder workspace](https://corepath-founder.inquisitiveblade1.chatgpt.site) uses ChatGPT sign-in. It is a separate owner-private portal; it does not yet connect to this knowledge API or provision PostgreSQL roles. See its [access and maintenance notes](docs/FOUNDER-WORKSPACE.md).

## Life Profiling bot

The first [Life Profile service](life-profile/README.md) is implemented separately from the knowledge API, based on the founder's Life Profile working draft. It supports consented conversation analysis, encrypted proposed observations, owner review/correction/deletion and explicitly approved Personal AI context. Its [requirements](docs/life-profile/requirements.md) preserve the draft categories and distinguish observations from confirmed understanding.

This code does not make the bot operational in the Founder portal. A separate database, encryption key, trusted Personal AI identity gateway and configured model are required; no live personal data or model requests were used to test it.

## Eleven specialist bots

The [specialist network](specialists/README.md) implements eleven distinct discipline briefs, library-scoped research, quoted evidence, draft findings, signed service capabilities, database permissions and request limits. Coordinator dispatch and own-domain independent research are separate operations. Specialists record collaboration requests for Coordinator review and never contact peers directly. It has no Life Profile access or member-facing chat.

A model connection, trusted machine-identity gateway, approved extracted sources and deployment are still required. Synthetic tests and HTTP mocks do not establish live model quality.

## Coordinator bot

The [Coordinator service](coordinator/README.md) accepts signed general-research requests from the Personal AI, chooses a bounded specialist team, authorises eligible follow-ups and consolidates cited draft findings. It preserves specialist disagreements and gaps, caps confidence at supporting findings and reports partial failures. Its restricted database role cannot read libraries or Life Profiles directly.

The model, trusted gateways/exchange, Personal AI client and hosting still require configuration and live evaluation. Automated tests use synthetic evidence and model doubles; they do not certify reasoning quality.

## Persy — Personal AI

[Persy](persy/README.md) is the first member-facing Personal AI service. It supports optional encrypted conversation history, explicit communication preferences, optional approved profile context, reviewed research handoffs and owner-controlled Life Profile analysis/review/decisions. Private conversations use their own third database, outside knowledge and Life Profile storage.

Persy is not connected to the Founder preview site. Live model quality, trusted member sign-in/exchange, frontend consent/chat controls and deployment remain pending. Its [evaluation scenarios](persy/evaluation.md) describe further review without claiming it has occurred.

## Local development

Use Python 3.11 or newer. Follow the [backend setup](backend/README.md#local-setup) to create a virtual environment and install the API. PostgreSQL is optional for liveness checks and database-independent tests; the source-registry integration test requires a disposable database with all eight migrations applied.

Open [frontend/index.html](frontend/index.html) in a browser to explore the independent design prototype. No frontend build tools are required.

## Access boundary

The API currently uses a temporary shared internal bearer token. Keep credentials out of Git and browser JavaScript. The schema's role records do not yet enforce user or library permissions in the API. External access requires the identity, session and authorisation work described in the [architecture](docs/knowledge-infrastructure/architecture.md).

Repository commits and passing tests do not establish production deployment or readiness. Keep individual Life Profile data outside this knowledge repository.

## Render live-test deployment

See [the deployment instructions](deployment/README.md) and `render.yaml` for the initial Percy → Coordinator → eleven-specialist chain. The new `service_gateway` package implements the limited research/dispatch token exchange required by those existing services. It does not enable profile access or deploy resources automatically. Hosting approval, restricted database provisioning, secret configuration, model access and live evaluation are still required.

## Business partner assessment and invitations

The [partner bot](partners/README.md) provides bounded candidate discovery, evidence review, country/sector qualification, a durable invitation queue and a disabled-by-default email worker. Australia and health/wellbeing are the founder-selected first trial. See the [approved baseline and proposed health standard](docs/partners/AU-HEALTH-STANDARD.md). This code has not started a real recruitment campaign.

## Independent feedback oversight

The [Feedback Bot](feedback/README.md) collects positive/negative CorePath and partner feedback, examines authorised review evidence and raises source-linked signals for human review. It uses separate encrypted storage and optional AI consent, and cannot change business ratings or access Life Profiles. This service is not deployed; no live review feed or customer feedback collection is enabled.


## Agreed bot foundation (review build)

The isolated [replacement bot foundation](bot-foundation/README.md) records the founder-agreed roles and implements an all-eleven discussion, routed peer review, coordinator feedback, Persy presentation, consent-controlled profile prototypes, public locations, partner limits and founder-controlled 12. It includes deterministic planning tools and reviewed-draft builders. It does not replace or deploy the existing services automatically. See its [handover](bot-foundation/HANDOVER.md), [integration plan](bot-foundation/INTEGRATION.md) and [executed checks](bot-foundation/TEST_RESULTS.md).
