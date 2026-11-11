# Persy — CorePath's Personal AI

Persy is the member-facing AI: listen, explain clearly, ask useful questions and help turn understanding into achievable action. The first service provides private conversations, explicit communication preferences, optional approved Life Profile context, reviewed research handoffs and owner-controlled profile workflows.

The default style is plain, warm and practical, with at most one follow-up question and three possible next steps. Members can explicitly choose plain, balanced or detailed replies. Persy does not infer intelligence, personality or psychological traits from writing or timing, claim human feelings, encourage emotional dependency or prioritise engagement. Significant guidance needs evidence and visible uncertainty; health, financial and other high-risk matters have limits. Policy instructions guide a model; they are not proof of live model quality.

## Privacy and continuity

Persy has a separate private PostgreSQL database and its own encryption key. It receives no knowledge/profile database credential or signing private key. Startup rejects a database containing the public knowledge or Life Profile tables. All service URLs are fixed trusted HTTPS settings, not model-selected destinations, and redirects are disabled.

Nothing calls a model until the member records `model_processing_enabled: true`. Retained history and profile context are independently opt-in; both default to false. The member may change these choices using optimistic privacy revisions. Chats receive the current member message, a bounded window of their own retained conversation and, only when both the setting and per-turn selection permit it, approved profile context. History is not a permanent model memory and older turns outside the window are not included.

Retained message/reply payloads and pending research questions are encrypted with Fernet. Encrypted envelopes bind the owner hash, record ID and purpose, preventing a swapped ciphertext from being presented as another record. The key and ciphertext must be managed separately; lost keys cannot be recovered by this code. Raw questions/message hashes, profile snapshots, member assertions and tokens are not written to operational/audit records. Owner lookup uses a SHA-256 hash of the gateway's opaque member subject; do not use names or email addresses as subjects.

Profile-assisted turns carry an encrypted snapshot fingerprint. They remain reviewable by their owner, but are excluded from future model context when profile use is off or approved context has changed. The profile service is queried again before accepting a profile-assisted reply. Profile data can still appear in generated conversation text the owner chose to retain; there is no claim that a model never repeats input.

Disabling retained history erases existing chat/research payloads in this store. Privacy changes invalidate pending research proposals. Deleting a conversation removes its retained text and proposals and prevents an in-flight reply from recreating it. Payload-free operation/nonces/audits remain for quotas, replay prevention and accountability, so deletion cannot reset a paid-call limit. It does not delete separately held Life Profile observations, externally submitted research or provider-retained data. Profile controls and the history controls are separate and must be explained in the eventual interface. Already dispatched network requests cannot be retracted by a local consent change.

Owner reads return at most the latest 50 retained turns; model context uses eight by default. There is no full-history export or automatic summarisation in this version. External model processing, retention, deletion and training controls must be checked with the provider before production. The adapter sets `store: false`; that flag is not a provider-wide zero-retention guarantee. Request-body logging, tokens and decrypted content must stay out of infrastructure logs.

## Research without silent sharing

Persy may propose a general research question, relevant domains and a small call budget. This is an encrypted pending proposal, not a performed action. The member must review its exact question and approve it through a separate endpoint before it is sent. It expires after fifteen minutes by default and is single-use. Turning a private message into a general question is model work, not a guaranteed anonymisation process; the review step lets the member remove/decline inappropriate details. Editing a question requires a new proposal.

Only the stored, approved question/domain/call/collaboration fields are submitted to the Coordinator. Persy does not automatically send chat history, approved profile context, member identity or the incoming member token to that service. The trusted exchange receives the member assertion to authorise delegation, then returns a Coordinator capability for Persy's machine identity. The Coordinator and specialists still enforce their own permissions and limits.

Returned research is validated against actual task findings and presented as evidence cards, with original citations, limitations, gaps and disagreements. Unsupported references or false completion states are rejected, and confidence cannot exceed the underlying findings. Partial work remains partial; if synthesis fails, validated individual findings may still be shown as drafts. The first adapter adds no free-form model paraphrase to the research cards. General conversational replies are model output and are not source-verified research. Citation matching establishes traceability, not truth, clinical validity or applicability.

## Life Profile through its dedicated service

Persy never queries the Life Profile database. It can request only the owner's explicitly accepted/shared understanding through the profile context endpoint. Context responses must contain confirmed understanding with the expected shape. Profiling does not run automatically when a member chats or enables shared context.

The member can select up to five retained turns and explicitly request analysis. Persy extracts only the original user messages, never its own answers, and submits them with the purpose already authorised in the profile service. Private-journal sources are not supported. The Life Profiling AI enforces its own category, sensitivity, external-processing and purpose consent. Its observations remain pending until the member accepts, corrects or rejects them. Owner review, profile consent, decisions and deletion are forwarded through owner-bound capabilities. These controls remain available when Persy's model-processing consent is off; analysis still needs it.

The existing profile service and its database migration are unchanged. Changing profile sharing does not erase independently retained user-written chat messages. Owners should be able to distinguish these controls in the member interface.

## Setup and trust boundary

Install from `backend/` with `pip install -e ".[dev]"`. Create a fresh, separate Persy database and apply its own release using a migration credential:

```bash
# DATABASE_URL must point to the fresh PRIVATE Persy database for these commands.
python -m app.migrations --directory ../persy/database/migrations
python -m app.migrations --directory ../persy/database/migrations --check
```

These are not knowledge migrations. Never run this release against knowledge or profile storage. The tracked runner refuses incompatible existing history. Configure the runtime through [.env.example](.env.example), using `PERSY_DATABASE_URL` and an independent Fernet key supplied through a secret manager. Do not enter keys in chat or commit them. Apply/adapt the operator [database role template](database/runtime-role.sql), then provision a dedicated non-superuser runtime login. The template does not revoke pre-existing/public/inherited permissions; review database-connect privileges as well. It cannot alter member activation, erase nonces/audits, or read arbitrary tables.

Start a separate process from `backend/`:

```bash
uvicorn persy.main:app --host 127.0.0.1 --port 8004
```

Persy does not implement a member identity provider or browser session. A trusted gateway must authenticate the actual member, enforce account/session state and mint short-lived Ed25519 capabilities. They require actor `member`, domain `*`, issuer/audience defaults `corepath-member-gateway` / `corepath-persy`, verified opaque `sub`, unique `jti`, scope list, purpose and integer `iat`/`nbf`/`exp` with at most five minutes' lifetime. Body owner IDs, browser headers and the shared knowledge token are never identity. Founder/admin/service roles do not bypass member ownership. Use fresh request IDs for mutations and profile calls; replayed starts are rejected.

| Endpoint | Scope / purpose |
|---|---|
| `GET`, `PUT /v1/persy/privacy` | `persy:privacy` / `owner_control` |
| `POST /v1/persy/conversations`, `DELETE /v1/persy/conversations/{id}` | `persy:conversations` / `conversation_control` |
| `GET /v1/persy/conversations`, `GET /v1/persy/conversations/{id}` | `persy:read` / `conversation_review` |
| `POST /v1/persy/conversations/{id}/messages` | `persy:chat` / `conversation_reply` |
| `POST /v1/persy/conversations/{id}/research/{proposal_id}` | `persy:research` / `research_approval`; body `{"approve":true}` |
| `GET /v1/persy/profile` | `persy:profile:review` / `profile_review` |
| `PUT /v1/persy/profile/consent`, `POST /v1/persy/profile/items/{id}/decision`, profile/item deletion | `persy:profile:control` / `profile_control` |
| `POST /v1/persy/profile/analyse` | `persy:profile:analyse` / `profile_analysis` |

The first privacy update uses `expected_revision: 0`; subsequent updates must use the revision returned by the API. Initially every processing/retention/profile switch is false. An individual message is `{"message":"Help me choose one next step","use_profile_context":false}`. Analysis selects `turn_ids` and the profile's previously consented `purpose`; client-supplied content/owners are not accepted on that route.

`GET /health/live` proves process liveness only. Protected routes fail closed when the separate store, encryption, identity, model or required service is unavailable. The Founder preview site has not been connected by this backend change and cannot yet provide a live Persy conversation.

## Scoped token exchange

Persy posts `target`, fixed `action`, `request_id` and `member_capability` to a fixed trusted HTTPS exchange, with its own scoped machine credential. Targets are only `life_profile` or `coordinator`; the model cannot select a target/action. The exchange must independently verify the member assertion and machine identity, enforce each incoming scope/purpose-to-target/action delegation, bind expiry to the member assertion and refuse arbitrary claims/subjects. It returns exactly `{"capability":"<JWT>"}`.

Profile capabilities use actor `personal_ai`, the **member's verified subject**, the expected profile issuer/audience, domain `*` and the exact profile action scope/purpose. Coordinator capabilities use actor `personal_ai`, **Persy's configured service subject**, the expected Coordinator issuer/audience and `coordinator:research` / `research_request`. Both bind `jti` to the requested operation ID and cannot outlive the incoming member capability. Persy verifies these before forwarding them. Member assertions go only to the exchange, never downstream services. Private signing keys remain exclusively in trusted issuers.

The gateway/exchange implementation, real member sessions, service identities/grants and hosted service connections still require provisioning. In the knowledge database, Persy's machine subject needs the Coordinator's active `personal_ai` service identity and global `coordinate` grant. This private Persy database stores no such knowledge grants or profile tables.

## Limits, testing and remaining work

Defaults: thirty model-capable operations per member per rolling day, one concurrent operation, fifty conversations, two hundred chat starts per conversation, 1,800 model output tokens and 60,000 context characters. Starts reserve capacity transactionally before model/service work. Failed attempts count; profile review/control do not consume the model-call allowance. A lease capped by member expiry is checked between operations. In-flight requests use network timeouts and are not forcibly cancelled at lease expiry. A later start marks abandoned operations failed. There are no retries, scheduled messages, notifications, transactions or uncontrolled agent loops. Align downstream quotas and enforce gateway/provider-wide rate/spend limits separately.

Run `pytest`, `ruff check .` and `ruff format --check .` from `backend/`. Full CI uses three separate disposable PostgreSQL databases, synthetic messages/evidence, ephemeral encryption/signing keys and mocked model/HTTP providers. Tests cover ownership, encryption/binding, consent changes during inference, history erasure, profile-context withdrawal, research review/replay/expiry, quotas/concurrency, gateway delegation and real Coordinator/specialist and Life Profile workflows. They do not assess a real model's conversational quality or clinical safety. See [evaluation scenarios](evaluation.md).

Still required: live model evaluation and expert safety review, trusted member sign-in/exchange, member chat/consent/review interface, service deployment, licensed knowledge ingestion, operational monitoring/recovery, encryption-key rotation/backup/restore, retention/deletion policy, abuse controls, outcome measures and account lifecycle management. These are not established by a passing code suite. No production Persy or live-model quality is claimed here.
