# CorePath Knowledge Infrastructure Architecture

**Status:** Initial technical baseline  
**Version:** 0.1.0  
**Scope:** Stage 1 — shared knowledge infrastructure for eleven specialist domains

## 1. Purpose

Provide a shared, extensible platform through which CorePath specialist systems can discover, ingest, organise, retrieve, evaluate and improve domain knowledge. The infrastructure must support independent specialist research while preserving provenance, access boundaries, auditability and operational reliability.

This document describes the proposed architecture. It does not claim that production services, AI bots, research automation or cloud hosting are deployed.

## 2. Architectural principles

1. **One shared foundation, eleven domain libraries.** Common services are reused; domain content and research ownership remain separated.
2. **Research independence.** A specialist may investigate sources within its authorised domain without waiting for the Coordinator. Cross-specialist collaboration requires explicit Coordinator authorisation.
3. **Provenance by default.** Findings must link to source records and, where possible, exact document sections or source locations.
4. **Evidence pluralism with critical evaluation.** Conventional research, traditional and Indigenous knowledge, historical records, practitioner knowledge and emerging hypotheses may be investigated. Origin or institutional status alone does not establish truth.
5. **Separate evidence categories.** Established evidence, emerging research, traditional/historical knowledge, professional opinion and unverified claims must not be conflated.
6. **Least-privilege access.** Services and bots receive only the permissions needed for their role.
7. **No Life Profile in the knowledge repository.** Personal Life Profile data is a separate protected system. This repository stores general knowledge and research artefacts, not individual profiles.
8. **Human-auditable change.** Knowledge changes are versioned, attributable and reversible.
9. **Incremental scalability.** Start with managed relational storage and object storage; add specialised infrastructure only when measured need justifies it.
10. **Cost-aware research.** Support scheduled, question-driven and knowledge-gap research with budgets, rate limits and deduplication.

## 3. Proposed technology baseline

The repository currently contains only a minimal README. No application framework, database, deployment configuration or existing backend has been identified. The following is therefore a proposed baseline to validate before deployment:

| Concern | Initial recommendation | Rationale |
|---|---|---|
| API/backend | Python with FastAPI | Strong document-processing ecosystem and typed API contracts |
| Primary database | Managed PostgreSQL | Relational integrity, transactions, JSON metadata and mature operations |
| Semantic retrieval | pgvector extension, subject to hosting compatibility | Keeps initial retrieval stack simple |
| Lexical retrieval | PostgreSQL full-text search | Complements semantic retrieval and supports exact terms |
| Original files | S3-compatible object storage | Durable, scalable document storage |
| Ingestion | Python worker processes | Reusable extraction and normalisation pipeline |
| Background work | Managed queue or Redis-backed workers | Retryable asynchronous ingestion and research jobs |
| Packaging | Docker | Repeatable local and hosted environments |
| Hosting | Managed cloud services in a selected region | Reduce operational burden; choose provider after cost, residency, backup and service review |
| Observability | Structured logs, metrics and error reporting | Operational visibility and incident diagnosis |

Do not add Kubernetes, a separate vector database, a graph database or multiple microservices at the outset. Reassess only when workload and scale justify them.

## 4. Logical components

### 4.1 Research service
Accepts scoped research requests, records queries and research projects, stores discovered source metadata, and tracks retrieval dates and search coverage. Research content is untrusted input and must never be treated as executable instructions.

### 4.2 Source and document registry
Maintains canonical source records separately from imported document instances. A source may have multiple editions, URLs or stored files. Record identifiers, authors, publishers, dates, licences and retrieval details where available.

### 4.3 Ingestion pipeline
Validates file type and size; scans uploads; extracts text and metadata; records extraction status; divides content into addressable sections; computes checksums; and queues indexing. Preserve original files where permitted. Respect copyright, licences, privacy and source terms. Where storage is not permitted, retain only allowed metadata and a reference.

### 4.4 Knowledge repository
Stores domain libraries, sources, documents, sections, research projects, findings, assessments, relationships, versions and audit events. Every knowledge item is assigned a domain or explicitly marked as shared.

### 4.5 Retrieval service
Provides permission-checked lexical and semantic retrieval. Results include source identity, document title, section locator, relevant dates, evidence classification and confidence/limitations metadata. Retrieval must not silently remove contradictory findings.

### 4.6 Evidence evaluation
Records claim-level assessments, methodology notes, supporting and challenging sources, limitations, conflicts of interest and review status. Avoid a universal numeric credibility score: source suitability depends on the question and type of knowledge.

### 4.7 Access gateway
Enforces service identity, domain scope, role permissions, request purpose and audit logging. Bot instructions are not a security boundary; permissions must be enforced server-side.

## 5. Specialist domains

The initial registry contains these eleven domains:

1. Personal Development
2. Physical Development
3. Nutrition
4. Mental Wellbeing
5. Relationships
6. Learning & Intelligence
7. Financial Capability
8. Career & Business
9. Practical Life Skills
10. Parenting & Family
11. Recreation & Discovery

Each domain receives its own library. Shared sources may be linked to multiple libraries without duplicating the underlying source record.

## 6. AI network boundaries

- Personal AI is the only bot permitted to communicate directly with the individual.
- Life Profiling AI is the sole bot with direct access to the Life Profile.
- AI Coordinator is the sole bot with direct access to the specialist network and specialist knowledge interfaces.
- Personal AI, Life Profiling AI and Coordinator may communicate with each other under defined permissions. Coordinator has default visibility of Personal AI–Life Profiling AI exchanges, subject to explicit privacy exclusions.
- Specialists do not initiate or conduct peer communication unless explicitly authorised by the Coordinator for a defined collaboration task.
- Specialists may independently research within their own domain and permitted research tools.
- The knowledge infrastructure must not provide specialists direct access to the Life Profile.

These are application-level access rules and must be enforced by authenticated service identities and API policy.

## 7. Core data flow

1. A specialist or Coordinator submits a scoped research or retrieval request.
2. The API authenticates the caller and checks domain and action permissions.
3. Retrieval returns relevant passages and their provenance, including conflicting material where relevant.
4. Research findings are stored separately from source documents.
5. Evidence assessments link claims to supporting, challenging and contextual sources.
6. Approved changes create a new knowledge version; previous versions remain auditable.
7. All sensitive operations create audit events.

## 8. Research lifecycle

Research supports three modes:
- **Scheduled:** periodic domain reviews with configurable frequency and budget.
- **Question-driven:** targeted research initiated by a user-facing workflow through the authorised bot network.
- **Knowledge-gap:** investigations triggered by missing, stale, contradictory or low-confidence material.

A research task records its scope, domain, requester, status, budget, sources searched, findings, unresolved questions and completion outcome. Research should be deduplicated and resumable.

## 9. Security and operational requirements

- Use managed secrets; never commit credentials or API keys.
- Encrypt data in transit and at rest.
- Use private object buckets and short-lived signed access where appropriate.
- Validate uploads, enforce file-size/type limits and scan files.
- Treat all retrieved documents and web content as untrusted data.
- Apply rate limits, quotas, retry policies and idempotency to background jobs.
- Back up PostgreSQL and object storage; test restoration.
- Keep audit logs for permission changes, ingestion, publication and deletion.
- Support source takedown, retention and deletion workflows.
- Define regional hosting and data residency only after legal and operational review.

## 10. Deployment approach

Begin with a modular monolith: one API application, one worker application, PostgreSQL and object storage. Separate processes may share well-defined modules and contracts. This is easier to operate than premature microservices and can later be split along stable boundaries.

Use separate development, test and production environments. Apply schema changes through versioned migrations. Deploy infrastructure through repeatable configuration rather than manual production changes.

## 11. Stage 1 milestones

1. Repository and architecture baseline.
2. Specialist domain registry and relational schema.
3. Source registration and document metadata.
4. Ingestion and extraction pipeline.
5. Lexical and semantic retrieval.
6. Evidence assessment and version history.
7. Access control, audit, backups and tests.
8. Nutrition end-to-end prototype, then repeatable enablement for all domains.

## 12. Open decisions before production deployment

- Cloud provider and deployment region.
- Hosting budget and expected document volume.
- Database and object-storage provider.
- Authentication/service identity mechanism.
- Approved file types and maximum upload sizes.
- Copyright/licensing policy and source retention rules.
- Embedding model and multilingual requirements.
- Research provider selection and API budgets.
- Backup retention and recovery objectives.
- Operational ownership and incident response.

These decisions must be resolved before production credentials, personal data or large-scale ingestion are introduced.
