from psycopg_pool import ConnectionPool

from app.config import Settings


def create_pool(settings: Settings) -> ConnectionPool | None:
    """Create a PostgreSQL pool when DATABASE_URL is configured.

    Returning None allows liveness checks and local API exploration before
    infrastructure credentials have been provisioned. Readiness remains false.
    """
    if not settings.database_url:
        return None

    return ConnectionPool(
        conninfo=settings.database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        open=False,
        kwargs={"autocommit": False},
    )
