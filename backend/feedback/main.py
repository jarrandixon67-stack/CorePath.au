from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from cryptography.fernet import InvalidToken
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg import Error
from psycopg_pool import ConnectionPool, PoolTimeout

from feedback.bot import FeedbackBot, Provider
from feedback.models import (
    ConsentChange,
    FeedbackEntry,
    ImportedReview,
    PromptPreference,
    Resolution,
)
from feedback.repository import Repository
from feedback.settings import get_settings
from partners.repository import Conflict, Denied, Missing
from specialists.models import Capability
from specialists.security import validate_capability


@asynccontextmanager
async def lifespan(app):
    settings = get_settings()
    pool = (
        ConnectionPool(settings.database_url, min_size=1, max_size=4, open=True)
        if settings.database_url
        else None
    )
    if pool:
        pool.wait(timeout=10)
    app.state.feedback_pool = pool
    try:
        yield
    finally:
        if pool:
            pool.close()


app = FastAPI(title="CorePath Feedback Bot", version="0.1.0", lifespan=lifespan)
bearer = HTTPBearer(auto_error=False)


@app.exception_handler(Denied)
async def denied(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=403)


@app.exception_handler(Missing)
async def missing(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=404)


@app.exception_handler(Conflict)
async def conflict(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=409)


@app.exception_handler(InvalidToken)
async def invalid_storage(request, exc):
    return JSONResponse({"detail": "Feedback storage verification failed"}, status_code=503)


@app.exception_handler(Error)
@app.exception_handler(PoolTimeout)
async def unavailable(request, exc):
    return JSONResponse({"detail": "Feedback database unavailable"}, status_code=503)


def repository(request: Request):
    pool = getattr(request.app.state, "feedback_pool", None)
    if not pool:
        raise HTTPException(503, "Feedback database is not configured")
    return Repository(pool, get_settings())


def capability(action):
    def dependency(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        settings = get_settings()
        return validate_capability(
            credentials.credentials if credentials else None,
            public_key=settings.gateway_public_key,
            issuer=settings.gateway_issuer,
            audience=settings.gateway_audience,
            actor="feedback_gateway",
            scope=action,
            purpose="feedback_quality",
            domain="*",
        )

    return dependency


Repo = Annotated[Repository, Depends(repository)]
Submit = Annotated[Capability, Depends(capability("feedback.submit"))]
Own = Annotated[Capability, Depends(capability("feedback.own"))]
Prompt = Annotated[Capability, Depends(capability("feedback.prompt"))]
Read = Annotated[Capability, Depends(capability("feedback.read"))]
Moderate = Annotated[Capability, Depends(capability("feedback.moderate"))]
Import = Annotated[Capability, Depends(capability("feedback.import_reviews"))]
Analyse = Annotated[Capability, Depends(capability("feedback.analyse"))]
Manage = Annotated[Capability, Depends(capability("feedback.targets.manage"))]


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.get("/health/ready")
def ready(repo: Repo):
    if not get_settings().gateway_public_key:
        raise HTTPException(503, "Feedback authentication is not configured")
    with repo.pool.connection() as c:
        c.execute("SELECT 1 FROM feedback_actors LIMIT 1")
    return {"status": "ready"}


@app.post("/v1/targets/{target}")
def register(target: str, cap: Manage, repo: Repo):
    return repo.register_target(cap.subject, target)


@app.post("/v1/targets/{target}/prompt")
def prompt(target: str, cap: Prompt, repo: Repo):
    return repo.prompt(cap.subject, target)


@app.put("/v1/prompt-preference")
def preference(body: PromptPreference, cap: Own, repo: Repo):
    return repo.preference(cap.subject, body.allow_requests)


@app.post("/v1/targets/{target}/feedback", status_code=201)
def submit(target: str, body: FeedbackEntry, cap: Submit, repo: Repo):
    return repo.submit(cap.subject, target, body)


@app.get("/v1/own-feedback")
def own(cap: Own, repo: Repo):
    return repo.own(cap.subject)


@app.put("/v1/own-feedback/{record_id}/analysis-consent")
def consent(record_id: UUID, body: ConsentChange, cap: Own, repo: Repo):
    return repo.change(cap.subject, record_id, allow=body.allow_ai_analysis)


@app.delete("/v1/own-feedback/{record_id}")
def withdraw(record_id: UUID, cap: Own, repo: Repo):
    return repo.change(cap.subject, record_id, delete=True)


@app.post("/v1/targets/{target}/reviews", status_code=201)
def import_review(target: str, body: ImportedReview, cap: Import, repo: Repo):
    return repo.import_review(cap.subject, target, body)


@app.delete("/v1/review-records/{record_id}")
def withdraw_review(record_id: UUID, cap: Moderate, repo: Repo):
    return repo.change(cap.subject, record_id, delete=True, moderate=True)


@app.post("/v1/targets/{target}/analyse")
def analyse(target: str, cap: Analyse, repo: Repo):
    return FeedbackBot(repo, Provider(get_settings())).analyse(cap.subject, target)


@app.get("/v1/targets/{target}/themes")
def themes(target: str, cap: Read, repo: Repo):
    return repo.themes(cap.subject, target)


@app.get("/v1/targets/{target}/records")
def records(target: str, cap: Read, repo: Repo):
    return repo.staff_records(cap.subject, target)


@app.post("/v1/themes/{theme_id}/resolution")
def resolve(theme_id: UUID, body: Resolution, cap: Moderate, repo: Repo):
    return repo.resolve(cap.subject, theme_id, body)
