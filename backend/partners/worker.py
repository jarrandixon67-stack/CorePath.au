"""Process one durable invitation per invocation; run from an operator-managed worker."""

import json

from psycopg_pool import ConnectionPool

from partners.mail import process_one
from partners.repository import Repository
from partners.settings import get_settings


def main():
    settings = get_settings()
    if not settings.database_url or not settings.worker_subject:
        raise SystemExit("Partner database and registered worker subject are required")
    if not settings.delivery_ready():
        raise SystemExit("Partner email delivery is disabled or not configured")
    with ConnectionPool(settings.database_url, min_size=1, max_size=2) as pool:
        result = process_one(Repository(pool), settings.worker_subject, settings)
        print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
