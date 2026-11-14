# CorePath bot foundation — agreed design, runnable development build

This package implements the foundation agreed with the founder on 14 November
2026. It is a replacement candidate for review, not an additional prompt layered
onto the existing services. Importing or running the demo starts no background
research, messages, bank access, outreach, deployment or spending.

Version 0.2.1 incorporates the [second code review](CODE_REVIEW.md). Research
and coordinator-authorised drafting use separate stage-specific instructions;
model instances are revalidated at hand-off, and specialist warnings cannot be
silently dropped from Persy's draft.

Version 0.2.2 replaces conflicting common instructions with
`corepath_bots/principles.json`, shared with the older backend through a generated
packaged snapshot. The [agreed rules](../docs/AGREED-RULES.md) explain the changes.
Tests require both implementations to use identical principles. The older
coordinator now supports eleven initial assessments, rejects incomplete fully
authorised plans and reports actual coverage. Shared peer review and automatic
subscriber chat integration still need the replacement execution path.

The existing `backend/` services retain their research contracts and are not
automatically switched to this package. Their earlier nine-specialist rule has
been replaced, while remaining transport/integration limits stay explicit. See
[INTEGRATION.md](INTEGRATION.md) for a deliberate migration and known conflicts.

## What is built

| Component | Implementation |
|---|---|
| Eleven specialists | Individual scope, personality, tools required, boundaries and versioned instructions in `corepath_bots/roles.json` |
| Chief of Staff | Eleven explicit assignments; initial assessments; one routed peer-review round; evidence-referenced synthesis; feedback for each specialist |
| Persy | Companion/coach instructions; structured presentation retaining validated conclusions, limitations, disagreements and gaps |
| Life Profile | Optional model analysis, quoted proposals, repeated-pattern checks, owner review/correction/rejection/deletion, consent revisions and role-specific context sharing |
| Public location directory | City/town/rural/remote records, sourced dated facts, refresh flags and literal name search; no global data imported |
| Partner Bot | Deterministic checks against the proposed 10% commission and founder-controlled negotiating limits; nonbinding decision briefs |
| 12 | Reviewed general findings only, founder-only assignments and controls, founder-only reports, persistent shutdown generation and logical local report deletion |
| Personal tools | SMART goal/accountability fields and weighted decision comparison |
| Financial tools | Decimal budget averages across payment frequencies; no bank connection or personal investment advice |
| Physical tools | Limited adult BMI calculation, clinician-gated personalised bodyweight-plan draft builder |
| Nutrition tools | Everyday meal-plan draft builder with specialised-request referral gate and mandatory allergy/restriction review |
| Career tools | Resume and cover-letter draft builders with source fact IDs; business plans using coordinator-mediated full-team research, explicit assumptions and eight required sections |
| Recreation reminders | Opt-in daily invitation drafts, Sydney-aware local timing, quiet hours and caller-supplied duplicate suppression; no delivery worker |
| Model adapter | Explicit opt-in, environment-configured Responses API calls, no tools or redirects, bounded contexts/results and no automatic retries |

There are 16 defined roles: eleven specialists plus Chief of Staff, Persy,
Life Profile, Partner Bot and 12. Feedback & Quality and Jarmby's operational
rewrite were not fully agreed in this session and are not silently redesigned.

## Run locally

Python 3.11+ and Pydantic 2 are required. From this directory:

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m corepath_bots.cli catalogue
python -m corepath_bots.cli demo --output demo-result.json
python -m corepath_bots.cli export-instructions ./instructions
```

The demo is entirely synthetic. Its source is deliberately labelled as a fixture
with an `example.invalid` URL. It establishes execution and validation behaviour,
not research quality, medical safety, reasoning quality or live model reliability.

## Run with a real model

No live model calls were made during this build. Configure `OPENAI_API_KEY` and
`COREPATH_MODEL` securely outside the repository. The model must support the
Responses API and strict JSON schema output. Review the exact question and the
public licensed excerpts before supplying both explicit consent flags:

```bash
python -m corepath_bots.cli discuss \
  --question "Your approved general question" \
  --sources reviewed-sources.json \
  --approve-team-question \
  --allow-model-processing \
  --output discussion-draft.json
```

`reviewed-sources.json` is an array matching `contracts.Source`: `id`, `title`,
`url`, `checked_at`, `content`, `domains`, `approved_for_model: true`, and
`public: true`. These flags are trusted operator attestations, not source
verification performed by this package. Do not use the synthetic demo source as
real evidence. No model can fetch URLs, crawl cities or approve its own sources.

The default discussion has 24 model calls: eleven initial, eleven review, one
coordinator and one Persy. They execute sequentially, with a 40-second timeout per
API call and a 1,200-second overall acceptance deadline. This is bounded but is
not a fast live-chat architecture. A 13-call configuration can omit peer review;
requested but skipped review is visibly partial. There is no implied monetary
price guarantee. Live latency and cost require measurement before launch.

## Privacy and execution boundary

This is an internal Python development library and CLI, not an authenticated
public web service. Caller/owner IDs and permissions must come from a trusted
application identity layer, never model output or unauthenticated request fields.

The optional SQLite store is for local development. It is not encrypted,
production hardened, a bank database, a clinical record system or a replacement
for the existing encrypted Life Profile storage. Use synthetic data. Production
must preserve separate private profile/conversation databases, scoped identities,
encryption, consent controls, retention and deletion behaviour.

Profile proposals remain unconfirmed until the owner reviews them. Acceptance
and permission to share are separate. Changed consent resets sharing; withdrawn
analysis permission blocks further context access. Only Persy and Chief of Staff
are allowed profile context through this library interface. Specialists and 12
receive no automatic private profile context. The all-team question itself must
be explicitly approved because it may otherwise contain personal information.

Life Profile input must now be reviewed excerpts with explicit
`Message.categories` and `Message.sensitive` metadata supplied by the trusted
application/owner review flow. Unclassified input is rejected rather than guessed.
Categories and sensitivity are checked before model transmission and again
before recording proposals. These labels are not automatic content classification:
the application must review them accurately. Conversation IDs remain with evidence.
Corrections are conservatively marked sensitive; sharing them requires the
corresponding permission. Consent revisions are not reused after owner erasure.

Draft builders require `Builders(provider, caller_role="chief-of-staff")`; the
application authenticates this role before construction. This internal
coordinator facade is not a direct subscriber-to-specialist channel.

12 is disabled initially. The founder alone enables, assigns, shuts down or
erases it. Shutdown rejects new runs and discards an in-flight response before
acceptance; it cannot instantly stop computation already executing at a model
provider. Logical local report deletion does not physically erase SQLite pages,
backups, provider records or external effects. No actual notification channel is
configured to report to the founder.

Short SQLite acceptance transactions lock before checking consent, shutdown and
evidence, protecting the check/write boundary across connections. Reports from
12 retain source fingerprints; changed or retracted findings mark the report's
evidence as needing review. Production jobs, cancellation, authentication and
encrypted storage still need separate integration.

Exact source quotes and valid reference IDs establish traceability, not truth,
claim entailment, safe applicability or professional competence. All generated
answers, meal plans, workouts and documents remain drafts requiring review.

## Still to integrate

- Production authentication, frontend consent/review controls and existing API adapters.
- Durable asynchronous jobs, cancellation, progress updates, reconciliation and measured cost controls.
- Reviewed ingestion/research and geographic datasets; worldwide location coverage and current local events.
- Authorised read-only bank provider, market feeds and live financial calculations beyond simple budgets.
- Reviewed video/animation, camera-guided demonstrations and equipment-specific instruction.
- Licensed/validated optional learning assessment; no IQ test is selected or implemented.
- Joint relationship session privacy and separate participant consent controls.
- Delivery of reminders/alerts and partnership/founder notifications.
- Referral directory, commercial agreement templates, suitability evidence and approved negotiating ranges.
- Live evaluation of helpfulness, fairness, safety, reasoning, latency and cost.

All accepted product requirements, including deferred ones, remain recorded in
`roles.json` and [HANDOVER.md](HANDOVER.md). Nothing in this package claims these
integrations are operational.
