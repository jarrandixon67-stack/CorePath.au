# Knowledge Infrastructure Implementation Status

**Scope:** Knowledge-infrastructure foundation in this repository.

Use the [CI workflow](../../.github/workflows/knowledge-infrastructure-ci.yml) and [GitHub Actions results](https://github.com/jarrandixon67-stack/CorePath.au/actions) to verify the exact branch and commit being assessed.

## Completed repository work

- [x] Initial architecture specification.
- [x] Initial relational data-model specification.
- [x] Architecture decision log.
- [x] Initial PostgreSQL schema migration with eleven specialist domain and library seed records.
- [x] FastAPI application scaffold.
- [x] Typed environment configuration.
- [x] Optional PostgreSQL connection pool.
- [x] Liveness and database-readiness endpoints.
- [x] Health endpoint tests, including configured and unconfigured database cases.
- [x] Dockerfile and local development documentation.
- [x] GitHub Actions workflow for PostgreSQL migration validation, specialist seed-count checks, backend tests and linting.
- [x] Source-to-library association migration.
- [x] Authenticated source registry API: list libraries, list library sources and register source metadata.
- [x] Initial bearer-token guard and authentication tests.
- [x] Source records can be associated with multiple specialist libraries without duplicating source metadata.
- [x] Specialist library categories and initial category seed data.
- [x] Live library overview endpoint with registered-source, verified-record and accepted-finding counts.
- [x] Category creation and category-aware source registration endpoints.
- [x] Source verification status updates with audit events.
- [x] End-to-end CI test for library, category, source registration and verification flow.
- [x] Transactional database connection configuration with regression tests.
- [x] Initial human and AI principal registry with library-scoped researcher and specialist-AI role grants.
- [x] Database guard enforcing human versus AI service role types.
- [x] CI migration validation for identity and access schema.
- [x] Founder and Executive Administrator hierarchy added to the role schema.
- [x] Executive Administrator role constrained to a global human principal.
- [x] CI applies and validates the Executive Administrator migration.
- [x] Explicit migration runner with version/checksum history, advisory locking and transactional batch application.
- [x] Read-only pending-migration check and repeat-application CI checks.
- [x] Migration regression tests and documented deployment/recovery procedure.

## Eleven-specialist runtime continuation

- [x] All eleven established specialist briefs and distinct instruction/policy hashes.
- [x] Separate specialist service with signed Coordinator dispatch and own-domain independent research.
- [x] Active service identity, database role/domain, library status and retrieval/research grants checked per request.
- [x] Verified active source, completed extraction and explicit model-use approval required for retrieval.
- [x] Quoted citations, server-owned provenance, draft findings, limitations and knowledge gaps.
- [x] Persisted run states, policy/input hashes, audit events, replay protection and transactional quotas.
- [x] Access/evidence rechecked before saving; collaboration requests recorded without peer execution.
- [x] Migration 007 and restricted runtime database-role template.
- [ ] Real model quality evaluation and trusted machine-identity gateway/Coordinator integration.
- [ ] Deployed specialist service and licensed ingestion/review workflow.
- [ ] Scheduling, multilingual/semantic retrieval, evidence acceptance/versioning and approved collaboration execution.

See the [specialist setup and boundaries](../../specialists/README.md). The human knowledge API authorisation checklist below is separate and remains incomplete. Consult the exact continuation commit's CI before claiming validation.

## Verification evidence

The [cleanup merge run](https://github.com/jarrandixon67-stack/CorePath.au/actions/runs/42862635494) for commit `59ffc7006079e364b055300f1bcf19587ab2084a` passed. Its [PR run](https://github.com/jarrandixon67-stack/CorePath.au/actions/runs/42862486204) verified all eight original backend tests, all five original migrations, specialist seed data, lint and formatting.

The continuation brings forward the existing permissions foundation and migration 006 from `feature/knowledge-infrastructure-foundation` at commit `584b824aa954e10d5ea19cbe2c91436c960ca346`. Its [CI run](https://github.com/jarrandixon67-stack/CorePath.au/actions/runs/42839462104) passed before integration. The integrated policy also tests Coordinator-only task dispatch, malformed global-role scopes and revoked grants.

The migration-tracking continuation adds tests for repeat application, read-only pending checks, failed-batch rollback, changed/missing history and untracked-data preservation. Check the exact continuation commit's CI result to verify those additions; the earlier baseline does not establish their success or production readiness.

- [x] Full CI passed for the cleanup merge, including migrations, tests, lint and formatting.
- [ ] Verify the migration-tracking release commit's full CI result and selected managed PostgreSQL service/version before deployment.

## Not yet verified or implemented

- [ ] Migration tested against the selected managed PostgreSQL service/version.
- [ ] Cloud provider, region and operating budget selected.
- [ ] Database backups and restore procedure tested.
- [ ] Production identity provider and secure server-side session selected and implemented.
- [ ] Endpoint-level role and action authorisation implemented and tested.
- [ ] Founder and administrator accounts provisioned through trusted identity management.
- [ ] Specialist researcher invitation and library-scoped access workflow implemented.

## Next implementation sequence

The migration-tracking milestone and [deployment procedure](deployment.md) are implemented in this continuation. The [build handover](../HANDOVER.md) records the wider direction and remaining decisions.

1. Implement secure administrator authentication and server-side session handling; choose identity provider before deployment.
2. Implement action-level authorisation for founder and administrator roles, then library-scoped researcher access.
3. Connect Intelligence Centre through a server-side API proxy; remove hardcoded demonstration data.
4. Complete source registry validation and duplicate handling.
5. Implement document ingestion, extraction and section indexing.
6. Implement hybrid retrieval and provenance-rich results.
7. Implement evidence assessments and knowledge versioning.
8. Add Coordinator-authorised cross-specialist research workflows.

## Important boundary

### Life Profile continuation

The founder has prioritised the Life Profiling bot as the first bot to build. Its [separate service](../../life-profile/README.md) now implements encrypted storage, consent, signed Personal AI capabilities, proposed observations, owner review/correction/deletion and explicitly approved context sharing. Its tables and migration are in a separate database, not the knowledge schema.

The model connection, real owner-identity gateway, deployed profile database and user-facing review flow remain unconfigured. Consult the exact Life Profile continuation commit's CI results; this implementation must not be represented as an operational bot in the Founder portal.


Repository commits are not equivalent to deployed infrastructure. No production API, database, research automation or AI specialist is considered operational until separately provisioned, deployed and tested.


## Access governance decisions

- [x] Executive Administrator positioned directly below Founder, with Founder-reserved powers.
- [x] Action-level permission boundaries documented separately from role names.
- [x] Life Profile and Coordinator/specialist orchestration boundaries explicitly excluded from automatic Executive Administrator access.

**Next implementation work:** connect trusted identity, load principal/role/action grants from PostgreSQL, and enforce the existing policy at API endpoints with allow/deny tests. Keep the shared bearer token as a temporary development-only guard until a trusted identity provider and server-side session are in place.


## Action-level authorisation foundation

- [x] Deny-by-default policy evaluator for active principals and active role grants.
- [x] Founder and Executive Administrator permission boundaries.
- [x] Explicit action grants for administrators, with optional library scope.
- [x] Specialist researcher and specialist AI library isolation.
- [x] Coordinator-only specialist task dispatch permissions.
- [x] Explicit denial of Life Profile access through the knowledge API permission catalogue.
- [x] PostgreSQL migration for revocable administrator action grants.
- [x] Unit tests for role boundaries and library scope.
- [x] Database integration tests for grant constraints.
- [ ] Trusted identity provider and secure server-side sessions.
- [ ] Load authenticated principals and grants from PostgreSQL.
- [ ] Apply permission dependencies to every protected API route.
- [ ] Add endpoint-level allow/deny tests for each role and action.

**Boundary:** The policy evaluator is a tested foundation, not yet active HTTP route enforcement. The current shared bearer token does not identify a human or AI principal. Do not expose the internal-token API as a production user-facing service until identity and per-request authorisation are connected.
