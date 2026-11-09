from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from psycopg import OperationalError

from app.config import get_settings
from app.database import create_pool


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
    except (OperationalError, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc

    return {"status": "ready", "database": "connected"}
