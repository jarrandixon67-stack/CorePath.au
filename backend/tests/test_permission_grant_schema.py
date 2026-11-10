from uuid import uuid4

import psycopg
import pytest

from app.config import get_settings


def test_permission_grants_are_limited_to_human_administrator_roles() -> None:
    database_url = get_settings().database_url
    if not database_url:
        pytest.skip("DATABASE_URL is not configured")

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
            administrator_id = uuid4()
            cursor.execute(
                """
                INSERT INTO access_principals (id, external_subject, principal_type, display_name)
                VALUES (%s, %s, 'human', 'Permission schema test administrator')
                """,
                (administrator_id, f"test-admin-{administrator_id}"),
            )
            administrator_assignment = cursor.execute(
                """
                INSERT INTO access_role_assignments (principal_id, role, grant_reason)
                VALUES (%s, 'administrator', 'Automated permission schema test')
                RETURNING id
                """,
                (administrator_id,),
            ).fetchone()[0]

            cursor.execute(
                """
                INSERT INTO access_permission_grants
                    (role_assignment_id, permission_key, library_id, granted_by, grant_reason)
                VALUES (%s, 'library.source.read', NULL, %s, 'Global read access test')
                """,
                (administrator_assignment, administrator_id),
            )
            assert cursor.execute(
                """
                SELECT count(*) FROM access_permission_grants
                WHERE role_assignment_id = %s AND revoked_at IS NULL
                """,
                (administrator_assignment,),
            ).fetchone()[0] == 1

            researcher_id = uuid4()
            cursor.execute(
                """
                INSERT INTO access_principals (id, external_subject, principal_type, display_name)
                VALUES (%s, %s, 'human', 'Permission schema test researcher')
                """,
                (researcher_id, f"test-researcher-{researcher_id}"),
            )
            library_id = cursor.execute(
                "SELECT id FROM knowledge_libraries ORDER BY name LIMIT 1"
            ).fetchone()[0]
            researcher_assignment = cursor.execute(
                """
                INSERT INTO access_role_assignments
                    (principal_id, role, library_id, grant_reason)
                VALUES (%s, 'specialist_researcher', %s, 'Automated permission schema test')
                RETURNING id
                """,
                (researcher_id, library_id),
            ).fetchone()[0]

            with pytest.raises(psycopg.errors.RaiseException):
                with connection.transaction():
                    cursor.execute(
                        """
                        INSERT INTO access_permission_grants
                            (role_assignment_id, permission_key, granted_by, grant_reason)
                        VALUES (%s, 'library.source.verify', %s, 'Must be rejected')
                        """,
                        (researcher_assignment, administrator_id),
                    )

            with pytest.raises(psycopg.errors.CheckViolation):
                with connection.transaction():
                    cursor.execute(
                        """
                        INSERT INTO access_permission_grants
                            (role_assignment_id, permission_key, granted_by, grant_reason)
                        VALUES (%s, 'platform.ownership.transfer', %s, 'Must be rejected')
                        """,
                        (administrator_assignment, administrator_id),
                    )
