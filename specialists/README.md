# CorePath specialist network

The first runtime for all eleven established specialist domains. These are distinct instructions, library scopes and testable execution paths using a shared model adapter. They are not eleven newly trained models. A default model can serve them all, with optional per-specialist overrides.

The [expanded capability requirements](../docs/SPECIALIST-CAPABILITIES.md) define
Nutrition's physiology/nutrient/lab-interpretation target, Financial Capability's
Australian maths/law/markets/Centrelink target, concise practical guidance and
independent evaluation. These are development targets, not verified expertise.
`python -m specialists.tool_needs` prepares tool-consultation briefs without model
calls. Explicit `--live` consultations require configured models, credentials and
a new `--output` report; responses are proposed requirements, never permissions.

| Specialist | Domain slug |
|---|---|
| Personal Development | `personal-development` |
| Physical Development | `physical-development` |
| Nutrition | `nutrition` |
| Mental Wellbeing | `mental-wellbeing` |
| Relationships | `relationships` |
| Learning & Intelligence | `learning-intelligence` |
| Financial Capability | `financial-capability` |
| Career & Business | `career-business` |
| Practical Life Skills | `practical-life-skills` |
| Parenting & Family | `parenting-family` |
| Recreation & Discovery | `recreation-discovery` |

## Implemented behaviour

An authenticated Coordinator dispatches a general research question and search terms to one specialist. The runtime checks its active database identity, active library and both retrieval/research grants. An independently authenticated specialist can run research only in its own discipline. Human roles and the Personal AI cannot call these endpoints as an alternate Coordinator.

Retrieval uses PostgreSQL English full-text search over the assigned library's prepared sections. Sources must be active and verified, documents must have completed extraction, and each document must explicitly have `document_metadata.model_use_allowed` set to JSON `true` after rights/privacy review. Both the document's library and source-library association must match. Registering source metadata alone does not provide searchable evidence or authorise sending text to a model. Documents must contain general, licensed knowledge, never private profiles, conversations or journals.

The model receives up to six excerpts, each limited to 2,000 characters, plus bounded metadata. Results include proposed findings with exact quoted sections, source provenance, confidence, limitations, practical options, contradictions, knowledge gaps and requests for collaboration. Unknown sections, fabricated quotations and inconsistent references are rejected. Source metadata comes from PostgreSQL, not model-invented URLs. No matching evidence means a recorded gap without a model call.

**Quotation matching establishes traceability, not truth or entailment.** A real quote can still be misinterpreted. Confidence is an uncalibrated model judgement; source verification does not prove every claim. All findings remain drafts requiring evidence review. No accepted finding is published, source verified, Life Profile accessed, peer bot contacted, transaction executed or member messaged by this service. The Personal AI remains the only member-facing AI.

Every run has a policy hash, question hash, request ID, model ID, state and audit events for starts/completions/failures. No separate raw question/body is persisted; generated output can repeat input, so general questions are still required. Signed capabilities are single-use for starting a run. Quotas are enforced transactionally per requesting service across processes: 20 starts per rolling 24 hours and two concurrent runs by default, including failed and evidence-empty attempts. A two-minute execution lease recovers abandoned runs when the next start is attempted. These are operational limits, not a global currency budget. Configure organisation/provider spend limits as well.

Permissions and the retrieved evidence are rechecked before saving results. Revocation, withdrawn sources, changed excerpts or expired leases prevent completion. Stored results retain their historical citation provenance; they are not retroactively refreshed when a source later changes.

## Local setup

Install the existing backend and development dependencies from `backend/`:

```bash
pip install -e ".[dev]"
python -m specialists.registry
```

Use a disposable knowledge database first. Apply migrations through the existing tracked runner using the migration/owner credential, then use a different runtime credential:

```bash
python -m app.migrations
python -m app.migrations --check
uvicorn specialists.main:app --host 127.0.0.1 --port 8002
```

The runner reads `DATABASE_URL`; the specialist service reads only `SPECIALISTS_DATABASE_URL`. It does not fall back to the Life Profile or knowledge API configuration. See [.env.example](.env.example). Configuration loads `.env` in the working directory, so copy the required variables into `backend/.env` or export them. Never commit that file.

Before accepting work, an operator must:

1. Provision the knowledge database, apply migrations 001–008, and configure backups/restore.
2. Apply/adapt [runtime-role.sql](database/runtime-role.sql) with an administrative database account. Use a dedicated non-superuser login belonging to that restricted role. Check existing/public grants and database-connect privileges; this additive template does not revoke pre-existing rights. The runtime must have no credentials or connection authority for the separate Life Profile database. Never use the migration owner as runtime login.
3. Set the gateway's **public** Ed25519 verification key and issuer/audience. Keep the private signing key only in the trusted service gateway. That gateway, its deployment and machine identity issuance are separate work; this service does not mint credentials or accept the temporary shared knowledge token.
4. Map gateway subjects to reviewed `service_identities.service_key` records. A Coordinator uses database role `coordinator`; each specialist uses role `specialist` with its actual domain UUID. Grant the required `research` and `retrieve` actions through `access_permissions`, normally scoped to the relevant library. A specialist's domain restriction still applies even if an operator accidentally issues a global grant. These original internal service grants are separate from the human principal/action tables; no user-role loader is implied.
5. Activate reviewed libraries (the seeded state is `planned`) and ingest/review permitted sections. Source verification and model-use approval remain separately authorised operator work; the specialists cannot grant themselves either.
6. Configure `SPECIALISTS_OPENAI_API_KEY`, an evaluated `SPECIALISTS_MODEL`, provider spend/retention settings and deployment controls. No provider key or model is bundled. The adapter uses OpenAI Responses API with `store: false`, no model tools, a strict output schema and no retries. This flag does not establish provider-wide zero retention; confirm applicable account controls before sending approved content.

## Service API

| Route | Required actor / scope / purpose |
|---|---|
| `GET /health/live` | Public process liveness only |
| `GET /v1/specialists` | `coordinator_ai` / `specialist:catalogue` / `catalogue`, domain `*` |
| `POST /v1/specialists/{domain}/tasks` | `coordinator_ai` / `specialist:dispatch` / `dispatch` |
| `GET /v1/specialists/{domain}/tasks/{run_id}` | `coordinator_ai` / `specialist:read` / `task_status` |
| `POST /v1/specialists/{domain}/research` | `specialist_ai` / `specialist:research` / `independent_research` |
| `GET /v1/specialists/{domain}/research/{run_id}` | `specialist_ai` / `specialist:read` / `research_status` |

For all domain routes the signed `domain` claim must equal the path slug. Tokens require `sub`, `actor`, `domain`, `scope` (a list), `purpose`, `iss`, `aud`, integer `iat`/`nbf`/`exp`, and a unique `jti` no longer than 100 characters. Maximum lifetime is five minutes. Only EdDSA signatures are accepted. A gateway signs a fresh capability for each operation; result reads are restricted to the original requesting service. The Coordinator cannot read another service's independent run through these endpoints; an approved handoff workflow remains future work. Request IDs are not user identifiers.

Example task body, using a freshly signed service capability in the Authorization header:

```json
{
  "question": "What does our reviewed library say about gradual habit formation?",
  "search_terms": ["habit", "gradual change"],
  "max_sources": 4
}
```

Do not send personal Life Profile context. Free-text questions cannot technically be guaranteed free of personal details, so trusted callers must minimise input, and request-body logging must remain disabled in infrastructure. The model receives the question and approved excerpts. The API accepts no profile/user field and has no profile credentials or access route.

Run states are `running`, `completed`, `needs_evidence`, `failed`; `completed` means validated draft output, not scientific acceptance. Missing configuration fails closed. The catalogue distinguishes library state and configured model connection from live model quality, which remains unverified. `/health/live` proves only that the process responds.

## Validation and remaining work

Run `pytest`, `ruff check .` and `ruff format --check .` from `backend/`. PostgreSQL tests need a fresh disposable migrated knowledge database and a separate migrated profile test database for the existing full suite. Specialist tests use generated schemas and synthetic evidence. They exercise every domain, isolation, revocation, source changes, replay, quotas, concurrent starts, citation validation and model failure. Provider tests use HTTP mocks; they do not assess real model quality.

The separate [Coordinator service](../coordinator/README.md) now implements bounded dispatch and one explicitly reviewed round of requested peer follow-ups. It uses these existing task endpoints; specialists still cannot contact peers directly. Live gateway/model/deployment integration remains pending.

Still required: real model evaluations per discipline (including misleading sources and prompt injection), trusted gateway/Coordinator/Personal AI integration, hosting, licensed ingestion/extraction, multilingual and semantic retrieval, human evidence review/versioning, research scheduling, global spend controls and handoffs for independently recorded research. A specialist cannot execute a peer request itself; the separate Coordinator can review and authorise bounded follow-ups. No web crawler, live news monitoring or autonomous background loop is implemented. No production deployment or live specialist quality is claimed by these tests.
