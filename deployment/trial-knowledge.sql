-- Run as the operator on the dedicated trial knowledge database after migration 008.
-- Supply the agreed end timestamp with psql -v trial_end='YYYY-MM-DD HH:MM:SS+00'.
BEGIN;
INSERT INTO service_identities (service_key, display_name, service_role)
VALUES ('corepath-persy', 'Percy', 'personal_ai'),
       ('corepath-coordinator', 'CorePath Coordinator', 'coordinator')
ON CONFLICT (service_key) DO NOTHING;

-- A NULL library is necessary only for the Coordinator's admission check.
INSERT INTO access_permissions (service_identity_id, action, granted_by, expires_at)
SELECT i.id, 'coordinate', 'trial-operator', :'trial_end'::timestamptz
FROM service_identities i
WHERE i.service_key = 'corepath-persy' AND i.service_role = 'personal_ai'
  AND NOT EXISTS (
    SELECT 1 FROM access_permissions p
    WHERE p.service_identity_id = i.id AND p.action = 'coordinate'
      AND p.library_id IS NULL
  );

INSERT INTO access_permissions (service_identity_id, library_id, action, granted_by, expires_at)
SELECT i.id, l.id, a.action, 'trial-operator', :'trial_end'::timestamptz
FROM service_identities i
CROSS JOIN knowledge_libraries l
CROSS JOIN (VALUES ('research'), ('retrieve')) a(action)
WHERE i.service_key = 'corepath-coordinator' AND i.service_role = 'coordinator'
ON CONFLICT (service_identity_id, library_id, action) DO NOTHING;
COMMIT;
