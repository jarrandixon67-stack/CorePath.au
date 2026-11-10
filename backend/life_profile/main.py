from contextlib import asynccontextmanager
from uuid import UUID

from cryptography.fernet import InvalidToken
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from psycopg import Error as DatabaseError
from psycopg_pool import ConnectionPool, PoolTimeout

from life_profile.bot import LifeProfileBot
from life_profile.models import AnalyseRequest, Consent, Decision
from life_profile.provider import InvalidProposal, OpenAIProvider, ProviderUnavailable
from life_profile.repository import (
    ConsentRequired,
    ProfileConflict,
    ProfileMissing,
    ProfileRepository,
)
from life_profile.security import Caller, require_capability
from life_profile.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    pool = None
    if settings.database_url:
        pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=1,
            max_size=5,
            open=False,
            kwargs={"autocommit": False},
        )
    app.state.profile_pool = pool
    try:
        if pool:
            pool.open()
            pool.wait(timeout=10)
            with pool.connection() as connection:
                if connection.execute(
                    "SELECT to_regclass('public.knowledge_libraries') IS NOT NULL"
                ).fetchone()[0]:
                    raise RuntimeError("Life Profile cannot use the knowledge database.")
        yield
    finally:
        if pool:
            pool.close()


app = FastAPI(
    title="CorePath Life Profiling Service",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def private_responses(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def repository(request: Request) -> ProfileRepository:
    pool = getattr(request.app.state, "profile_pool", None)
    if pool is None:
        raise HTTPException(503, "The separate Life Profile database is not configured")
    try:
        cipher = get_settings().cipher()
    except (ValueError, TypeError) as exc:
        raise HTTPException(503, "Life Profile encryption is not configured") from exc
    return ProfileRepository(pool, cipher)


def bot(repo: ProfileRepository = Depends(repository)) -> LifeProfileBot:  # noqa: B008
    return LifeProfileBot(repo, OpenAIProvider(get_settings()))


@app.exception_handler(ProfileMissing)
async def missing(_request, _exc):
    return JSONResponse({"detail": "Profile or observation not found for this individual"}, 404)


@app.exception_handler(ProfileConflict)
async def conflict(_request, exc):
    return JSONResponse({"detail": str(exc)}, 409)


@app.exception_handler(ConsentRequired)
async def consent_required(_request, _exc):
    return JSONResponse({"detail": "The required individual consent has not been granted"}, 403)


@app.exception_handler(InvalidProposal)
async def invalid_proposal(_request, _exc):
    return JSONResponse({"detail": "The model proposal failed validation; nothing was saved"}, 502)


@app.exception_handler(ProviderUnavailable)
async def model_unavailable(_request, _exc):
    return JSONResponse({"detail": "The model connection is not available; nothing was saved"}, 503)


async def storage_unavailable(_request, _exc):
    return JSONResponse({"detail": "Life Profile storage is unavailable"}, 503)


for error_type in (DatabaseError, PoolTimeout, InvalidToken):
    app.add_exception_handler(error_type, storage_unavailable)


@app.get("/health/live")
def live():
    return {"status": "alive", "service": "life_profile"}


@app.put("/v1/life-profile/consent")
def set_consent(
    consent: Consent,
    caller: Caller = Depends(require_capability("profile:consent", "owner_control")),  # noqa: B008
    repo: ProfileRepository = Depends(repository),  # noqa: B008
):
    return {
        "consent_revision": repo.set_consent(caller.subject, consent, caller.request_id),
        "consent": consent,
    }


@app.post("/v1/life-profile/analyse")
def analyse(
    request: AnalyseRequest,
    caller: Caller = Depends(require_capability("profile:analyse", "profile_analysis")),  # noqa: B008
    service: LifeProfileBot = Depends(bot),  # noqa: B008
):
    return service.analyse(caller.subject, request, caller.request_id)


@app.get("/v1/life-profile/review")
def review(
    caller: Caller = Depends(require_capability("profile:review", "owner_review")),  # noqa: B008
    repo: ProfileRepository = Depends(repository),  # noqa: B008
):
    return repo.snapshot(caller.subject, caller.request_id, owner_review=True)


@app.post("/v1/life-profile/items/{item_id}/decision")
def decide(
    item_id: UUID,
    decision: Decision,
    caller: Caller = Depends(require_capability("profile:decide", "owner_control")),  # noqa: B008
    repo: ProfileRepository = Depends(repository),  # noqa: B008
):
    return repo.decide(caller.subject, item_id, decision, caller.request_id)


@app.get("/v1/life-profile/context")
def approved_context(
    caller: Caller = Depends(require_capability("profile:context", "personalisation")),  # noqa: B008
    repo: ProfileRepository = Depends(repository),  # noqa: B008
):
    return {"approved_understanding": repo.context(caller.subject, caller.request_id)}


@app.delete("/v1/life-profile/items/{item_id}", status_code=204)
def delete_item(
    item_id: UUID,
    caller: Caller = Depends(require_capability("profile:delete", "owner_control")),  # noqa: B008
    repo: ProfileRepository = Depends(repository),  # noqa: B008
):
    repo.delete_item(caller.subject, item_id, caller.request_id)
    return Response(status_code=204)


@app.delete("/v1/life-profile", status_code=204)
def delete_profile(
    caller: Caller = Depends(require_capability("profile:delete", "owner_control")),  # noqa: B008
    repo: ProfileRepository = Depends(repository),  # noqa: B008
):
    repo.delete_profile(caller.subject)
    return Response(status_code=204)
