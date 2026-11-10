"""Versioned PostgreSQL migrations, explicitly run from a release checkout."""

import argparse
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg

DEFAULT_DIRECTORY = Path(__file__).resolve().parents[2] / "database" / "migrations"
MIGRATION_LOCK = 0x434F524550415448  # Stable shared lock for CorePath migration runners.
FILENAME = re.compile(r"(?P<version>[0-9]{3,})_[a-z0-9_]+\.sql\Z")
TRANSACTION = re.compile(
    r"\A(?:\s|--[^\n]*(?:\n|$))*BEGIN\s*;(?P<body>.*)COMMIT\s*;\s*\Z",
    re.IGNORECASE | re.DOTALL,
)


class MigrationError(Exception):
    """A release cannot safely be applied to the current database."""


@dataclass(frozen=True)
class Migration:
    version: int
    filename: str
    checksum: str
    sql: str


def load_migrations(directory: Path) -> list[Migration]:
    """Validate the release's ordered SQL files before connecting to PostgreSQL."""
    if not directory.is_dir():
        raise MigrationError(
            "Migration directory is missing; use a release checkout or --directory."
        )

    migrations = []
    for path in sorted(directory.glob("*.sql")):
        match = FILENAME.fullmatch(path.name)
        if match is None:
            raise MigrationError(f"Invalid migration filename: {path.name}")
        data = path.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MigrationError(f"Migration must be UTF-8: {path.name}") from exc
        transaction = TRANSACTION.fullmatch(text)
        if transaction is None or not transaction["body"].strip():
            raise MigrationError(f"Expected one outer BEGIN/COMMIT wrapper: {path.name}")
        migrations.append(
            Migration(
                version=int(match["version"]),
                filename=path.name,
                checksum=hashlib.sha256(data).hexdigest(),
                sql=transaction["body"],
            )
        )

    migrations.sort(key=lambda migration: migration.version)
    if not migrations:
        raise MigrationError("No SQL migrations found.")
    if [m.version for m in migrations] != list(range(1, len(migrations) + 1)):
        raise MigrationError("Migration versions must be unique and consecutive, starting at 001.")
    return migrations


def migrate(
    connection: psycopg.Connection,
    migrations: list[Migration],
    *,
    check_only: bool = False,
) -> list[Migration]:
    """Apply a pending batch and its history atomically, or check without writes.

    Existing SQL wrappers are removed so the runner owns the release's batch
    transaction. The original files and checksums remain intact.
    A failed batch rolls back every pending migration and its ledger entries.
    """
    if not connection.autocommit:
        raise MigrationError("The migration connection must use autocommit=True.")

    with connection.transaction():
        if check_only:
            connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL lock_timeout = '30s'")
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK,))

        has_history = connection.execute(
            "SELECT to_regclass('schema_migrations') IS NOT NULL"
        ).fetchone()[0]
        history = (
            connection.execute(
                "SELECT version, filename, checksum FROM schema_migrations ORDER BY version"
            ).fetchall()
            if has_history
            else []
        )

        if not history:
            existing = connection.execute(
                """
                SELECT tablename FROM pg_tables
                WHERE schemaname = current_schema() AND tablename <> 'schema_migrations'
                LIMIT 1
                """
            ).fetchone()
            if existing is not None:
                raise MigrationError(
                    "Existing schema has untracked tables. Use a reviewed adoption procedure; "
                    "this runner will not baseline, drop or recreate them."
                )

        if len(history) > len(migrations):
            raise MigrationError("Database contains migrations missing from this release.")
        for row, migration in zip(history, migrations, strict=False):
            if tuple(row) != (migration.version, migration.filename, migration.checksum):
                raise MigrationError(
                    f"Migration history or checksum differs at version {migration.version:03d}. "
                    "Restore the original release files; do not edit applied migrations."
                )

        pending = migrations[len(history) :]
        if check_only or not pending:
            return pending

        if not has_history:
            connection.execute(
                """
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY CHECK (version > 0),
                    filename TEXT NOT NULL UNIQUE,
                    checksum CHAR(64) NOT NULL CHECK (checksum ~ '^[a-f0-9]{64}$'),
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        for migration in pending:
            connection.execute(migration.sql, prepare=False)
            connection.execute(
                "INSERT INTO schema_migrations (version, filename, checksum) VALUES (%s, %s, %s)",
                (migration.version, migration.filename, migration.checksum),
            )
        return pending


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    parser.add_argument(
        "--check", action="store_true", help="Read-only check; exit 1 if migrations are pending."
    )
    args = parser.parse_args(argv)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL must be set in the process environment.", file=sys.stderr)
        return 2

    try:
        migrations = load_migrations(args.directory)
        with psycopg.connect(database_url, autocommit=True, connect_timeout=10) as connection:
            pending = migrate(connection, migrations, check_only=args.check)
    except (MigrationError, OSError) as exc:
        print(f"Migration error: {exc}", file=sys.stderr)
        return 2
    except psycopg.Error as exc:
        # Connection strings must not appear in command output or CI logs.
        reason = exc.diag.message_primary or type(exc).__name__
        print(f"Database migration failed: {reason}", file=sys.stderr)
        return 2

    if not pending:
        print("Database schema is up to date.")
        return 0
    label = "Pending" if args.check else "Applied"
    for migration in pending:
        print(f"{label}: {migration.filename}")
    return 1 if args.check else 0


if __name__ == "__main__":
    raise SystemExit(main())
