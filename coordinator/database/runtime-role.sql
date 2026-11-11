-- Operator-run template for the KNOWLEDGE database after migration 008.
-- Separate runtime login, no schema ownership, no model signing key.
BEGIN;
CREATE ROLE corepath_coordinator_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS;
GRANT USAGE ON SCHEMA public TO corepath_coordinator_runtime;
GRANT SELECT ON service_identities, access_permissions, specialist_domains
    TO corepath_coordinator_runtime;
GRANT SELECT, INSERT ON coordinator_runs, coordinator_tasks TO corepath_coordinator_runtime;
GRANT UPDATE (state, plan, report, error_code, calls_used, completed_at)
    ON coordinator_runs TO corepath_coordinator_runtime;
GRANT UPDATE (state, result, specialist_run_id, error_code, completed_at)
    ON coordinator_tasks TO corepath_coordinator_runtime;
GRANT INSERT ON audit_events TO corepath_coordinator_runtime;
COMMIT;
