# CorePath Coordinator

The Coordinator is an internal research orchestrator for the eleven established specialists. The Personal AI submits general research requests and receives review-required reports. It remains the only member-facing AI. This service has no Life Profile credentials, member chat or direct library-reading permission.

## Research workflow

1. Verify a short-lived signed Personal AI capability, its active database service identity and explicit global `coordinate` grant. Verify the configured Coordinator identity is active as well.
2. Ask the configured model for a small specialist team, concise selection reasons and bounded research tasks. Material ambiguity can produce clarification questions without dispatching anything. The server rejects duplicate disciplines, domains outside the request allowlist and plans exceeding the effective call limit.
3. Reserve each task transactionally, then call the existing specialist API using a freshly exchanged, domain-bound Coordinator capability. Specialists still enforce their own library and database grants. A failed or malformed response is recorded as a failed task; valid work from other specialists is retained.
4. If the Personal AI explicitly allowed collaboration, a specialist requested an eligible peer and budget remains, ask the Coordinator model to approve specific follow-ups. Only requested, allowed and unused disciplines may run. There is one follow-up round, with no recursive team expansion or direct peer calls.
5. Ask for conclusions, practical options and cross-specialist disagreements, referencing real task IDs and finding indexes. Rebuild the supporting evidence server-side. Reject missing/duplicate references and invalid opposing evidence. Cap a conclusion's reported confidence at its least-confident supporting finding. Preserve all underlying specialist findings, limitations, gaps and source disagreements even when the synthesis does not mention them.
6. Recheck caller/Coordinator access and the execution lease before saving the report. Return an explicitly complete, partial, evidence-empty, clarification-needed or failed state to the Personal AI.

Model text never grants permissions. No model tools, arbitrary destination URLs, publication, source verification, profile reading, transactions or member messages are available. The Coordinator does not hold a private signing key. HTTPS service locations are fixed operator settings, redirects are not followed, and the exchange credential is never sent to the specialist service. Exchanged signatures, subject, domain, purpose, audience and request IDs are checked before dispatch.

## Evidence and quality limits

Every synthesised factual conclusion and practical option references specialist findings. Citation metadata and quotes are copied from the validated specialist response; the synthesis cannot submit its own citations or URLs. Source IDs are deduplicated when reporting the number of distinct sources, without claiming those sources are independent.

**Traceability is not truth, entailment or a quality guarantee.** A real quote can still be misinterpreted. Models may select the wrong specialist, miss a contradiction or offer a weak interpretation. Confidence remains uncalibrated judgement even after capping. Full specialist results stay visible, and every report requires review. `completed` means the requested processing and structural validation finished; it does not mean scientific acceptance or readiness for an individual's high-risk decision.

If there is no evidence, the Coordinator skips synthesis and reports gaps. If some specialists fail, the report is partial. If synthesis fails, the report retains the validated specialist results and exposes the synthesis issue, with no invented replacement conclusions. If every specialist fails, the run is failed. Expired/revoked caller access or an expired lease prevents report completion. A previously stored report is historical; later source withdrawals are not automatically propagated to every past report.

## Setup

Install the backend from `backend/` using `pip install -e ".[dev]"`. Apply migrations 001–008 explicitly through `python -m app.migrations` using a migration credential and `DATABASE_URL`. Run `python -m app.migrations --check` afterwards. The original SQL migrations remain immutable; 008 adds Coordinator records, the distinct internal `personal_ai` service role and the explicit `coordinate` action.

Use a different, restricted runtime database login. The operator-run [role template](database/runtime-role.sql) grants only service/grant/domain lookup, Coordinator records and audit inserts. It cannot read source documents, specialist run tables or profiles, edit grants or manage identities. This is an additive template: review public, inherited and pre-existing permissions. Do not reuse schema-owner, superuser, specialist or Life Profile credentials. The Coordinator must have no private-profile database authority.

Copy required settings from [.env.example](.env.example) into the environment or `backend/.env`. Start a separate process from `backend/`:

```bash
uvicorn coordinator.main:app --host 127.0.0.1 --port 8003
```

`COORDINATOR_DATABASE_URL` is explicit; it does not fall back to the profile or knowledge API database configuration. Startup refuses a database containing `public.life_profiles`. Process liveness is available at `GET /health/live`; it does not establish model, gateway, source or deployment readiness.

Provision trusted internal identities separately:

- The incoming capability's `sub` must map to an active `service_identities` row with role `personal_ai` and an unexpired global `access_permissions` action `coordinate`.
- `COORDINATOR_SERVICE_SUBJECT` must map to an active `coordinator` identity. The specialist service checks its explicit `research` and `retrieve` grants for each assigned library. This code creates no identities or grants automatically.
- Configure the Personal AI gateway's public Ed25519 key, issuer and audience. Private signing keys stay in the gateway. Human roles, other bots, shared internal tokens and browser identity headers cannot substitute for Personal AI authentication.
- Configure a reviewed Coordinator model supporting Responses API strict structured output, the scoped exchange service, specialist HTTPS endpoint and specialist gateway public key. Gateway issuance/exchange and the Personal AI client are external contracts, not implemented identity providers in this change.

The older human principal/action tables and knowledge API's temporary shared bearer guard remain separate work. A working internal service does not complete human authentication or grant a Founder/admin account access to specialist orchestration.

## Internal API

| Method and route | Capability purpose and scope |
|---|---|
| `POST /v1/coordinator/research` | `research_request`, `coordinator:research` |
| `GET /v1/coordinator/research/{run_id}` | `research_status`, `coordinator:read` |

Both require actor `personal_ai`, domain `*`, expected issuer/audience, an EdDSA signature and integer `iat`, `nbf`, `exp` timestamps with at most five minutes' lifetime. They also require `sub`, unique `jti` of at most 100 characters and a scope list. The default audience is `corepath-coordinator`. Starts are single-use by verified service subject and request ID. Reads use fresh capabilities and remain restricted to the original requesting service; there is no public job listing.

Example general research request:

```json
{
  "question": "What does the reviewed evidence say about the relationship between budgeting education and stress coping?",
  "allowed_domains": ["financial-capability", "mental-wellbeing", "learning-intelligence"],
  "max_specialist_calls": 3,
  "allow_collaboration": true
}
```

The effective budget is the smallest of request limit, server limit and allowed domain count. Requests containing extra profile/user fields are rejected. Free text can still contain personal details, so callers must minimise it and send general questions only. The raw request body is not separately stored, but plans, rationales and generated results can repeat input. Disable infrastructure request-body logging. The configured model receives the general question and specialist draft material; the adapter sets `store: false`, which is not a provider-wide zero-retention guarantee. Confirm account retention, licensing and regional requirements before live data use.

## Gateway exchange contract

The Coordinator posts only these fixed, bounded fields to `COORDINATOR_EXCHANGE_URL` using its scoped machine credential:

```json
{"domain":"nutrition","purpose":"dispatch","scope":["specialist:dispatch"],"request_id":"<reserved-task-UUID>"}
```

The trusted gateway must bind the machine identity to the configured Coordinator subject and allowlisted specialist-dispatch operation; it must not accept arbitrary subjects, roles, audiences or signing claims from the caller. Its response is exactly `{"capability":"<signed JWT>"}`, with actor `coordinator_ai`, the requested domain, purpose `dispatch`, scope containing `specialist:dispatch`, expected issuer/audience, bound subject and `jti` equal to the reserved task UUID. Maximum token lifetime is five minutes. The Coordinator verifies this before sending it only to the configured specialist endpoint. The inbound Personal AI capability is never forwarded to a specialist.

This contract must be implemented and deployed through trusted machine identity before live operation. Synthetic tests use ephemeral signing keys and HTTP mocks; no production credential issuer is bundled.

## Work limits and recovery

Requests and server capacity default to eleven specialist calls. A full team is
one Coordinator plus all eleven specialists. Auto selects only necessary domains even when all eleven are authorised.
Only an explicit `specialist_mode: "full"` request requires every initial
assessment; missing domains are rejected before dispatch. A numeric budget is
a ceiling, not a quota. Explicitly scoped jobs may use fewer; their permissions are
never broadened automatically. Reports expose actual coverage and distinguish
initial assessment from a shared peer-review round, which this older transport
does not execute. Persy still obtains approval of the exact question and scope.
Existing lower-capacity deployments stay capped until deliberately reconfigured.
No schema migration is needed; the existing database permits eleven calls.

Other defaults are twenty starts per rolling day for each Personal AI service
identity, one concurrent run, 3,000 output tokens per Coordinator model call and
80,000 JSON context characters. A run makes one planning call, at most one
collaboration-review call and at most one synthesis call. There are no automatic
retries or unattended scheduling loops. Specialist-side quotas still apply and
may be more restrictive; configure both services together and apply provider-wide
spend limits. These limits do not constitute a global currency budget.

Permissions and a 180-second lease (also capped by the incoming token expiry) are checked between operations. In-flight network calls have their own timeouts and are not forcibly cancelled at the lease boundary. On the next start, expired active runs and unfinished tasks are marked failed so they release concurrency. Failed and evidence-empty starts count towards the daily limit. A timed-out specialist request may have completed remotely; it is recorded as uncertain/unavailable locally and is not automatically replayed. Production task reconciliation and background recovery remain future work.

Coordinator runs record policy/model/input hashes, allowed domains, plan, reserved tasks, draft reports and audit events. Task reservations are committed before dispatch and are serialised against the run row, so concurrent calls cannot exceed the budget or repeat a domain. These are historical research records; retention, monitoring, backup/restore and operational ownership still need deployment policies.

## Validation and model evaluation

From `backend/`, run `pytest`, `ruff check .` and `ruff format --check .`. The full suite requires fresh, separately migrated PostgreSQL knowledge and profile test databases. Coordinator tests exercise all eleven existing specialist runtimes with synthetic evidence, actor/signature boundaries, exchanged-token binding, replay, caller isolation, revocation, collaboration controls, quotas/concurrency, confidence capping, disagreements, partial failures and the restricted database role. HTTP mocks and deterministic model doubles establish code behaviour, not live reasoning quality.

A small routing benchmark covers all eleven disciplines, ambiguity, two-discipline requests and an instruction-injection example:

```bash
python -m coordinator.evaluate
# Explicit, optional model calls: one per synthetic case; incurs provider usage.
python -m coordinator.evaluate --live --output routing-evaluation.json
```

Without `--live`, the command validates fixture contracts only and reports `live_model_evaluated: false`. A live run requires configured model/key settings and an output path. It reports actual plans and whether each matches the labelled decision and minimal domain set. Even a perfect routing score does not certify overall bot quality, factuality, clinical safety, prompt-injection resistance or synthesis quality. Real model and end-to-end evaluations, licensed source ingestion, human evidence review, Personal AI integration, trusted gateways, hosting and operational monitoring remain required before launch. No live model evaluation or deployed Coordinator is claimed by this repository implementation.

