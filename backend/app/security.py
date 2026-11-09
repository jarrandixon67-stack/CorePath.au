import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


def require_internal_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> str:
    """Protect internal knowledge-management routes.

    This shared-token guard is a development bridge, not the final bot identity
    system. Production must use per-service identities and scoped permissions.
    """
    expected = settings.internal_api_token
    if not expected:
        raise HTTPException(status_code=503, detail="Internal API authentication is not configured")

    supplied = credentials.credentials if credentials else ""
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")

    return "internal"
