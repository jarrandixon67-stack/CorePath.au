# CorePath Feedback Bot

The founder requested a dedicated bot whose only job is to ask for feedback, examine reviews for recurring themes and raise possible concerns. The scope explicitly includes **positive and negative feedback about both CorePath and partner businesses**. This service does not recommend treatments, investigate private Life Profiles, qualify businesses, change ratings, impose sanctions or send recruitment invitations.

Its code is implemented and tested; the service, member gateway and model are not deployed/configured. No real feedback has been collected or analysed, and no feedback requests have been sent. The existing website does not yet have a live feedback-service connection. The separate journalling introduction is already published in the Sites project.

## Asking without pressure

`POST /v1/targets/{target}/prompt` returns neutral questions for Percy/the CorePath UI to present: what worked, what did not or could improve, and what should change. Each answer is optional. The bot does not request a positive rating, offer a reward for praise or demand a negative answer. Prompts are in-app responses, not outgoing email messages. The default cooldown is thirty days per target and seven days across all targets for each owner. `PUT /v1/prompt-preference` turns requests off; voluntary feedback submission remains possible.

`corepath` is the initial target. An authorised operator registers a partner target as `business:<UUID>`, after verifying that it identifies the intended business. That reference is not permission to access the partner database. Targets stay separate when collecting and analysing feedback.

## Intake and privacy

`POST /v1/targets/{target}/feedback` accepts positive, negative and constructive text and a stable client retry reference. AI analysis defaults off. The client must explain before submission that the CorePath quality team can review submitted feedback, advise against including identifiable health details, and provide a separate, unselected AI-analysis choice. Do not preselect analysis or represent feedback as anonymous/public. External model processing requires that choice.

Feedback bodies and derived theme/concern payloads use a dedicated Fernet key, bound to the owner/target, record ID and purpose. Swapping ciphertext between records or changing a consent flag without its authenticated content fails verification. Owner identifiers are HMAC pseudonyms using a separate managed key. Audit events contain action/reference metadata, not feedback text. Nothing is added to a Life Profile or journal, used to infer personality or sold as personal profile information. Identifiable details might still appear in submitted text, so restricted team access and explicit analysis consent matter.

Owners use `GET /v1/own-feedback`, `PUT /v1/own-feedback/{id}/analysis-consent` and `DELETE /v1/own-feedback/{id}`. A retry cannot silently change saved text/consent or restore withdrawn feedback. Withdrawal removes the active ciphertext and retracts/clears derived themes that cite it. Consent/source versions are checked again after model processing, so late output cannot restore withdrawn material. Previously transmitted provider inputs and backups cannot be recalled by an active-database deletion.

Authorised human reviewers can read unanalysed feedback with `GET /v1/targets/{target}/records`; the AI service cannot use that endpoint or table. Human review is necessary for feedback whose author declines AI processing. No round-the-clock or emergency-response promise is made.

## Reviews and evidence

`POST /v1/targets/{target}/reviews` imports a review only through authorised human-source review, with a source URL/reference, contributor reference, original publication date and documented permission/analysis basis. Public visibility alone is not treated as permission to collect, store or send a review to a model. Licensed provider integrations and source-rights checks must precede live automated feeds. No general web scraper or live reviews provider is enabled.

Duplicate source references are rejected. Publication date is preserved; an old review is not presented as recent because it was just imported. An authorised moderator can withdraw a source at `DELETE /v1/review-records/{id}` and invalidate dependent signals.

## Finding themes and raising concerns

`POST /v1/targets/{target}/analyse` gives the model only current, active, AI-authorised feedback/review records. A batch considers at most ten records in the configured ninety-day window, within a 50,000-character default budget, preserving full fields rather than silently removing qualifying context. It is a bounded sample, not a claim to have examined every review. Model output is not stored as an accepted fact.

Every proposed theme requires an exact quote, field and record ID. Praise, improvements and concerns are separate; positive comments never cancel a serious concern. By default a recurring theme needs three distinct contributor identifiers. Those identifiers do not prove independent people, genuine purchases or representativeness; cross-posts, coordinated reviews and selection bias remain review concerns. A single possible serious safety/privacy report may be flagged for urgent **human triage**, labelled as an unverified signal. This does not establish that an allegation is true.

Signals are encrypted records with source provenance and an explicit `review_required` response. `GET /v1/targets/{target}/themes` is restricted to authorised human staff. A person can acknowledge, investigate, resolve or dismiss a signal at `POST /v1/themes/{id}/resolution`, with a documented reason. Source withdrawal retracts the signal and prevents a late resolution from restoring its text. Repeated analysis of the same topic, source set and versions is deduplicated. No email/Slack notification or automatic partner-rating change is implemented.

Feedback can suggest questions for CorePath's future funding-dependent research programme. It cannot establish that a treatment works. Research priorities and outcomes must remain independent of partner commissions; see the [health standard and research direction](../docs/partners/AU-HEALTH-STANDARD.md).

## Technical boundaries and setup

Use a separate PostgreSQL feedback database, a separate migration owner and non-owner API/analysis roles. Do not reuse partner, Persy or Life Profile runtime credentials. Apply the tracked schema with the existing migration runner:

```sh
cd backend
DATABASE_URL="$FEEDBACK_MIGRATION_DATABASE_URL" python -m app.migrations --directory ../feedback/database/migrations
DATABASE_URL="$FEEDBACK_MIGRATION_DATABASE_URL" python -m app.migrations --directory ../feedback/database/migrations --check
uvicorn feedback.main:app --host 0.0.0.0 --port "$PORT"
```

Provision verified account/service subjects in `feedback_actors` using migration-owner authority. Never create founder authority from model claims, an email address or browser input. Members can act on their own feedback only. Founder/Executive Administrator and explicitly delegated administrators can perform quality-team review; services are restricted to `feedback.analyse`. No API grants roles or changes ownership.

Apply `database/runtime-grants.sql` with the pre-existing `feedback_api_role` and `feedback_analysis_role` psql variables. The analysis role can select only the consent-filtered `feedback_analysis_sources` view, limited identity/target metadata and required theme identifiers. It cannot select raw unconsented records, change consent, resolve concerns, edit roles, read partner ratings or access Life Profiles. These restrictions are checked with real PostgreSQL roles in the tests.

Protected endpoints require Ed25519 capabilities issued by the trusted gateway, `actor=feedback_gateway`, `purpose=feedback_quality`, `domain=*`, the feedback audience and exact action scopes. Active roles/permissions are read from PostgreSQL on each operation. Identity scopes are separate from partner/research service scopes. Supply keys only through the deployment secret manager; see `.env.example`. Deploying gateways must enforce body/rate limits and verified member identity.

The tests use synthetic sources and mocked model calls, including both feedback polarities, cross-target separation, request cooldowns, consent defaults/withdrawal races, strict source grounding, duplicate contributor handling, urgent triage, human resolutions, API role/purpose enforcement and a restricted database analysis role. They establish implementation behaviour, not live model quality or a production privacy/operational review.
