from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, status
from psycopg import OperationalError
from psycopg_pool import PoolTimeout

from app.config import get_settings
from app.database import create_pool
from app.schemas import SourceCreate
from app.security import require_internal_token
from app.source_service import (
    LibraryNotFoundError,
    SourceNotFoundError,
    link_existing_source,
    list_libraries,
    list_library_sources,
    register_library_source,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    pool = create_pool(settings)
    app.state.db_pool = pool

    if pool is not None:
        pool.open()
        pool.wait(timeout=10)

    try:
        yield
    finally:
        if pool is not None:
            pool.close()


app = FastAPI(
    title=get_settings().app_name,
    version="0.1.0",
    description="Shared knowledge infrastructure API for CorePath specialist domains.",
    lifespan=lifespan,
)


def get_database_pool(request: Request):
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database is not configured")
    return pool


@app.get("/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    """Indicates that the API process is running."""
    return {"status": "alive"}


@app.get("/health/ready", tags=["health"])
def readiness(request: Request) -> dict[str, str]:
    """Indicates whether required dependencies are available."""
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database is not configured")

    try:
        with pool.connection() as connection:
            connection.execute("SELECT 1")
    except (OperationalError, PoolTimeout, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc

    return {"status": "ready", "database": "connected"}


@app.get(
    "/v1/libraries",
    tags=["knowledge sources"],
    dependencies=[Depends(require_internal_token)],
)
def get_libraries(pool=Depends(get_database_pool)  # noqa: B008) -> list[dict]:
    """List specialist libraries available to the authenticated internal caller."""
    try:
        return list_libraries(pool)
    except (OperationalError, PoolTimeout, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc


@app.get(
    "/v1/libraries/{library_id}/sources",
    tags=["knowledge sources"],
    dependencies=[Depends(require_internal_token)],
)
def get_library_sources(
    library_id: UUID,
    pool=Depends(get_database_pool),
) -> list[dict]:
    """List registered sources associated with a specialist library."""
    try:
        return list_library_sources(pool, library_id)
    except LibraryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Knowledge library not found") from exc
    except (OperationalError, PoolTimeout, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc


@app.post(
    "/v1/libraries/{library_id}/sources",
    tags=["knowledge sources"],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal_token)],
)
def create_library_source(
    library_id: UUID,
    source: SourceCreate,
    pool=Depends(get_database_pool),
) -> dict:
    """Register source metadata in a specialist library; does not download the source."""
    try:
        return register_library_source(pool, library_id, source)
    except LibraryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Knowledge library not found") from exc
    except (OperationalError, PoolTimeout, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc



@app.put(
    "/v1/libraries/{library_id}/sources/{source_id}",
    tags=["knowledge sources"],
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_internal_token)],
)
def add_existing_source_to_library(
    library_id: UUID,
    source_id: UUID,
    pool=Depends(get_database_pool),
) -> None:
    """Associate an existing shared source record with another specialist library."""
    try:
        link_existing_source(pool, library_id, source_id)
    except LibraryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Knowledge library not found") from exc
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Knowledge source not found") from exc
    except (OperationalError, PoolTimeout, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc
