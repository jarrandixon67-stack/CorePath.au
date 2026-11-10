-- Add a second-in-command human role beneath the founder.
-- The role is global in scope; endpoint permissions will be enforced by the API.

BEGIN;

ALTER TABLE access_role_assignments
    DROP CONSTRAINT access_role_assignments_role_check;

ALTER TABLE access_role_assignments
    ADD CONSTRAINT access_role_assignments_role_check
    CHECK (role IN (
        'founder',
        'executive_administrator',
        'administrator',
        'specialist_researcher',
        'specialist_ai',
        'coordinator_ai'
    ));

ALTER TABLE access_role_assignments
    DROP CONSTRAINT access_role_assignments_check;

ALTER TABLE access_role_assignments
    ADD CONSTRAINT access_role_assignments_check
    CHECK (
        (role IN ('specialist_researcher', 'specialist_ai') AND library_id IS NOT NULL)
        OR
        (role IN (
            'founder',
            'executive_administrator',
            'administrator',
            'coordinator_ai'
        ) AND library_id IS NULL)
    );

CREATE OR REPLACE FUNCTION enforce_access_role_principal_type()
RETURNS trigger
LANGUAGE plpgsql
AS '
DECLARE
    assigned_type TEXT;
BEGIN
    SELECT principal_type INTO assigned_type
    FROM access_principals
    WHERE id = NEW.principal_id;

    IF assigned_type IS NULL THEN
        RAISE EXCEPTION ''Access principal does not exist'';
    END IF;

    IF NEW.role IN (
        ''founder'',
        ''executive_administrator'',
        ''administrator'',
        ''specialist_researcher''
    ) AND assigned_type <> ''human'' THEN
        RAISE EXCEPTION ''Role % requires a human principal'', NEW.role;
    END IF;

    IF NEW.role IN (''specialist_ai'', ''coordinator_ai'')
       AND assigned_type <> ''ai_service'' THEN
        RAISE EXCEPTION ''Role % requires an AI service principal'', NEW.role;
    END IF;

    RETURN NEW;
END;
';

COMMIT;
