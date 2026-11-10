"""Deny-by-default authorization policy for CorePath knowledge services.

Authentication must supply a verified Principal. This module does not authenticate
bearer tokens or infer a user's identity from a shared development credential.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID


class PrincipalType(StrEnum):
    HUMAN = "human"
    AI_SERVICE = "ai_service"


class Role(StrEnum):
    FOUNDER = "founder"
    EXECUTIVE_ADMINISTRATOR = "executive_administrator"
    ADMINISTRATOR = "administrator"
    SPECIALIST_RESEARCHER = "specialist_researcher"
    SPECIALIST_AI = "specialist_ai"
    COORDINATOR_AI = "coordinator_ai"


class Permission(StrEnum):
    DASHBOARD_READ = "dashboard.read"
    LIBRARY_READ = "library.read"
    SOURCE_READ = "library.source.read"
    SOURCE_CREATE = "library.source.create"
    SOURCE_EDIT = "library.source.edit"
    SOURCE_VERIFY = "library.source.verify"
    CATEGORY_MANAGE = "library.category.manage"
    FINDING_SUBMIT = "research.finding.submit"
    FINDING_PUBLISH = "research.finding.publish"
    USER_MANAGE = "access.user.manage"
    ROLE_GRANT_ADMINISTRATOR = "access.role.grant.administrator"
    ROLE_GRANT_RESEARCHER = "access.role.grant.researcher"
    ROLE_GRANT_EXECUTIVE_ADMINISTRATOR = "access.role.grant.executive_administrator"
    ROLE_GRANT_FOUNDER = "access.role.grant.founder"
    PLATFORM_SETTINGS_MANAGE = "platform.settings.manage"
    RESEARCH_COORDINATE = "research.coordinate"
    SPECIALIST_TASK_DISPATCH = "specialist.task.dispatch"
    OWNERSHIP_TRANSFER = "platform.ownership.transfer"
    PROFILE_DATA_READ = "profile.data.read"
    SPECIALIST_COMMUNICATION_BYPASS = "specialist.communication.bypass"


@dataclass(frozen=True)
class PermissionGrant:
    permission: Permission
    library_id: UUID | None = None
    active: bool = True


@dataclass(frozen=True)
class RoleGrant:
    role: Role
    library_id: UUID | None = None
    active: bool = True
    permissions: frozenset[PermissionGrant] = field(default_factory=frozenset)


@dataclass(frozen=True)
class Principal:
    subject: str
    principal_type: PrincipalType
    active: bool
    role_grants: tuple[RoleGrant, ...] = ()


COORDINATOR_ONLY_PERMISSIONS = frozenset(
    {Permission.RESEARCH_COORDINATE, Permission.SPECIALIST_TASK_DISPATCH}
)

FOUNDER_PERMISSIONS = frozenset(
    permission
    for permission in Permission
    if permission
    not in {
        Permission.PROFILE_DATA_READ,
        Permission.SPECIALIST_COMMUNICATION_BYPASS,
    }
    and permission not in COORDINATOR_ONLY_PERMISSIONS
)

EXECUTIVE_ADMINISTRATOR_PERMISSIONS = frozenset(
    {
        Permission.DASHBOARD_READ,
        Permission.LIBRARY_READ,
        Permission.SOURCE_READ,
        Permission.SOURCE_CREATE,
        Permission.SOURCE_EDIT,
        Permission.SOURCE_VERIFY,
        Permission.CATEGORY_MANAGE,
        Permission.FINDING_SUBMIT,
        Permission.FINDING_PUBLISH,
        Permission.USER_MANAGE,
        Permission.ROLE_GRANT_ADMINISTRATOR,
        Permission.ROLE_GRANT_RESEARCHER,
        Permission.PLATFORM_SETTINGS_MANAGE,
    }
)

RESEARCHER_PERMISSIONS = frozenset(
    {
        Permission.LIBRARY_READ,
        Permission.SOURCE_READ,
        Permission.SOURCE_CREATE,
        Permission.SOURCE_EDIT,
        Permission.FINDING_SUBMIT,
    }
)

SPECIALIST_AI_PERMISSIONS = frozenset(
    {
        Permission.LIBRARY_READ,
        Permission.SOURCE_READ,
        Permission.FINDING_SUBMIT,
    }
)

COORDINATOR_PERMISSIONS = frozenset(
    {
        Permission.RESEARCH_COORDINATE,
        Permission.SPECIALIST_TASK_DISPATCH,
    }
)

ADMINISTRATOR_GRANTABLE_PERMISSIONS = frozenset(
    {
        Permission.DASHBOARD_READ,
        Permission.LIBRARY_READ,
        Permission.SOURCE_READ,
        Permission.SOURCE_CREATE,
        Permission.SOURCE_EDIT,
        Permission.SOURCE_VERIFY,
        Permission.CATEGORY_MANAGE,
        Permission.FINDING_SUBMIT,
        Permission.FINDING_PUBLISH,
        Permission.USER_MANAGE,
    }
)


def is_authorized(
    principal: Principal,
    permission: Permission,
    library_id: UUID | None = None,
) -> bool:
    """Return whether an active principal has permission in the requested scope.

    A library-scoped grant never authorizes a global request or another library.
    Missing, inactive, mismatched, or unsupported grants are denied.
    """
    if not principal.active:
        return False

    # Profile data belongs to a separately authorised subsystem, not this API.
    # Direct specialist communication must always pass through the Coordinator.
    if permission in {
        Permission.PROFILE_DATA_READ,
        Permission.SPECIALIST_COMMUNICATION_BYPASS,
    }:
        return False

    for grant in principal.role_grants:
        if not grant.active:
            continue

        if grant.role in {Role.SPECIALIST_RESEARCHER, Role.SPECIALIST_AI}:
            if library_id is None or grant.library_id != library_id:
                continue
        elif grant.library_id is not None:
            # Human global roles and the Coordinator cannot be represented as
            # scoped role assignments; administrator actions carry their scopes.
            continue

        role_permissions = {
            (Role.FOUNDER, PrincipalType.HUMAN): FOUNDER_PERMISSIONS,
            (Role.EXECUTIVE_ADMINISTRATOR, PrincipalType.HUMAN): (
                EXECUTIVE_ADMINISTRATOR_PERMISSIONS
            ),
            (Role.SPECIALIST_RESEARCHER, PrincipalType.HUMAN): RESEARCHER_PERMISSIONS,
            (Role.SPECIALIST_AI, PrincipalType.AI_SERVICE): SPECIALIST_AI_PERMISSIONS,
            (Role.COORDINATOR_AI, PrincipalType.AI_SERVICE): COORDINATOR_PERMISSIONS,
        }.get((grant.role, principal.principal_type), frozenset())

        if permission in role_permissions:
            return True

        if grant.role == Role.ADMINISTRATOR and principal.principal_type == PrincipalType.HUMAN:
            for permission_grant in grant.permissions:
                if (
                    permission_grant.active
                    and permission_grant.permission == permission
                    and (
                        permission_grant.library_id is None
                        or permission_grant.library_id == library_id
                    )
                    and permission in ADMINISTRATOR_GRANTABLE_PERMISSIONS
                ):
                    return True

    return False
