import secrets
import time
from functools import lru_cache
from typing import Literal
from uuid import UUID

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from fastapi import FastAPI, Header, HTTPException
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.trial_metrics import install_endpoint
from specialists.models import StrictModel
from specialists.registry import Domain
from specialists.security import validate_capability


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EXCHANGE_", extra="ignore")
    signing_private_key: str | None = None
    profile_signing_private_key: str | None = None
    member_public_key: str | None = None
    percy_machine_token: str | None = None
    coordinator_machine_token: str | None = None
    allowed_member_subject: str | None = None
    allowed_member_subjects: str | None = None
    percy_subject: str = "corepath-persy"
    coordinator_subject: str = "corepath-coordinator"


@lru_cache
def settings():
    return Settings()


def member_is_enabled(config: Settings, subject: str) -> bool:
    """Temporary allowlist for the small pilot; authentication remains external."""
    if config.allowed_member_subjects is not None:
        allowed = [part.strip() for part in config.allowed_member_subjects.split(",")]
        if not 1 <= len(allowed) <= 20:
            return False
        if any(not part or len(part) > 200 or part == "*" for part in allowed):
            return False
        if len(set(allowed)) != len(allowed):
            return False
        return subject in allowed
    return bool(config.allowed_member_subject and subject == config.allowed_member_subject)


class ResearchExchange(StrictModel):
    target: Literal["coordinator"]
    action: Literal["research"]
    request_id: UUID
    member_capability: str


class ProfileExchange(StrictModel):
    target: Literal["life_profile"]
    action: Literal[
        "context",
        "review",
        "consent",
        "analyse",
        "decision",
        "delete_item",
        "delete_profile",
    ]
    request_id: UUID
    member_capability: str


# Scope and purpose on the incoming member token, followed by the narrowly
# delegated Life Profile permission. Do not accept caller-supplied scopes.
PROFILE_DELEGATIONS = {
    "context": (
        "persy:chat",
        "conversation_reply",
        "profile:context",
        "personalisation",
    ),
    "review": (
        "persy:profile:review",
        "profile_review",
        "profile:review",
        "owner_review",
    ),
    "consent": (
        "persy:profile:control",
        "profile_control",
        "profile:consent",
        "owner_control",
    ),
    "analyse": (
        "persy:profile:analyse",
        "profile_analysis",
        "profile:analyse",
        "profile_analysis",
    ),
    "decision": (
        "persy:profile:control",
        "profile_control",
        "profile:decide",
        "owner_control",
    ),
    "delete_item": (
        "persy:profile:control",
        "profile_control",
        "profile:delete",
        "owner_control",
    ),
    "delete_profile": (
        "persy:profile:control",
        "profile_control",
        "profile:delete",
        "owner_control",
    ),
}


class DispatchExchange(StrictModel):
    domain: Domain
    purpose: Literal["dispatch"]
    scope: list[Literal["specialist:dispatch"]]
    request_id: UUID


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def private_response(request, call_next):
    # The exchange takes only small capability envelopes, never conversation bodies.
    if request.method == "POST":
        chunks = []
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > 16384:
                from fastapi.responses import JSONResponse

                return JSONResponse({"detail": "Request too large"}, status_code=413)
            chunks.append(chunk)
        request._body = b"".join(chunks)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


def machine(authorization, expected):
    if not expected or len(expected) < 32:
        raise HTTPException(503, "Exchange machine identity is not configured")
    supplied = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
    if not secrets.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(401, "Machine authentication required")


def mint(
    config,
    *,
    subject,
    actor,
    domain,
    scope,
    purpose,
    audience,
    request_id,
    expires,
    issuer="corepath-service-gateway",
    signing_key=None,
):
    now = int(time.time())
    if expires <= now:
        raise HTTPException(401, "Delegation expired")
    signing_key = config.signing_private_key if signing_key is None else signing_key
    if not signing_key:
        raise HTTPException(503, "Exchange signing identity is not configured")
    try:
        key = load_pem_private_key(signing_key.replace("\\n", "\n").encode(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise TypeError("Expected Ed25519")
    except (ValueError, TypeError) as exc:
        raise HTTPException(503, "Exchange signing identity is not configured") from exc
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "actor": actor,
        "domain": domain,
        "scope": [scope],
        "purpose": purpose,
        "jti": str(request_id),
        "iat": now,
        "nbf": now,
        "exp": min(expires, now + 240),
    }
    return {"capability": jwt.encode(claims, key, algorithm="EdDSA")}


@app.get("/health/live")
def live():
    return {"status": "alive", "service": "capability-exchange"}


@app.post("/exchange/percy")
def percy(
    body: ResearchExchange | ProfileExchange,
    authorization: str | None = Header(default=None),
):
    config = settings()
    machine(authorization, config.percy_machine_token)
    if isinstance(body, ProfileExchange):
        (
            member_scope,
            member_purpose,
            profile_scope,
            profile_purpose,
        ) = PROFILE_DELEGATIONS[body.action]
    else:
        member_scope, member_purpose = "persy:research", "research_approval"
    member = validate_capability(
        body.member_capability,
        public_key=config.member_public_key,
        issuer="corepath-member-gateway",
        audience="corepath-persy",
        actor="member",
        scope=member_scope,
        purpose=member_purpose,
        domain="*",
    )
    if not member_is_enabled(config, member.subject):
        raise HTTPException(403, "Member is not enabled for the live test")
    if isinstance(body, ProfileExchange):
        if not config.profile_signing_private_key:
            raise HTTPException(503, "Life Profile signing identity is not configured")
        return mint(
            config,
            subject=member.subject,
            actor="personal_ai",
            domain="*",
            scope=profile_scope,
            purpose=profile_purpose,
            audience="corepath-life-profile",
            request_id=body.request_id,
            expires=member.expires_at,
            issuer="corepath-personal-ai",
            signing_key=config.profile_signing_private_key,
        )
    return mint(
        config,
        subject=config.percy_subject,
        actor="personal_ai",
        domain="*",
        scope="coordinator:research",
        purpose="research_request",
        audience="corepath-coordinator",
        request_id=body.request_id,
        expires=member.expires_at,
    )


@app.post("/exchange/coordinator")
def coordinator(body: DispatchExchange, authorization: str | None = Header(default=None)):
    config = settings()
    machine(authorization, config.coordinator_machine_token)
    if body.scope != ["specialist:dispatch"]:
        raise HTTPException(403, "Only specialist dispatch is permitted")
    return mint(
        config,
        subject=config.coordinator_subject,
        actor="coordinator_ai",
        domain=body.domain.value,
        scope="specialist:dispatch",
        purpose="dispatch",
        audience="corepath-specialists",
        request_id=body.request_id,
        expires=int(time.time()) + 240,
    )


install_endpoint(app, "exchange")
