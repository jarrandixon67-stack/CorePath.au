-- Operator-run template for the KNOWLEDGE database, after migrations 001-007.
-- This NOLOGIN group owns no objects and cannot edit sources, grants or accepted findings.
-- Provision a separate LOGIN account through trusted infrastructure; grant it this role.
-- Do not reuse the schema owner, migration account, a superuser or profile credentials.
BEGIN;
CREATE ROLE corepath_specialist_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS;
GRANT USAGE ON SCHEMA public TO corepath_specialist_runtime;
GRANT SELECT ON specialist_domains, knowledge_libraries, service_identities,
    access_permissions, knowledge_sources, source_library_links,
    knowledge_documents, document_sections TO corepath_specialist_runtime;
GRANT SELECT, INSERT ON specialist_runs TO corepath_specialist_runtime;
GRANT UPDATE (state, result, error_code, completed_at) ON specialist_runs
    TO corepath_specialist_runtime;
GRANT INSERT ON audit_events TO corepath_specialist_runtime;
COMMIT;
