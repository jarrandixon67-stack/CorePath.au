-- Identity and role foundations for phased human and AI access.
-- Authentication remains the responsibility of a future OIDC/session gateway.
-- This migration stores principals and grants; it does not create credentials.

BEGIN;

CREATE TABLE access_principals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_subject TEXT NOT NULL UNIQUE,
    principal_type TEXT NOT NULL
        CHECK (principal_type IN ('human', 'ai_service')),
    display_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended', 'revoked')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE access_role_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    principal_id UUID NOT NULL REFERENCES access_principals(id) ON DELETE RESTRICT,
    role TEXT NOT NULL
        CHECK (role IN (
            'founder',
            'administrator',
            'specialist_researcher',
            'specialist_ai',
            'coordinator_ai'
        )),
    library_id UUID REFERENCES knowledge_libraries(id) ON DELETE RESTRICT,
    granted_by UUID REFERENCES access_principals(id) ON DELETE RESTRICT,
    grant_reason TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    CHECK (
        (role IN ('specialist_researcher', 'specialist_ai') AND library_id IS NOT NULL)
        OR
        (role IN ('founder', 'administrator', 'coordinator_ai') AND library_id IS NULL)
    )
);


CREATE FUNCTION enforce_access_role_principal_type()
RETURNS trigger
LANGUAGE plpgsql
AS $
DECLARE
    assigned_type TEXT;
BEGIN
    SELECT principal_type INTO assigned_type
    FROM access_principals
    WHERE id = NEW.principal_id;

    IF assigned_type IS NULL THEN
        RAISE EXCEPTION 'Access principal does not exist';
    END IF;

    IF NEW.role IN ('founder', 'administrator', 'specialist_researcher')
       AND assigned_type <> 'human' THEN
        RAISE EXCEPTION 'Role % requires a human principal', NEW.role;
    END IF;

    IF NEW.role IN ('specialist_ai', 'coordinator_ai')
       AND assigned_type <> 'ai_service' THEN
        RAISE EXCEPTION 'Role % requires an AI service principal', NEW.role;
    END IF;

    RETURN NEW;
END;
$;

CREATE TRIGGER access_role_principal_type_guard
    BEFORE INSERT OR UPDATE OF principal_id, role
    ON access_role_assignments
    FOR EACH ROW
    EXECUTE FUNCTION enforce_access_role_principal_type();

CREATE UNIQUE INDEX access_role_assignments_active_unique
    ON access_role_assignments (
        principal_id,
        role,
        COALESCE(library_id, '00000000-0000-0000-0000-000000000000'::uuid)
    )
    WHERE revoked_at IS NULL;

CREATE INDEX access_role_assignments_principal_idx
    ON access_role_assignments(principal_id)
    WHERE revoked_at IS NULL;

CREATE INDEX access_role_assignments_library_idx
    ON access_role_assignments(library_id)
    WHERE revoked_at IS NULL;

COMMENT ON TABLE access_principals IS
    'Human users and AI services after authentication by the trusted identity gateway.';
COMMENT ON TABLE access_role_assignments IS
    'Role grants. Specialist researcher and specialist AI roles are restricted to one library.';

COMMIT;
