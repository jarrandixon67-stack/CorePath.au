from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from coordinator.settings import Settings, get_settings
from specialists.security import validate_capability

bearer = HTTPBearer(auto_error=False)


def personal_capability(purpose: str, scope: str):
    def dependency(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
        settings: Annotated[Settings, Depends(get_settings)],
    ):
        return validate_capability(
            credentials.credentials if credentials else None,
            public_key=settings.gateway_public_key,
            issuer=settings.gateway_issuer,
            audience=settings.gateway_audience,
            actor="personal_ai",
            scope=scope,
            purpose=purpose,
            domain="*",
        )

    return dependency
