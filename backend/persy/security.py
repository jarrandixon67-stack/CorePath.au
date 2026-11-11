from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from persy.settings import Settings, get_settings
from specialists.security import validate_capability

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Member:
    subject: str
    request_id: str
    expires_at: int
    assertion: str = field(repr=False)


def member_capability(scope, purpose):
    def dependency(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
        settings: Annotated[Settings, Depends(get_settings)],
    ):
        token = credentials.credentials if credentials else None
        caller = validate_capability(
            token,
            public_key=settings.gateway_public_key,
            issuer=settings.gateway_issuer,
            audience=settings.gateway_audience,
            actor="member",
            scope=scope,
            purpose=purpose,
            domain="*",
        )
        return Member(caller.subject, caller.request_id, caller.expires_at, token)

    return dependency
