from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from psycopg import Error as DatabaseError
from psycopg_pool import ConnectionPool, PoolTimeout

from coordinator.models import ResearchRequest
from coordinator.provider import OpenAIProvider
from coordinator.repository import Repository
from coordinator.runtime import Runtime
from coordinator.security import personal_capability
from coordinator.settings import get_settings
from coordinator.transport import HTTPSpecialistClient
from specialists.models import (
    AccessDenied,
    BudgetExceeded,
    Capability,
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
                    "SELECT to_regclass('public.life_profiles') IS NOT NULL"
                ).fetchone()[0]:
                    raise RuntimeError("The Coordinator cannot use the Life Profile database")
        app.state.coordinator_pool = pool
        yield
    finally:
        if pool:
            pool.close()


app = FastAPI(
    title="CorePath Coordinator",
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
    pool = getattr(request.app.state, "coordinator_pool", None)
    if pool is None:
        raise HTTPException(503, "The Coordinator store is not configured")
    return Repository(pool)


def runtime(repo: Annotated[Repository, Depends(repository)]):
    settings = get_settings()
    return Runtime(repo, OpenAIProvider(settings), HTTPSpecialistClient(settings), settings)


def error_handler(status, message):
    async def handler(_request, _exc):
        return JSONResponse({"detail": message}, status_code=status)

    return handler


for error, status, message in (
    (AccessDenied, 403, "The service or coordination permission is not authorised"),
    (RunConflict, 409, "The request was already used or its permission/execution lease changed"),
    (BudgetExceeded, 429, "The configured Coordinator work limit was reached"),
    (InvalidEvidence, 502, "The Coordinator plan failed validation"),
    (ProviderUnavailable, 503, "The Coordinator model or service connection is unavailable"),
    (DatabaseError, 503, "The Coordinator store is unavailable"),
    (PoolTimeout, 503, "The Coordinator store is unavailable"),
):
    app.add_exception_handler(error, error_handler(status, message))


@app.get("/health/live")
def live():
    return {"status": "alive", "service": "coordinator", "live_model_quality_verified": False}


@app.post("/v1/coordinator/research")
def research(
    request: ResearchRequest,
    caller: Annotated[
        Capability, Depends(personal_capability("research_request", "coordinator:research"))
    ],
    service: Annotated[Runtime, Depends(runtime)],
):
    return service.execute(caller, request)


@app.get("/v1/coordinator/research/{run_id}")
def research_status(
    run_id: UUID,
    caller: Annotated[
        Capability, Depends(personal_capability("research_status", "coordinator:read"))
    ],
    repo: Annotated[Repository, Depends(repository)],
):
    result = repo.read(caller, run_id, get_settings())
    if result is None:
        raise HTTPException(404, "Coordinator run not found for this service")
    return result
