-- Persist explicit, revocable action permissions for delegated administrators.
-- Founder, Executive Administrator and specialist roles use the policy engine's
-- role defaults; this table only adds narrower permissions to human administrators.

BEGIN;

CREATE TABLE access_permission_grants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_assignment_id UUID NOT NULL
        REFERENCES access_role_assignments(id) ON DELETE RESTRICT,
    permission_key TEXT NOT NULL
        CHECK (permission_key IN (
            'dashboard.read',
            'library.read',
            'library.source.read',
            'library.source.create',
            'library.source.edit',
            'library.source.verify',
            'library.category.manage',
            'research.finding.submit',
            'research.finding.publish',
            'access.user.manage'
        )),
    library_id UUID REFERENCES knowledge_libraries(id) ON DELETE RESTRICT,
    granted_by UUID REFERENCES access_principals(id) ON DELETE RESTRICT,
    grant_reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    CHECK (length(trim(grant_reason)) > 0)
);

CREATE UNIQUE INDEX access_permission_grants_active_unique
    ON access_permission_grants (
        role_assignment_id,
        permission_key,
        COALESCE(library_id, '00000000-0000-0000-0000-000000000000'::uuid)
    )
    WHERE revoked_at IS NULL;

CREATE INDEX access_permission_grants_assignment_idx
    ON access_permission_grants(role_assignment_id)
    WHERE revoked_at IS NULL;

CREATE FUNCTION enforce_administrator_permission_grant()
RETURNS trigger
LANGUAGE plpgsql
AS '
DECLARE
    assigned_role TEXT;
    assigned_status TEXT;
    assigned_type TEXT;
BEGIN
    SELECT assignment.role, principal.status, principal.principal_type
      INTO assigned_role, assigned_status, assigned_type
    FROM access_role_assignments assignment
    JOIN access_principals principal ON principal.id = assignment.principal_id
    WHERE assignment.id = NEW.role_assignment_id
      AND assignment.revoked_at IS NULL;

    IF assigned_role IS NULL THEN
        RAISE EXCEPTION ''Active role assignment does not exist'';
    END IF;

    IF assigned_role <> ''administrator'' OR assigned_type <> ''human''
       OR assigned_status <> ''active'' THEN
        RAISE EXCEPTION ''Explicit permission grants are only allowed for active human administrators'';
    END IF;

    RETURN NEW;
END;
';

CREATE TRIGGER access_permission_grant_guard
    BEFORE INSERT OR UPDATE OF role_assignment_id, permission_key
    ON access_permission_grants
    FOR EACH ROW
    EXECUTE FUNCTION enforce_administrator_permission_grant();

COMMENT ON TABLE access_permission_grants IS
    'Explicit, revocable action permissions for human administrator role assignments.';

COMMIT;
