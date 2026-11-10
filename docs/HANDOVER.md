# CorePath build handover

This implementation handover is reconstructed from the repository, recorded decisions and the founder-supplied platform handover in this development conversation. The [platform brief](COREPATH-PLATFORM.md) records the supplied direction and distinguishes it from verified implementation. It does not claim access to another assistant's private chat. Update it alongside meaningful milestones so the next contributor can resume from evidence.

## Product direction

Continue the CorePath described in the [product requirements repository](https://github.com/jarrandixon67-stack/CorePath): Life Profile, personalised AI support, social/community, events/experiences, professional referrals, and education/development. The documented integrated-platform direction remains in place. Suggestions from a review are not automatically approved product changes.

The immediate build is the shared knowledge foundation for eleven specialist domains. Its permissions, evidence handling and interfaces support the wider platform. Personal Life Profile records remain outside this database.

## Verified starting point

- Requirements cleanup: [CorePath PR 1](https://github.com/jarrandixon67-stack/CorePath/pull/1), now merged. The complete architecture was recovered, the platform-map filename corrected and documentation indexed.
- Implementation cleanup: [CorePath.au PR 8](https://github.com/jarrandixon67-stack/CorePath.au/pull/8), merged as `59ffc7006079e364b055300f1bcf19587ab2084a`.
- [Main-branch CI](https://github.com/jarrandixon67-stack/CorePath.au/actions/runs/42862635494) passed for that merge. The cleanup's [PR CI](https://github.com/jarrandixon67-stack/CorePath.au/actions/runs/42862486204) verified all eight existing backend tests, all five original migrations, seed data, lint and formatting.
- The baseline API implements library/category/source metadata and source verification. The static frontend uses illustrative data and does not save submissions or call the API.

## Current continuation

The founder has prioritised the **Life Profiling bot first**, supplying `Life Profile.docx` as requirements input. The first [profile service](../life-profile/README.md) and [source-document requirements review](life-profile/requirements.md) now define that continuation. It is a separate service/database, with signed Personal AI capabilities, encrypted profile data, consented model analysis, owner review/correction and controlled sharing. This changes the immediate bot build order; it does not discard the remaining eleven-specialist architecture.

The model, trusted identity gateway and profile deployment are not configured by this code. The hosted Founder portal remains a separate private workspace, without a live profile conversation interface. Confirm the Life Profile continuation commit's actual CI results before claiming its tests pass.

The [private Founder workspace](FOUNDER-WORKSPACE.md) is now deployed with managed ChatGPT sign-in. Its 14 local request/response tests passed. It does not yet connect to PostgreSQL or provision its Founder role; keep that distinction visible when describing access.

The previous handover identifies additional permissions work on `feature/knowledge-infrastructure-foundation` at `584b824aa954e10d5ea19cbe2c91436c960ca346`. Its [CI run](https://github.com/jarrandixon67-stack/CorePath.au/actions/runs/42839462104) passed. This continuation brings its policy engine, tests and migration 006 forward while retaining the main-branch cleanup. Coordinator-only execution is protected against human-role escalation.

A supporting foundation task is also implemented here: tracked database migrations and a repeatable [deployment procedure](knowledge-infrastructure/deployment.md).

- `python -m app.migrations` applies pending files with transactional history, checksums and a shared runner lock.
- `--check` reports pending work without database writes.
- All six existing migrations are preserved. Existing untracked databases require a reviewed adoption plan.
- CI now uses the runner twice and checks for pending migrations before running the API tests. New tests exercise repeat runs, changed/missing history, rollback and preservation of untracked data in isolated test schemas.

Use the exact continuation commit's CI result to confirm these additions. The verified baseline above is not evidence that a later commit or a production deployment passed.

## Next implementation sequence

**Current first-bot priority:** complete the Life Profile model connection and evaluations, separate deployment, trusted Personal AI gateway, and owner-facing consent/review controls. The broader sequence below remains relevant to the shared knowledge platform.

1. Confirm the integrated test suite and permissions engine are stable.
2. Select the production identity provider and implement secure administrator authentication and server-side sessions.
3. Load verified principals and action grants from PostgreSQL, then enforce the recorded action permissions, Founder-reserved powers, delegated Executive Administrator authority and library scopes at API endpoints; test denied actions as well as permitted ones.
4. Connect the Intelligence Centre through an authenticated server-side API layer and replace demonstration data with real responses.
5. Complete source validation and duplicate handling, then ingestion, extraction and section indexing.
6. Add provenance-rich lexical/semantic retrieval, evidence assessments and knowledge versioning.
7. Implement Coordinator-authorised specialist research and collaboration, then continue the wider product roadmap.

## Boundaries and unresolved decisions

- The shared bearer token is a temporary development guard. It must stay out of browser JavaScript. Role tables alone do not enforce API access.
- Knowledge-library authority does not grant access to Life Profiles or private conversations. Founder and Executive Administrator access remain governed by the recorded decisions; specialists do not bypass the Coordinator.
- No production API, database, cloud region, backup system, research automation or specialist bot has been established as operational by this repository work.
- Identity provider, hosting provider/region, budget, backups/restore targets and source-licensing details still require decisions. Enter secrets through the hosting platform, not chat or Git.
- The requirements repository flags an incomplete D013 cooling-off protocol and legal copyright-owner placeholders. Preserve these as unresolved rather than inventing policy or ownership details.

## Resume checklist

Read [implementation status](knowledge-infrastructure/implementation-status.md), [architecture](knowledge-infrastructure/architecture.md), [technical decisions](knowledge-infrastructure/decisions.md) and the latest PR/CI results. Confirm the current branch and base commit before editing; do not overwrite another contributor's work. Keep implemented code, passing tests and deployed infrastructure distinct in every update.
