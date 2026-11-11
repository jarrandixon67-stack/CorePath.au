import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from specialists.models import Capability
from specialists.settings import Settings, get_settings

bearer = HTTPBearer(auto_error=False)


def validate_capability(
    token: str | None,
    *,
    public_key: str | None,
    issuer: str,
    audience: str,
    actor: str,
    scope: str,
    purpose: str,
    domain: str,
) -> Capability:
    if not public_key:
        raise HTTPException(503, "Specialist service identity is not configured")
    try:
        key = load_pem_public_key(public_key.encode())
        if not isinstance(key, Ed25519PublicKey):
            raise TypeError("Expected Ed25519 public key")
    except (ValueError, TypeError) as exc:
        raise HTTPException(503, "Specialist service identity is not configured") from exc
    if token is None:
        raise HTTPException(401, "A verified service capability is required")
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["EdDSA"],
            issuer=issuer,
            audience=audience,
            options={
                "require": [
                    "sub",
                    "actor",
                    "domain",
                    "scope",
                    "purpose",
                    "iat",
                    "nbf",
                    "exp",
                    "jti",
                ]
            },
            leeway=5,
        )
        if any(type(claims[k]) is not int for k in ("iat", "nbf", "exp")):
            raise ValueError("Invalid times")
        if not 0 < claims["exp"] - claims["iat"] <= 300:
            raise ValueError("Invalid lifetime")
        if not isinstance(claims["sub"], str) or not 1 <= len(claims["sub"].strip()) <= 200:
            raise ValueError("Invalid service subject")
        if not isinstance(claims["jti"], str) or not 1 <= len(claims["jti"].strip()) <= 100:
            raise ValueError("Invalid request ID")
        if not isinstance(claims["scope"], list) or any(
            not isinstance(s, str) for s in claims["scope"]
        ):
            raise ValueError("Invalid action scopes")
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise HTTPException(401, "Invalid or expired service capability") from exc
    if (
        claims["actor"] != actor
        or claims["purpose"] != purpose
        or scope not in claims["scope"]
        or claims["domain"] != domain
    ):
        raise HTTPException(403, "Caller, purpose, action or specialist scope is not authorised")
    return Capability(claims["sub"], actor, domain, claims["jti"], claims["exp"])


def require_capability(actor: str, scope: str, purpose: str):
    def dependency(
        domain: str = "*",
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),  # noqa: B008
        settings: Settings = Depends(get_settings),  # noqa: B008
    ) -> Capability:
        return validate_capability(
            credentials.credentials if credentials else None,
            public_key=settings.gateway_public_key,
            issuer=settings.gateway_issuer,
            audience=settings.gateway_audience,
            actor=actor,
            scope=scope,
            purpose=purpose,
            domain=domain,
        )

    return dependency
