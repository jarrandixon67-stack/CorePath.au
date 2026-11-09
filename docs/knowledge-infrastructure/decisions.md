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
