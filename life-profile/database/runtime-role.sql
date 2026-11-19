-- Apply only in the separate Life Profile database.
BEGIN;
CREATE ROLE corepath_profile_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS;
GRANT USAGE ON SCHEMA public TO corepath_profile_runtime;
GRANT SELECT, INSERT, DELETE ON life_profiles, life_profile_items
    TO corepath_profile_runtime;
GRANT UPDATE (consent_ciphertext, consent_revision, updated_at)
    ON life_profiles TO corepath_profile_runtime;
GRANT UPDATE (state, version, payload_ciphertext, updated_at)
    ON life_profile_items TO corepath_profile_runtime;
GRANT INSERT ON life_profile_item_versions, life_profile_audit TO corepath_profile_runtime;
COMMIT;
