from dataclasses import dataclass

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from life_profile.settings import Settings, get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Caller:
    subject: str
    request_id: str


def require_capability(scope: str, purpose: str):
    """Accept only short-lived, signed requests from the trusted Personal AI gateway.

    The gateway must authenticate the individual and authorise the requested
    owner operation before minting a token. Browser identity headers and the
    knowledge API's shared development credential are never trusted here.
    """

    def dependency(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),  # noqa: B008
        settings: Settings = Depends(get_settings),  # noqa: B008
    ) -> Caller:
        if not settings.gateway_public_key:
            raise HTTPException(503, "Life Profile identity verification is not configured")
        try:
            key = load_pem_public_key(settings.gateway_public_key.encode())
            if not isinstance(key, Ed25519PublicKey):
                raise TypeError("Expected Ed25519 public key")
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                503, "Life Profile identity verification is not configured"
            ) from exc
        if credentials is None:
            raise HTTPException(401, "A verified Personal AI capability is required")
        try:
            claims = jwt.decode(
                credentials.credentials,
                key,
                algorithms=["EdDSA"],
                audience=settings.gateway_audience,
                issuer=settings.gateway_issuer,
                leeway=5,
                options={
                    "require": [
                        "sub",
                        "exp",
                        "iat",
                        "nbf",
                        "iss",
                        "aud",
                        "actor",
                        "purpose",
                        "scope",
                        "jti",
                    ]
                },
            )
            if any(type(claims[name]) is not int for name in ("iat", "nbf", "exp")):
                raise ValueError("Invalid token times")
            if claims["exp"] - claims["iat"] > 300 or claims["exp"] <= claims["iat"]:
                raise ValueError("Capability lifetime must be at most five minutes")
            subject, request_id = claims["sub"], claims["jti"]
            if not isinstance(subject, str) or not 1 <= len(subject.strip()) <= 200:
                raise ValueError("Invalid subject")
            if not isinstance(request_id, str) or not 1 <= len(request_id.strip()) <= 100:
                raise ValueError("Invalid request identifier")
            scopes = claims["scope"]
            if not isinstance(scopes, list) or any(not isinstance(s, str) for s in scopes):
                raise ValueError("Invalid scopes")
        except (jwt.PyJWTError, ValueError, TypeError) as exc:
            raise HTTPException(401, "Invalid or expired Personal AI capability") from exc
        if claims["actor"] != "personal_ai" or claims["purpose"] != purpose or scope not in scopes:
            raise HTTPException(403, "This caller, purpose or action is not authorised")
        return Caller(subject, request_id)

    return dependency
