-- Apply only to the separate private Persy database after its migration.
BEGIN;
CREATE ROLE corepath_persy_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS;
GRANT USAGE ON SCHEMA public TO corepath_persy_runtime;
GRANT SELECT, INSERT ON persy_members, persy_conversations, persy_operations,
    persy_research_proposals, persy_nonces TO corepath_persy_runtime;
GRANT UPDATE (model_processing_enabled, history_enabled, profile_context_enabled,
    communication_style, revision, updated_at) ON persy_members TO corepath_persy_runtime;
GRANT UPDATE (revision) ON persy_conversations TO corepath_persy_runtime;
GRANT DELETE ON persy_conversations TO corepath_persy_runtime;
GRANT UPDATE (state, payload_ciphertext, error_code, completed_at)
    ON persy_operations TO corepath_persy_runtime;
GRANT UPDATE (state, payload_ciphertext, approved_at) ON persy_research_proposals
    TO corepath_persy_runtime;
GRANT INSERT ON persy_audit TO corepath_persy_runtime;
COMMIT;
