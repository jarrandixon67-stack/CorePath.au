# Knowledge Infrastructure — Decision Log

## D-001: Shared infrastructure, separate specialist libraries

**Status:** Accepted  
**Decision:** Build one shared knowledge platform with eleven separate specialist libraries.  
**Reason:** Reuse core services while preserving domain boundaries and independent research.

## D-002: Modular monolith for initial deployment

**Status:** Proposed baseline  
**Decision:** Begin with one modular API application and separate background workers rather than microservices.  
**Reason:** Lower operational complexity and cost; split services only when measured scale or ownership boundaries justify it.

## D-003: PostgreSQL as primary relational store

**Status:** Proposed baseline  
**Decision:** Use managed PostgreSQL for metadata, research records, permissions and audit history. Evaluate pgvector and PostgreSQL full-text search for retrieval.  
**Reason:** Mature relational integrity and a simple initial operating model. Confirm hosting compatibility before enabling extensions.

## D-004: Object storage for original documents

**Status:** Proposed baseline  
**Decision:** Store permitted source files in private S3-compatible object storage; keep metadata and searchable text references in PostgreSQL.  
**Reason:** Avoid bloating the relational database and support durable document storage.

## D-005: Life Profile is outside the knowledge repository

**Status:** Accepted  
**Decision:** Do not store individual Life Profile records in the specialist knowledge database.  
**Reason:** Maintain the agreed exclusive Life Profiling AI access boundary and separate personal data from general knowledge.

## D-006: Research freedom with provenance and critical evaluation

**Status:** Accepted  
**Decision:** Specialists may research independently within their domain and authorised tools. Sources and findings must be traceable and evaluated.  
**Reason:** Support intellectual independence without treating institutional status, popularity, traditional origin or natural origin as proof.

## D-007: Coordinator-controlled specialist collaboration

**Status:** Accepted  
**Decision:** Specialists may communicate with one another only when explicitly authorised by the Coordinator for a defined task.  
**Reason:** Enable deliberate cross-disciplinary work while maintaining controlled collaboration.

## D-008: Do not lock vector dimensions prematurely

**Status:** Accepted  
**Decision:** Defer vector schema/index details until embedding model and dimensions are selected.  
**Reason:** Avoid unnecessary migrations and model-specific coupling.

## D-009: Phased human and AI access with library-scoped researcher roles

**Status:** Accepted  
**Decision:** Design access for founder, administrators, specialist researchers, specialist AI services and the Coordinator from the beginning. Introduce human researcher access after the initial administrator workspace is operational. Specialist researcher and specialist AI grants are scoped to an individual library.  
**Reason:** Avoid redesigning access controls later while preserving least privilege and the separation between human contributors and AI service identities.

**Permission boundary:** Authentication establishes who is calling; authorisation determines which libraries and actions that identity may use. Reading a source, contributing a research assessment, registering a source, verifying a source, managing permissions and publishing an accepted finding are distinct permissions. A researcher does not automatically receive verification, administrative or cross-library rights.

**AI boundary:** Specialist AI identities are library-scoped. The Coordinator is a separate service identity authorised to coordinate cross-specialist work. Specialist-to-specialist collaboration remains Coordinator-authorised. No knowledge-library role grants access to Life Profile data.

**Implementation constraint:** The current shared bearer token is a temporary internal development guard, not production human authentication. Production access must use a trusted identity provider, server-side sessions or service credentials, and server-enforced permissions. Do not place internal credentials in browser JavaScript.

## D-010: Founder and Executive Administrator hierarchy

**Status:** Accepted  
**Decision:** Add a global **Executive Administrator** role directly below the Founder and above all other administrators, researchers and contributors. The Founder retains ultimate ownership and reserved authority. The Executive Administrator receives broad operational and governance permissions delegated by the Founder.  
**Reason:** CorePath requires a trusted second-in-command who can manage the platform and people without holding the Founder's ultimate ownership powers.

**Reserved Founder powers:** Transfer or relinquish ownership; appoint or remove the Executive Administrator; change the Founder role or its reserved permissions; approve dissolution or transfer of CorePath; and override or revoke any delegated grant. These powers are not inherited by the Executive Administrator.

**Executive Administrator scope:** Global operational oversight, user and researcher administration, library and source management, research oversight, and delegated approval of knowledge publication and verification. The Founder may narrow or revoke these permissions. The role does not automatically grant access to Life Profile data or private user conversations; those remain separately controlled boundaries.

**Security:** The role is assigned only to a named, individually authenticated human principal. It must not be shared as a generic account. All privileged actions are audited, and sensitive changes should require re-authentication and, where appropriate, a second approval.


## D-011: Separate role hierarchy from action-level permissions

**Status:** Accepted  
**Decision:** A role identifies a person's organisational authority, but does not by itself grant unrestricted access to every operation or dataset. Enforce explicit action permissions and data boundaries server-side.

| Action | Founder | Executive Administrator | Administrator | Specialist researcher |
|---|---|---|---|---|
| View operational dashboard | Yes | Yes | Delegated | No, unless needed |
| Manage ordinary users and researcher invitations | Yes | Yes | Delegated | No |
| Create, edit and organise knowledge sources | Yes | Yes | Delegated | Within assigned library, as granted |
| Review and verify sources | Yes | Yes, delegated | Delegated | Submit review only by default |
| Approve/publish accepted research findings | Yes | Yes, delegated | Delegated | Submit proposals only |
| Manage role grants below own authority | Yes | Yes, delegated | Only if explicitly granted | No |
| Appoint/remove Executive Administrator | Yes | No | No | No |
| Change Founder-reserved powers or transfer ownership | Yes | No | No | No |
| Access Life Profile records or private conversations | Only through separately authorised systems and purpose | No automatic access | No automatic access | No |
| Access specialist AI runtime or issue cross-specialist tasks | Through approved governance controls | Operational oversight only; not an alternate Coordinator | No | No |
| Direct specialist-to-specialist communication | Only through Coordinator-authorised workflow | No bypass | No bypass | No bypass |

**Executive Administrator limits:** This role is broad but delegated. It may manage ordinary administrators, researcher accounts, library operations and research workflows. It cannot appoint or remove the Founder or Executive Administrator, alter Founder-reserved powers, transfer ownership, bypass the Coordinator's specialist orchestration boundary, or gain Life Profile access merely by rank.

**Permission implementation:** Represent permissions as explicit actions (for example library.source.create, library.source.verify, research.finding.publish, access.user.manage, access.role.grant, platform.settings.manage). Each request must be checked against the authenticated principal, active role grant, scope, resource and action. Record privileged grants and decisions in an append-only audit trail. Deny by default.


## D-012: Explicit, tracked transactional schema releases

**Status:** Implemented technical baseline
**Decision:** Keep the original numbered SQL files, validate and record their checksums in `schema_migrations`, and run pending files explicitly through `python -m app.migrations`. Apply the pending batch and its history atomically, with an advisory lock coordinating runners. Provide a read-only pending check. Do not run migrations during API startup or automatically adopt existing untracked schemas.

**Reason:** Make repeat releases auditable, prevent reapplying or silently changing completed migrations, and ensure failures do not leave partially applied batches. Existing databases created through direct SQL need separately reviewed adoption; no reset or automatic downgrade is provided. New SQL files must remain transactional, with one outer BEGIN/COMMIT wrapper and no internal transaction-control statements.

**Verification:** CI uses the runner twice, checks for pending work, validates specialist seeds and runs regression tests in isolated test schemas. See the [deployment procedure](deployment.md) and exact commit's CI result.
