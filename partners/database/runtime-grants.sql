-- Apply with psql -v partners_api_role=... -v partners_worker_role=...
-- Both login roles must already exist; the migration owner remains separate.
-- Run in the isolated partner database, never a Life Profile database.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"partners_api_role", :"partners_worker_role";
GRANT SELECT ON partner_actors TO :"partners_api_role", :"partners_worker_role";
-- PostgreSQL locking SELECTs require UPDATE on at least one column. These grants
-- permit row locks, without allowing changes to identities or their permissions.
GRANT UPDATE(last_checked_at) ON partner_actors TO :"partners_api_role", :"partners_worker_role";
GRANT SELECT,INSERT,UPDATE ON partner_businesses,partner_policies,partner_evidence,partner_assessments,partner_contacts,partner_outbox,partner_suppressions,partner_dispatch_nonces TO :"partners_api_role";
GRANT DELETE ON partner_dispatch_nonces TO :"partners_api_role";
GRANT INSERT ON partner_audit TO :"partners_api_role", :"partners_worker_role";
GRANT USAGE ON SEQUENCE partner_audit_id_seq TO :"partners_api_role", :"partners_worker_role";
GRANT SELECT ON partner_businesses,partner_policies,partner_evidence,partner_assessments,partner_contacts,partner_outbox,partner_suppressions TO :"partners_worker_role";
GRANT UPDATE(revision) ON partner_businesses TO :"partners_worker_role";
GRANT UPDATE(last_checked_at) ON partner_policies,partner_contacts TO :"partners_worker_role";
GRANT UPDATE ON partner_outbox TO :"partners_worker_role";
-- The sending worker cannot approve policies, verify evidence/contacts, grant
-- roles, delete suppressions or edit the audit trail. Neither role owns tables.
