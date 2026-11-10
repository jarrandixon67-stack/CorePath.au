# CorePath Knowledge Database Model

**Status:** Initial schema specification  
**Version:** 0.1.0

## 1. Design goals

- Preserve provenance from each finding to its sources and exact document sections.
- Keep source identity separate from stored document copies and editions.
- Support eleven specialist libraries and shared sources.
- Represent competing claims without forcing premature consensus.
- Maintain immutable research history and reversible knowledge versions.
- Keep individual Life Profile data outside this database.

## 2. Main entities

| Entity | Purpose |
|---|---|
| specialist_domains | Canonical list of eleven specialist domains |
| knowledge_libraries | Domain-specific collections |
| knowledge_sources | Bibliographic or web source identity |
| source_library_links | Shared source associations with specialist libraries |
| knowledge_categories | Categories within an individual library |
| knowledge_documents | Specific file, edition or captured web document |
| document_sections | Addressable text sections used for retrieval |
| research_projects | Scoped investigations |
| research_findings | Claims, observations and conclusions from research |
| evidence_assessments | Assessment of a finding and its evidence |
| source_relationships | Support, challenge, context, duplication or supersession links |
| knowledge_versions | Versioned snapshots of curated knowledge items |
| access_permissions | Domain and action permission records for service identities |
| access_principals | Registry of human and AI service identities |
| access_role_assignments | Global or library-scoped role assignments |
| access_permission_grants | Explicit, revocable action grants for human administrator assignments |
| audit_events | Append-only record of important actions |

## 3. Relationship overview

- One specialist domain has one primary library; a library belongs to one domain.
- A source may have multiple documents or editions.
- A document belongs to one source and one library. Migration 002 adds source_library_links so a source record can be associated with multiple libraries; migration 003 adds library categories.
- A document contains many sections.
- A research project belongs to a domain and may reference many sources.
- A research finding belongs to a project and may cite many sections and sources.
- An evidence assessment evaluates a finding and records its supporting and challenging material.
- Source relationships connect two source records with a typed relationship.
- Knowledge versions preserve prior states of curated findings or knowledge records.
- Access permissions are granted to service identities for specific domains and actions.
- Audit events record actor, action, target, timestamp and safe metadata.

## 4. Evidence classification

Use controlled labels, not a single universal quality score:

- established_evidence
- emerging_research
- traditional_historical_knowledge
- professional_opinion
- unverified_claim
- mixed_or_contested

These labels describe the status/type of a claim, not an endorsement. Each assessment must explain its reasoning and limitations.

## 5. Source relationship types

- supports
- challenges
- contextualises
- duplicates
- supersedes
- derived_from
- cites

## 6. Retrieval requirements

A retrieval result must return:
- domain/library identity
- source title and canonical locator
- document title/edition
- section identifier and location
- relevant excerpt
- publication and retrieval dates where known
- evidence classification where assessed
- limitations and review status

Semantic similarity alone must not be treated as evidence of truth. Use lexical matching, metadata filters and semantic retrieval together. Include contrary material when relevant.

## 7. Integrity and lifecycle

- Prefer UUID primary keys.
- Use UTC timestamps.
- Store canonical URLs separately from retrieval URLs.
- Store SHA-256 checksums for imported files and extracted content.
- Keep raw source material immutable after ingestion; corrections create a new document version.
- Record ingestion status and failure reasons.
- Use soft deletion/tombstones where legal retention or audit obligations require traceability.
- Do not store secrets, credentials or individual Life Profile content in this schema.

## 8. Implementation note

The first SQL migration establishes the core relational entities and the eleven domain seed records. Vector columns and indexes should be introduced only after confirming the chosen embedding dimensions and managed PostgreSQL extension support. This avoids locking the schema to an embedding model prematurely.

Migrations 002–005 extend the initial schema with source-library associations, categories and source verification, human/AI principals, scoped role assignments and the Executive Administrator role. These tables do not enforce API permissions by themselves; endpoint-level authorisation remains unfinished. See [migration instructions](../../backend/README.md#database-migrations) and [implementation status](implementation-status.md).

Migration 006, brought forward from the knowledge-infrastructure feature branch, stores delegated administrator action grants with optional library scopes, grant reasons and revocation timestamps. The Python policy evaluates the permitted action set; identity loading and endpoint enforcement remain separate implementation work.
