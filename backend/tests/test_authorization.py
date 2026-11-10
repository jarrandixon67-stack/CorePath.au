from uuid import uuid4

import pytest

from app.authorization import (
    Permission,
    PermissionGrant,
    Principal,
    PrincipalType,
    Role,
    RoleGrant,
    is_authorized,
)


LIBRARY_A = uuid4()
LIBRARY_B = uuid4()


def principal(
    role: Role,
    principal_type: PrincipalType = PrincipalType.HUMAN,
    *,
    active: bool = True,
    library_id=None,
    permissions=frozenset(),
) -> Principal:
    return Principal(
        subject="test-subject",
        principal_type=principal_type,
        active=active,
        role_grants=(
            RoleGrant(
                role=role,
                library_id=library_id,
                permissions=permissions,
            ),
        ),
    )


def test_inactive_principal_is_denied_even_with_founder_role() -> None:
    actor = principal(Role.FOUNDER, active=False)

    assert not is_authorized(actor, Permission.DASHBOARD_READ)


def test_missing_role_grant_is_denied_by_default() -> None:
    actor = Principal("unassigned", PrincipalType.HUMAN, True)

    assert not is_authorized(actor, Permission.LIBRARY_READ, LIBRARY_A)


def test_founder_has_global_knowledge_administration_permissions() -> None:
    actor = principal(Role.FOUNDER)

    assert is_authorized(actor, Permission.SOURCE_VERIFY, LIBRARY_A)
    assert is_authorized(actor, Permission.ROLE_GRANT_EXECUTIVE_ADMINISTRATOR)
    assert is_authorized(actor, Permission.OWNERSHIP_TRANSFER)


def test_founder_does_not_gain_profile_data_or_coordinator_bypass() -> None:
    actor = principal(Role.FOUNDER)

    assert not is_authorized(actor, Permission.PROFILE_DATA_READ)
    assert not is_authorized(actor, Permission.SPECIALIST_COMMUNICATION_BYPASS)


def test_executive_administrator_has_broad_delegated_operations_but_not_reserved_powers() -> None:
    actor = principal(Role.EXECUTIVE_ADMINISTRATOR)

    assert is_authorized(actor, Permission.SOURCE_VERIFY, LIBRARY_A)
    assert is_authorized(actor, Permission.FINDING_PUBLISH, LIBRARY_A)
    assert is_authorized(actor, Permission.USER_MANAGE)
    assert is_authorized(actor, Permission.ROLE_GRANT_RESEARCHER)
    assert not is_authorized(actor, Permission.ROLE_GRANT_EXECUTIVE_ADMINISTRATOR)
    assert not is_authorized(actor, Permission.ROLE_GRANT_FOUNDER)
    assert not is_authorized(actor, Permission.OWNERSHIP_TRANSFER)
    assert not is_authorized(actor, Permission.SPECIALIST_COMMUNICATION_BYPASS)


def test_administrator_requires_explicit_action_and_scope_grants() -> None:
    actor = principal(
        Role.ADMINISTRATOR,
        permissions=frozenset(
            {
                PermissionGrant(Permission.SOURCE_READ, library_id=LIBRARY_A),
                PermissionGrant(Permission.SOURCE_VERIFY),
            }
        ),
    )

    assert is_authorized(actor, Permission.SOURCE_READ, LIBRARY_A)
    assert not is_authorized(actor, Permission.SOURCE_READ, LIBRARY_B)
    assert not is_authorized(actor, Permission.SOURCE_CREATE, LIBRARY_A)
    assert not is_authorized(actor, Permission.SOURCE_VERIFY, LIBRARY_A)


def test_administrator_global_permission_grant_can_cover_all_libraries() -> None:
    actor = principal(
        Role.ADMINISTRATOR,
        permissions=frozenset(
            {PermissionGrant(Permission.LIBRARY_READ)}
        ),
    )

    assert is_authorized(actor, Permission.LIBRARY_READ, LIBRARY_A)
    assert is_authorized(actor, Permission.LIBRARY_READ, LIBRARY_B)


def test_administrator_cannot_be_granted_reserved_permissions() -> None:
    actor = principal(
        Role.ADMINISTRATOR,
        permissions=frozenset(
            {
                PermissionGrant(Permission.OWNERSHIP_TRANSFER),
                PermissionGrant(Permission.ROLE_GRANT_FOUNDER),
                PermissionGrant(Permission.PROFILE_DATA_READ),
            }
        ),
    )

    assert not is_authorized(actor, Permission.OWNERSHIP_TRANSFER)
    assert not is_authorized(actor, Permission.ROLE_GRANT_FOUNDER)
    assert not is_authorized(actor, Permission.PROFILE_DATA_READ)


@pytest.mark.parametrize("role", [Role.SPECIALIST_RESEARCHER, Role.SPECIALIST_AI])
def test_specialist_roles_are_restricted_to_the_assigned_library(role: Role) -> None:
    actor_type = (
        PrincipalType.HUMAN
        if role == Role.SPECIALIST_RESEARCHER
        else PrincipalType.AI_SERVICE
    )
    actor = principal(role, actor_type, library_id=LIBRARY_A)

    assert is_authorized(actor, Permission.LIBRARY_READ, LIBRARY_A)
    assert not is_authorized(actor, Permission.LIBRARY_READ, LIBRARY_B)
    assert not is_authorized(actor, Permission.LIBRARY_READ)


def test_researcher_can_submit_but_cannot_verify_or_publish() -> None:
    actor = principal(Role.SPECIALIST_RESEARCHER, library_id=LIBRARY_A)

    assert is_authorized(actor, Permission.FINDING_SUBMIT, LIBRARY_A)
    assert not is_authorized(actor, Permission.SOURCE_VERIFY, LIBRARY_A)
    assert not is_authorized(actor, Permission.FINDING_PUBLISH, LIBRARY_A)


def test_specialist_ai_cannot_manage_sources_or_verify_records() -> None:
    actor = principal(
        Role.SPECIALIST_AI,
        PrincipalType.AI_SERVICE,
        library_id=LIBRARY_A,
    )

    assert is_authorized(actor, Permission.SOURCE_READ, LIBRARY_A)
    assert is_authorized(actor, Permission.FINDING_SUBMIT, LIBRARY_A)
    assert not is_authorized(actor, Permission.SOURCE_CREATE, LIBRARY_A)
    assert not is_authorized(actor, Permission.SOURCE_VERIFY, LIBRARY_A)


def test_coordinator_can_dispatch_but_cannot_impersonate_specialists() -> None:
    actor = principal(Role.COORDINATOR_AI, PrincipalType.AI_SERVICE)

    assert is_authorized(actor, Permission.RESEARCH_COORDINATE)
    assert is_authorized(actor, Permission.SPECIALIST_TASK_DISPATCH)
    assert not is_authorized(actor, Permission.SOURCE_READ, LIBRARY_A)
    assert not is_authorized(actor, Permission.SPECIALIST_COMMUNICATION_BYPASS)


def test_human_cannot_use_ai_service_role() -> None:
    actor = principal(Role.COORDINATOR_AI, PrincipalType.HUMAN)

    assert not is_authorized(actor, Permission.RESEARCH_COORDINATE)


def test_ai_service_cannot_use_human_administrator_role() -> None:
    actor = principal(
        Role.EXECUTIVE_ADMINISTRATOR,
        PrincipalType.AI_SERVICE,
    )

    assert not is_authorized(actor, Permission.USER_MANAGE)
