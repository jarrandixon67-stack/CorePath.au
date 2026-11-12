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

from specialists.models import StrictModel
from specialists.registry import Domain
from specialists.security import validate_capability


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EXCHANGE_", extra="ignore")
    signing_private_key: str | None = None
    member_public_key: str | None = None
    percy_machine_token: str | None = None
    coordinator_machine_token: str | None = None
    allowed_member_subject: str | None = None
    percy_subject: str = "corepath-persy"
    coordinator_subject: str = "corepath-coordinator"


@lru_cache
def settings():
    return Settings()


class ResearchExchange(StrictModel):
    target: Literal["coordinator"]
    action: Literal["research"]
    request_id: UUID
    member_capability: str


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


def mint(config, *, subject, actor, domain, scope, purpose, audience, request_id, expires):
    now = int(time.time())
    if expires <= now:
        raise HTTPException(401, "Delegation expired")
    if not config.signing_private_key:
        raise HTTPException(503, "Exchange signing identity is not configured")
    try:
        key = load_pem_private_key(
            config.signing_private_key.replace("\\n", "\n").encode(), password=None
        )
        if not isinstance(key, Ed25519PrivateKey):
            raise TypeError("Expected Ed25519")
    except (ValueError, TypeError) as exc:
        raise HTTPException(503, "Exchange signing identity is not configured") from exc
    claims = {
        "iss": "corepath-service-gateway",
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
def percy(body: ResearchExchange, authorization: str | None = Header(default=None)):
    config = settings()
    machine(authorization, config.percy_machine_token)
    member = validate_capability(
        body.member_capability,
        public_key=config.member_public_key,
        issuer="corepath-member-gateway",
        audience="corepath-persy",
        actor="member",
        scope="persy:research",
        purpose="research_approval",
        domain="*",
    )
    if not config.allowed_member_subject or member.subject != config.allowed_member_subject:
        raise HTTPException(403, "Member is not enabled for the live test")
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
