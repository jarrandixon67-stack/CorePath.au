# CorePath business partner bot

The first trial is **Australian health and wellbeing**, selected by the founder. This service discovers small batches of candidates, records public business evidence, proposes research interpretations, computes an auditable qualification decision and queues eligible business invitations. An enabled worker sends those invitations through a verified provider. It is separate from the eleven personal-development specialists and has no Life Profile, journal or personal-conversation access.

The five baseline requirements are approved. The [health standard](../docs/partners/AU-HEALTH-STANDARD.md) adds four proposed sector requirements for founder review. The implementation and tests do not establish a live deployment, verified real businesses, permission to contact any recipient, approved health policy or an operational sender. **No real invitation has been sent.**

## What the rating means

Qualification requires reviewed, current evidence for every requirement in the selected country/sector policy. Unknown, expired, withdrawn or conflicting evidence means `review`. A demonstrated failure means `not_qualified`; all requirements met means `qualified`. Ratings remain internal during the trial. A numeric score, when complete, is the fraction of this checklist met, not a consumer star rating. Commercial payment never influences it.

Policies are immutable definitions with a separately recorded approval/withdrawal. Evidence is immutable content with a separately recorded review/withdrawal. All nine health requirements are mandatory; a baseline-only health policy is rejected. Reassessments preserve history. A business can correct evidence through new records and a new review.

OpenStreetMap discovery is one bounded search of at most one square degree/100 records per call, filtered to health/wellbeing candidates. It retains attribution and source links, ignores contact email tags and does not verify licensing, ownership, country or consent. An explicitly conflicting country tag is excluded; otherwise the country comes from the requested search area. OSM has incomplete coverage and can include facilities that are not independent businesses. Do not call this a complete world business register. Batch ingestion also accepts independently sourced `BusinessSeed` records; future registry/directory adapters must retain source rights and provenance.

Deduplication uses country plus a supplied registration number, otherwise website hostname, otherwise source URL. It helps prevent repeated invitations; it is not complete global entity resolution. A domain shared by branches is deliberately treated as one organisation until a reviewed parent/branch model is introduced.

## Identity and database boundary

Use an isolated PostgreSQL partner database and separate migration, API and delivery-worker credentials. Apply:

```sh
cd backend
DATABASE_URL="$PARTNERS_MIGRATION_DATABASE_URL" python -m app.migrations --directory ../partners/database/migrations
DATABASE_URL="$PARTNERS_MIGRATION_DATABASE_URL" python -m app.migrations --directory ../partners/database/migrations --check
```

Provision the actual trusted founder subject and service subjects with migration-owner access. Match the founder to a verified account identity; do not derive authority from an email address, browser input or model output. No API endpoint creates founders, changes ownership or grants roles. An Executive Administrator has operational permissions here, without any additional reserved founder powers. An administrator needs explicit action grants. Services cannot approve policy/evidence/contacts or suppress recipients through privileged APIs.

Create separate API and sender login roles outside the application. Apply `database/runtime-grants.sql` using psql variables `partners_api_role` and `partners_worker_role`. The sender can read the partner ledger and update delivery state; it cannot approve policies/evidence/contacts, change roles, remove suppressions or delete the audit trail. Timestamp-only column update grants support PostgreSQL row locks without granting permission to change authority. Neither runtime role should own tables or have access to another service database.

Protected APIs require short-lived Ed25519 capabilities, fixed issuer/audience, `actor=partner_gateway`, `purpose=business_partnerships`, `domain=*`, and the exact action scope. Subject roles and active permissions are loaded from PostgreSQL on every operation. Token `role` claims are ignored. Dispatch capabilities have single-use request IDs. Health/live and opaque recipient opt-out links are the only public operations.

## Workflow

1. Import candidates with `POST /v1/businesses` or run a small `POST /v1/discovery` search (`country`, `sector=health_and_wellbeing`, `bbox`, `limit`). Discovery does not imply qualification.
2. Create a draft with `POST /v1/policies`. `au-health-policy.proposed.json` supplies the draft definition. An authorised human reviews the actual standard with `POST /v1/policies/{id}/review`; `verified=false` withdraws approval.
3. Register evidence with `POST /v1/businesses/{id}/evidence`. An authorised human verifies/withdraws it at `POST /v1/evidence/{id}/review`. Record the exact public excerpt, source, date, expiry, criterion, result and rationale. Never import patient records or private Life Profile data.
4. Optional `POST /v1/businesses/{id}/research` requests a model draft based on at most ten registered public excerpts. Every proposal needs an exact matching quote/source ID. The model cannot verify evidence, score a business, enable email or execute tools. Drafts are returned for review rather than silently incorporated.
5. `POST /v1/businesses/{id}/assess` takes `policy_id`. `GET /v1/businesses/{id}` returns evidence and recent assessments. Business listing uses bounded UUID cursor pagination.
6. Record a reviewed business contact with `POST /v1/businesses/{id}/contact`: express or specifically reviewed inferred consent, source, notes and validity. Separately document compatibility with the proposed 10% commercial arrangement. A publicly listed address does not establish consent; a good quality rating does not establish commercial eligibility.
7. `POST /v1/assessment-batches` takes `policy_id` and at most 25 `business_ids`. It requires both research and queue scopes/permissions. It assesses each business and queues those whose current evidence, policy approval, consent, commercial review and country permit it. It sends no email itself. Individual queueing uses `POST /v1/businesses/{id}/invitations` with `assessment_id`.
8. The configured sender runs `python -m partners.worker` to process one item. An operator-managed schedule/worker can invoke it repeatedly within the daily limit. The API equivalent is `POST /v1/process-one`, with a fresh single-use send capability.

Action scopes are `partners.read`, `partners.research`, `partners.verify`, `partners.policy.manage`, `partners.contact.verify`, `partners.invitation.queue`, `partners.invitation.send`, and `partners.suppress`. Default service subjects receive only explicitly granted scopes. A queue worker that needs research snapshots also needs the read permission.

## Delivery, corrections and opt-out

Use `PARTNERS_EMAIL_DELIVERY_ENABLED=false` until the database, verified CorePath sender and actual approved policy/contact records are in place. The default allowed country is AU, the default allowed sector is health_and_wellbeing and the initial global daily limit is ten attempted invitations. International records are supported; outreach to another country requires its approved country/sector policy, consent basis, commercial review and explicit runtime country and sector settings.

The renderer discloses the proposed 10% commission, states that partnership does not buy a better rating and invites discussion rather than creating an agreement. Sender legal identity, working reply-to/contact information and the public opt-out service origin are required. No placeholder emails are sent by tests. The provider adapter uses the fixed Resend API with a stable outbox idempotency key and no redirects.

Only one initial invitation can exist per business or recipient. Queue retries are idempotent; a fresh assessment can update an unattempted queued invitation without making another message. A durable `dispatching` transition commits before the external call. Timeouts, invalid acknowledgements or failed requests become `unknown`, and interrupted `dispatching` items are not automatically retried. Reconcile these against the provider before taking any manual action; do not reset them to queued merely because a process failed. `sent` means the provider acknowledged acceptance, not confirmed inbox delivery. Bounce/reply ingestion and follow-up campaigns are not implemented.

Policy, evidence, consent, suppression, exact recipient, template and sender configuration are rechecked immediately before sending. An opaque, random opt-out token needs no sign-in. GET shows confirmation without changing state; POST, including provider one-click POST, adds suppression. Committed opt-outs win before future sends. The final send and suppression are serialised at the provider handoff boundary; an already accepted provider message cannot be recalled. `POST /v1/suppressions` lets authorised humans record direct opt-outs or bounces. Correcting an assessment does not erase past audit records.

The queue, model gateway and discovery endpoints are private service APIs, not a public internet signup form. Set request/rate limits in the deploying gateway; preserve provider quotas and directory usage rules. There is no automatic web crawler, exhaustive global index or unattended worldwide campaign in this release.

## Runtime

Set production values through the deployment secret manager. See `.env.example`. Start the API with:

```sh
uvicorn partners.main:app --host 0.0.0.0 --port "$PORT"
```

No runtime credentials are stored in the repository. API and worker processes use different `PARTNERS_DATABASE_URL` values for their restricted roles. A sending worker needs no model key or capability-signing private key. The service stores business records/contact permission metadata, not customer profiles.

## Validation

The tests use synthetic businesses, an isolated PostgreSQL database and mocked directory/model/email providers. They exercise all nine criteria, unknown/conflicting evidence, source withdrawal, policy/country/sector gates, consent and commercial compatibility, revocation, duplicate prevention, concurrency and daily caps, uncertain acknowledgements, reserved-message tampering, signed capability scopes/replay, opt-outs and actual database-role restrictions. CI prepares a separate partner database and checks tracked migrations twice plus `--check` before running the backend suite.

Local validation uses five fresh isolated PostgreSQL 17 test databases, with Ruff lint/format checks. The pull request records the final verified test count. Provider calls were mocked; no real business was rated or contacted. CI repeats against PostgreSQL 16.
