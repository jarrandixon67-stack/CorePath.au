from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from cryptography.fernet import InvalidToken
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from psycopg import Error as DatabaseError
from psycopg_pool import ConnectionPool, PoolTimeout

from life_profile.models import Consent, Decision
from persy.membership import base_membership
from persy.models import Approval, Message, Missing, PrivacyChange, PrivacyRequired, ProfileAnalysis
from persy.provider import OpenAIProvider
from persy.repository import Repository
from persy.runtime import Runtime
from persy.security import Member, member_capability
from persy.services import Services
from persy.settings import get_settings
from persy.vault import Vault
from specialists.models import (
    AccessDenied,
    BudgetExceeded,
    InvalidEvidence,
    ProviderUnavailable,
    RunConflict,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    pool = None
    try:
        if settings.database_url:
            pool = ConnectionPool(
                settings.database_url,
                min_size=1,
                max_size=5,
                open=False,
                kwargs={"autocommit": False, "options": "-c statement_timeout=5000"},
            )
            pool.open()
            pool.wait(timeout=10)
            with pool.connection() as conn:
                if conn.execute(
                    "SELECT to_regclass('public.life_profiles') IS NOT NULL OR to_regclass('public.knowledge_libraries') IS NOT NULL"
                ).fetchone()[0]:
                    raise RuntimeError("Persy requires its own private conversation database")
            settings.cipher()
        app.state.persy_pool = pool
        yield
    finally:
        if pool:
            pool.close()


app = FastAPI(
    title="CorePath Persy Personal AI",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def private_responses(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def repository(request: Request):
    pool = getattr(request.app.state, "persy_pool", None)
    if pool is None:
        raise HTTPException(503, "Persy's private store is not configured")
    try:
        vault = Vault(get_settings().cipher())
    except (ValueError, TypeError) as exc:
        raise HTTPException(503, "Persy encryption is not configured") from exc
    return Repository(pool, vault)


def runtime(repo: Annotated[Repository, Depends(repository)]):
    settings = get_settings()
    return Runtime(repo, OpenAIProvider(settings), Services(settings), settings)


def handler(status, message):
    async def respond(_request, _exc):
        return JSONResponse({"detail": message}, status_code=status)

    return respond


for error, status, message in (
    (Missing, 404, "Profile, conversation, proposal or selected message not found for this member"),
    (PrivacyRequired, 403, "The required member privacy permission has not been granted"),
    (AccessDenied, 403, "The member or capability is no longer authorised"),
    (RunConflict, 409, "This request was used or its privacy, conversation or proposal changed"),
    (BudgetExceeded, 429, "Persy's configured operation limit was reached"),
    (InvalidEvidence, 502, "The response failed validation; no answer was accepted"),
    (ProviderUnavailable, 503, "The model or connected CorePath service is unavailable"),
    (InvalidToken, 503, "Persy's encrypted store is unavailable"),
    (DatabaseError, 503, "Persy's private store is unavailable"),
    (PoolTimeout, 503, "Persy's private store is unavailable"),
):
    app.add_exception_handler(error, handler(status, message))


OwnerControl = Annotated[Member, Depends(member_capability("persy:privacy", "owner_control"))]
Conversations = Annotated[
    Member, Depends(member_capability("persy:conversations", "conversation_control"))
]
Read = Annotated[Member, Depends(member_capability("persy:read", "conversation_review"))]
ProfileControl = Annotated[
    Member, Depends(member_capability("persy:profile:control", "profile_control"))
]
Repo = Annotated[Repository, Depends(repository)]
Service = Annotated[Runtime, Depends(runtime)]


@app.get("/health/live")
def live():
    return {
        "status": "alive",
        "service": "persy",
        "name": "Persy",
        "live_model_quality_verified": False,
    }


@app.get("/v1/persy/membership")
def membership():
    return base_membership()


@app.get("/v1/persy/privacy")
def privacy(member: OwnerControl, repo: Repo):
    return repo.privacy(member)


@app.put("/v1/persy/privacy")
def set_privacy(change: PrivacyChange, member: OwnerControl, repo: Repo):
    return repo.set_privacy(member, change)


@app.post("/v1/persy/conversations")
def create_conversation(member: Conversations, repo: Repo):
    return repo.create_conversation(member, get_settings())


@app.get("/v1/persy/conversations")
def list_conversations(member: Read, repo: Repo):
    return {"conversations": repo.conversations(member)}


@app.get("/v1/persy/conversations/{conversation_id}")
def history(conversation_id: UUID, member: Read, repo: Repo):
    return {
        "turns": repo.history(member, conversation_id),
        "window": "most_recent_50_retained_turns",
    }


@app.delete("/v1/persy/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: UUID, member: Conversations, repo: Repo):
    repo.delete_conversation(member, conversation_id)
    return Response(status_code=204)


@app.post("/v1/persy/conversations/{conversation_id}/messages")
def chat(
    conversation_id: UUID,
    message: Message,
    member: Annotated[Member, Depends(member_capability("persy:chat", "conversation_reply"))],
    service: Service,
):
    return service.chat(member, conversation_id, message)


@app.post("/v1/persy/conversations/{conversation_id}/research/{proposal_id}")
def approve_research(
    conversation_id: UUID,
    proposal_id: UUID,
    approval: Approval,
    member: Annotated[Member, Depends(member_capability("persy:research", "research_approval"))],
    service: Service,
):
    return service.research(member, conversation_id, proposal_id)


@app.get("/v1/persy/profile")
def review_profile(
    member: Annotated[Member, Depends(member_capability("persy:profile:review", "profile_review"))],
    service: Service,
):
    return service.profile_action(member, "review")


@app.put("/v1/persy/profile/consent")
def profile_consent(consent: Consent, member: ProfileControl, service: Service):
    return service.profile_action(member, "consent", consent.model_dump(mode="json"))


@app.post("/v1/persy/profile/analyse")
def analyse_profile(
    analysis: ProfileAnalysis,
    member: Annotated[
        Member, Depends(member_capability("persy:profile:analyse", "profile_analysis"))
    ],
    service: Service,
):
    return service.profile_action(member, "analyse", analysis=analysis)


@app.post("/v1/persy/profile/items/{item_id}/decision")
def decide_profile(item_id: UUID, decision: Decision, member: ProfileControl, service: Service):
    return service.profile_action(member, "decision", decision.model_dump(mode="json"), item_id)


@app.delete("/v1/persy/profile/items/{item_id}", status_code=204)
def delete_profile_item(item_id: UUID, member: ProfileControl, service: Service):
    service.profile_action(member, "delete_item", item_id=item_id)
    return Response(status_code=204)


@app.delete("/v1/persy/profile", status_code=204)
def delete_profile(member: ProfileControl, service: Service):
    service.profile_action(member, "delete_profile")
    return Response(status_code=204)
