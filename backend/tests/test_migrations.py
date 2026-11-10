import hashlib
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from app.migrations import DEFAULT_DIRECTORY, MigrationError, load_migrations, main, migrate


def write_migration(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(f"BEGIN;\n{body}\nCOMMIT;\n")
    return path


def test_loads_existing_release_without_changing_sql_files():
    migrations = load_migrations(DEFAULT_DIRECTORY)
    assert [m.version for m in migrations] == [1, 2, 3, 4, 5, 6, 7]
    for migration in migrations:
        data = (DEFAULT_DIRECTORY / migration.filename).read_bytes()
        assert migration.checksum == hashlib.sha256(data).hexdigest()
        assert not migration.sql.lstrip().startswith("BEGIN;")
        assert not migration.sql.rstrip().endswith("COMMIT;")


@pytest.mark.parametrize(
    "names",
    [
        ["001_a.sql", "001_b.sql"],
        ["002_a.sql"],
        ["001_a.sql", "003_b.sql"],
        ["not_numbered.sql"],
    ],
)
def test_rejects_invalid_release_order_before_database_access(tmp_path, names):
    for name in names:
        write_migration(tmp_path, name, "SELECT 1;")
    with pytest.raises(MigrationError):
        load_migrations(tmp_path)


@pytest.mark.parametrize("content", [b"SELECT 1;", b"BEGIN; COMMIT;", b"\xff"])
def test_rejects_invalid_sql_file_format(tmp_path, content):
    (tmp_path / "001_bad.sql").write_bytes(content)
    with pytest.raises(MigrationError):
        load_migrations(tmp_path)


def test_missing_database_configuration_is_an_explicit_cli_error(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert main(["--check"]) == 2
    assert "DATABASE_URL must be set" in capsys.readouterr().err


@pytest.fixture
def migration_database():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("requires a configured PostgreSQL service")
    schema = "migration_test_" + uuid4().hex
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            yield connection
        finally:
            connection.execute("SET search_path TO public")
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_existing_migrations_apply_once_and_preserve_seed_counts(migration_database):
    migrations = load_migrations(DEFAULT_DIRECTORY)
    assert len(migrate(migration_database, migrations)) == 7
    assert migrate(migration_database, migrations) == []
    assert migrate(migration_database, migrations, check_only=True) == []
    assert migration_database.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 7
    assert migration_database.execute("SELECT count(*) FROM specialist_domains").fetchone()[0] == 11
    assert (
        migration_database.execute("SELECT count(*) FROM knowledge_libraries").fetchone()[0] == 11
    )


def test_pending_check_does_not_create_history_or_schema(migration_database, tmp_path):
    write_migration(tmp_path, "001_example.sql", "CREATE TABLE example (id INTEGER);")
    pending = migrate(migration_database, load_migrations(tmp_path), check_only=True)
    assert [m.version for m in pending] == [1]
    assert (
        migration_database.execute("SELECT to_regclass('schema_migrations')").fetchone()[0] is None
    )
    assert migration_database.execute("SELECT to_regclass('example')").fetchone()[0] is None


def test_failed_batch_rolls_back_schema_and_history_then_can_retry(migration_database, tmp_path):
    write_migration(tmp_path, "001_example.sql", "CREATE TABLE example (id INTEGER);")
    write_migration(tmp_path, "002_failure.sql", "SELECT 1 / 0;")
    with pytest.raises(psycopg.errors.DivisionByZero):
        migrate(migration_database, load_migrations(tmp_path))
    assert migration_database.execute("SELECT to_regclass('example')").fetchone()[0] is None
    assert (
        migration_database.execute("SELECT to_regclass('schema_migrations')").fetchone()[0] is None
    )
    write_migration(tmp_path, "002_failure.sql", "INSERT INTO example VALUES (1);")
    assert len(migrate(migration_database, load_migrations(tmp_path))) == 2
    assert migration_database.execute("SELECT id FROM example").fetchone()[0] == 1


def test_changed_applied_file_blocks_all_pending_changes(migration_database, tmp_path):
    first = write_migration(tmp_path, "001_example.sql", "CREATE TABLE example (id INTEGER);")
    migrate(migration_database, load_migrations(tmp_path))
    first.write_text(first.read_text().replace("BEGIN;", "BEGIN;\n-- edited after application"))
    write_migration(tmp_path, "002_later.sql", "CREATE TABLE later (id INTEGER);")
    with pytest.raises(MigrationError, match="checksum differs"):
        migrate(migration_database, load_migrations(tmp_path))
    assert migration_database.execute("SELECT to_regclass('later')").fetchone()[0] is None
    assert migration_database.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 1


def test_release_missing_applied_versions_is_rejected(migration_database, tmp_path):
    write_migration(tmp_path, "001_example.sql", "CREATE TABLE example (id INTEGER);")
    second = write_migration(tmp_path, "002_later.sql", "INSERT INTO example VALUES (1);")
    migrate(migration_database, load_migrations(tmp_path))
    second.unlink()
    with pytest.raises(MigrationError, match="missing from this release"):
        migrate(migration_database, load_migrations(tmp_path))
    assert migration_database.execute("SELECT id FROM example").fetchone()[0] == 1


def test_existing_untracked_schema_requires_reviewed_adoption(migration_database, tmp_path):
    migration_database.execute("CREATE TABLE valuable_existing_data (id INTEGER)")
    migration_database.execute("INSERT INTO valuable_existing_data VALUES (42)")
    write_migration(tmp_path, "001_example.sql", "CREATE TABLE example (id INTEGER);")
    with pytest.raises(MigrationError, match="untracked tables"):
        migrate(migration_database, load_migrations(tmp_path))
    assert migration_database.execute("SELECT id FROM valuable_existing_data").fetchone()[0] == 42
    assert (
        migration_database.execute("SELECT to_regclass('schema_migrations')").fetchone()[0] is None
    )
