# CorePath Life Profiling bot

First implementation based on the founder's Life Profile working draft. It learns through purpose-limited conversation analysis, creates reviewable observations and exposes only owner-approved context to the Personal AI.

This is a separate service and database from the shared knowledge infrastructure. The existing knowledge API continues to run as `app.main:app`; the profile service runs as `life_profile.main:app`. The journal extension stores encrypted owner entries and accepts only currently included, consented entries for reviewable profiling.

## Configuration

Install the backend package with `pip install -e ".[dev]"` from `backend/`. Supply these values through the deployment environment or an untracked local `.env`:

| Setting | Purpose |
|---|---|
| `LIFE_PROFILE_DATABASE_URL` | A separate profile PostgreSQL database; never the knowledge database |
| `LIFE_PROFILE_ENCRYPTION_KEY` | Fernet key managed separately from the database |
| `LIFE_PROFILE_GATEWAY_PUBLIC_KEY` | PEM Ed25519 public key of the trusted Personal AI gateway |
| `LIFE_PROFILE_GATEWAY_ISSUER` | Expected issuer; defaults to `corepath-personal-ai` |
| `LIFE_PROFILE_GATEWAY_AUDIENCE` | Expected audience; defaults to `corepath-life-profile` |
| `LIFE_PROFILE_MODEL` | Approved model identifier |
| `LIFE_PROFILE_OPENAI_API_KEY` | Server-side model provider secret |
| `LIFE_PROFILE_MODEL_TIMEOUT_SECONDS` | Model request timeout, default 30 seconds, maximum 60 |

No secrets or real profile data belong in Git, browser JavaScript or chat. The gateway private signing key must not be deployed to this service. Missing identity verification, encryption, database or model configuration fails closed rather than enabling a demo identity or fabricated bot response.

## Database and local startup

From `backend/`, export the profile database URL into the migration command's `DATABASE_URL`. The migration runner reads the shell environment, not `.env`:

```bash
DATABASE_URL="$LIFE_PROFILE_DATABASE_URL" python -m app.migrations --directory ../life-profile/database/migrations
DATABASE_URL="$LIFE_PROFILE_DATABASE_URL" python -m app.migrations --directory ../life-profile/database/migrations --check
uvicorn life_profile.main:app --host 127.0.0.1 --port 8001
```

The separate profile migrations are 001 (profile foundation) and 002 (journal) in their own database/history. They are not knowledge-database migrations. The profile service also rejects a database containing the knowledge library tables at startup. Deploy under separate database credentials and network/access controls; these local checks are not a substitute for infrastructure isolation.

The current knowledge Docker image is unchanged and is not a packaged profile deployment. The profile service currently runs from the installed release checkout as above; dedicated production packaging remains future work.

## Authenticated service contract

Every protected request needs a signed JWT with algorithm `EdDSA` using the configured Ed25519 key. Required claims: `sub` (stable opaque individual ID), `iss`, `aud`, `iat`, `nbf`, `exp`, `actor`, `purpose`, `scope` (list), and `jti`. Maximum lifetime is five minutes. `actor` must be `personal_ai`.

The trusted Personal AI gateway is responsible for authenticating the actual individual, deriving `sub` from that identity, verifying explicit consent/review/control actions, and issuing only the necessary scope/purpose. Neither browser-supplied identity headers nor the knowledge API's shared token establish profile access. This gateway is not implemented by this change, so the service must remain private/unavailable until it is integrated.

| Method and path | Required scope | Purpose |
|---|---|---|
| PUT `/v1/life-profile/consent` | `profile:consent` | `owner_control` |
| POST `/v1/life-profile/analyse` | `profile:analyse` | `profile_analysis` |
| GET `/v1/life-profile/review` | `profile:review` | `owner_review` |
| POST `/v1/life-profile/items/{id}/decision` | `profile:decide` | `owner_control` |
| GET `/v1/life-profile/context` | `profile:context` | `personalisation` |
| DELETE `/v1/life-profile/items/{id}` | `profile:delete` | `owner_control` |
| DELETE `/v1/life-profile` | `profile:delete` | `owner_control` |
| GET `/v1/life-profile/journal/settings` | `profile:journal_read` | `owner_review` |
| PUT `/v1/life-profile/journal/settings` | `profile:journal_write` | `owner_control` |
| GET `/v1/life-profile/journal/entries` | `profile:journal_read` | `owner_review` |
| GET `/v1/life-profile/journal/entries/{id}` | `profile:journal_read` | `owner_review` |
| POST `/v1/life-profile/journal/entries` | `profile:journal_write` | `owner_control` |
| PUT `/v1/life-profile/journal/entries/{id}` | `profile:journal_write` | `owner_control` |
| DELETE `/v1/life-profile/journal/entries/{id}?expected_version=N` | `profile:journal_delete` | `owner_control` |
| POST `/v1/life-profile/journal/entries/{id}/analyse` | `profile:journal_analyse` | `profile_analysis` |

The individual ID always comes from the verified token, never a request body or a profile selector. All responses are `no-store`. Public API schema/docs endpoints are disabled; the unauthenticated liveness endpoint reveals only process status.

Journal creation requires a UUID `client_reference`, `content` (1–4,000 characters), `entry_date`, and `disclosure_version:1`; `title` is optional. `include_in_profile` overrides the owner's default when supplied. Original journal whitespace is preserved. Updating also requires `expected_version`; preferences require `expected_version` (0 initially), `default_include_in_profile` and `disclosure_version:1`. A list returns at most 50 encrypted-at-rest entry summaries and an owner-bound `next_cursor` for `?before=UUID`. It does not return every full entry body.

Saving an included entry attempts analysis only when the existing profile purpose/category/external-processing consent allows it. Missing consent or model availability leaves a saved entry marked accordingly. Excluded entries never reach the model. All resulting understanding remains pending and unshared. The journal-specific website bridge must have its own managed signing key, matching public verification key, fixed HTTPS service origin and verified initial owner binding. It implements journal controls, not the broader conversation/service capability exchange. See the journal requirements for exclusion, race, provenance and deployment boundaries.

## First analysis

The following is a **synthetic request shape**, not a person record or an automatic onboarding questionnaire:

```json
{
  "purpose": "Adapt communication",
  "messages": [{
    "message_id": "synthetic-message-1",
    "conversation_id": "synthetic-conversation-1",
    "source_type": "conversation",
    "speaker": "user",
    "content": "I prefer short answers."
  }]
}
```

The purpose must match the current consent's purpose. Consent starts with analysis, external processing, personalisation and sensitive observations disabled. Categories must be explicitly selected for analysis. The gateway must explain external processing of the selected messages, which themselves may contain sensitive information; the sensitive-observation toggle is an additional storage/sharing control, not a redaction system.

Model output creates pending proposals with exact message evidence. Owner-authorised decisions accept, reject or correct an item using its current `expected_version`. Sharing defaults to false. Accepted items enter the Personal AI's context only with explicit item sharing and current personalisation/category/sensitivity consent. Revocation blocks further analysis and sharing; owner review/deletion remains available.

## Tests

Run `pytest`, `ruff check .` and `ruff format --check .` from `backend/`. New unit/HTTP tests use synthetic inputs, ephemeral signing keys and mocked model responses; they never call a live model.

For database tests, provision a separate disposable database with a name ending in `_test`, apply its profile migration and export `LIFE_PROFILE_DATABASE_URL`. Knowledge tests continue to use `DATABASE_URL` and their six existing migrations. CI provisions and tests both databases independently.

See the [requirements and boundaries](../docs/life-profile/requirements.md) for draft versus established requirements and remaining live-model, retention, gateway, UI and operational work.
