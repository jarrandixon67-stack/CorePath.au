from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from psycopg import Error as DatabaseError
from psycopg_pool import ConnectionPool, PoolTimeout

from specialists.models import (
    AccessDenied,
    BudgetExceeded,
    Capability,
    InvalidEvidence,
    ProviderUnavailable,
    RunConflict,
    Task,
)
from specialists.provider import OpenAIProvider
from specialists.registry import Domain, catalogue
from specialists.repository import Repository
from specialists.runtime import Runtime
from specialists.security import require_capability
from specialists.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    pool = None
    if settings.database_url:
        pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=5,
            open=False,
            kwargs={"autocommit": False, "options": "-c statement_timeout=5000"},
        )
    app.state.specialist_pool = pool
    try:
        if pool:
            pool.open()
            pool.wait(timeout=10)
            with pool.connection() as conn:
                if conn.execute(
                    "SELECT to_regclass('public.life_profiles') IS NOT NULL"
                ).fetchone()[0]:
                    raise RuntimeError("Specialists cannot use the Life Profile database.")
        yield
    finally:
        if pool:
            pool.close()


app = FastAPI(
    title="CorePath Specialist Network",
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


def repository(request: Request) -> Repository:
    pool = getattr(request.app.state, "specialist_pool", None)
    if pool is None:
        raise HTTPException(503, "The specialist knowledge database is not configured")
    return Repository(pool)


def runtime(repo: Repository = Depends(repository)) -> Runtime:  # noqa: B008
    settings = get_settings()
    return Runtime(repo, OpenAIProvider(settings), settings)


@app.exception_handler(AccessDenied)
async def denied(_request, _exc):
    return JSONResponse(
        {"detail": "The service identity, library or action is not authorised"}, 403
    )


@app.exception_handler(RunConflict)
async def conflict(_request, _exc):
    return JSONResponse(
        {"detail": "The request was already used or its evidence/permission changed"}, 409
    )


@app.exception_handler(BudgetExceeded)
async def budget(_request, _exc):
    return JSONResponse(
        {"detail": "The service's request or concurrent-run limit was reached"}, 429
    )


@app.exception_handler(InvalidEvidence)
async def invalid(_request, _exc):
    return JSONResponse(
        {"detail": "Specialist output failed evidence validation; no findings accepted"}, 502
    )


@app.exception_handler(ProviderUnavailable)
async def unavailable(_request, _exc):
    return JSONResponse({"detail": "The specialist model connection is not available"}, 503)


async def storage_unavailable(_request, _exc):
    return JSONResponse({"detail": "The specialist research store is unavailable"}, 503)


for error_type in (DatabaseError, PoolTimeout):
    app.add_exception_handler(error_type, storage_unavailable)


@app.get("/health/live")
def live():
    return {"status": "alive", "service": "specialists", "specialist_count": 11}


@app.get("/v1/specialists")
def list_specialists(
    caller: Annotated[
        Capability,
        Depends(require_capability("coordinator_ai", "specialist:catalogue", "catalogue")),
    ],
    repo: Repository = Depends(repository),  # noqa: B008
):
    libraries = repo.catalogue(caller)
    settings = get_settings()
    return {
        "specialists": [
            entry
            | {
                "library_state": libraries.get(entry["domain"], "missing"),
                "model_connection_configured": bool(
                    settings.openai_api_key and settings.model_for(Domain(entry["domain"]))
                ),
                "live_model_quality_verified": False,
            }
            for entry in catalogue()
        ]
    }


@app.post("/v1/specialists/{domain}/tasks")
def dispatch(
    domain: Domain,
    task: Task,
    caller: Annotated[
        Capability, Depends(require_capability("coordinator_ai", "specialist:dispatch", "dispatch"))
    ],
    service: Runtime = Depends(runtime),  # noqa: B008
):
    return service.execute(caller, domain, task)


@app.post("/v1/specialists/{domain}/research")
def independent_research(
    domain: Domain,
    task: Task,
    caller: Annotated[
        Capability,
        Depends(require_capability("specialist_ai", "specialist:research", "independent_research")),
    ],
    service: Runtime = Depends(runtime),  # noqa: B008
):
    return service.execute(caller, domain, task)


@app.get("/v1/specialists/{domain}/tasks/{run_id}")
def task_status(
    domain: Domain,
    run_id: UUID,
    caller: Annotated[
        Capability, Depends(require_capability("coordinator_ai", "specialist:read", "task_status"))
    ],
    repo: Repository = Depends(repository),  # noqa: B008
):
    result = repo.read_run(caller, domain, run_id)
    if result is None:
        raise HTTPException(404, "Specialist run not found for this service and discipline")
    return result


@app.get("/v1/specialists/{domain}/research/{run_id}")
def research_status(
    domain: Domain,
    run_id: UUID,
    caller: Annotated[
        Capability,
        Depends(require_capability("specialist_ai", "specialist:read", "research_status")),
    ],
    repo: Repository = Depends(repository),  # noqa: B008
):
    result = repo.read_run(caller, domain, run_id)
    if result is None:
        raise HTTPException(404, "Specialist run not found for this service and discipline")
    return result
