# Database migration and deployment procedure

This procedure covers the knowledge-infrastructure foundation in a controlled environment. Hosting, production identity, access enforcement and backup ownership remain open decisions in [implementation status](implementation-status.md).

## Migration runner

From the release checkout's `backend/` directory, with dependencies installed and `DATABASE_URL` exported in the process environment:

```bash
python -m app.migrations --check
python -m app.migrations
python -m app.migrations --check
```

`--check` performs a read-only database transaction. Exit code 0 means up to date, 1 means valid pending migrations, and 2 means a configuration, history or database error. Applying migrations returns 0 on success and 2 on error. The command reads the environment directly; it does not load `.env` automatically. Do not put credentials on the command line or in Git.

The default SQL directory is `database/migrations/` in this checkout. Use `--directory /path/to/release/migrations` for a different layout. The current backend Docker image contains application code only; supply the exact release's migration files separately, for example with a read-only mount and `--directory`. Do not assume an installed wheel includes the repository's SQL files.

The runner:

- Validates unique, consecutive numeric versions starting at 001.
- Records version, filename, SHA-256 checksum and application time in `schema_migrations`.
- Checks all recorded history against the release before applying anything pending.
- Skips applied files on repeat runs; detects missing, renamed or edited applied migrations.
- Serialises runners with a transaction-level PostgreSQL advisory lock and a 30-second lock timeout.
- Applies the entire pending batch and its history in one transaction. A failure rolls back the batch, including the ledger if it was newly created.
- Refuses to adopt an existing schema with untracked tables. It does not erase, recreate or automatically baseline that schema.

SQL files are trusted release code. Keep one outer `BEGIN;` / `COMMIT;` wrapper, which the runner removes before execution. Do not add internal transaction-control commands or non-transactional operations such as `CREATE INDEX CONCURRENTLY`. Applied migrations are immutable; corrections require a new numbered file. The existing six SQL files, including migration 006 from the feature branch, are unchanged.

## Prepare a release

1. Record the exact commit and confirm its full PostgreSQL CI run passed. Include migration, seed, integration-test, lint and format results.
2. Identify the target database and responsible operator. Use a dedicated migration credential for schema changes; keep normal API credentials separately scoped.
3. For a database with existing data, take a backup and prove restoration into an isolated database before scheduling the change. Review compatibility with the current API and the selected PostgreSQL service/version.
4. Run the same release and migration commands against a disposable staging database first. The check must report no pending migrations after application, and a second application must make no changes.

## Apply in the controlled environment

1. Pause competing schema changes and any API writes that could conflict with the planned migration. Advisory locking coordinates migration runners, not ordinary application traffic.
2. Run the preflight check. Exit code 1 is expected when this release has pending files. Exit code 2 requires investigation; do not continue.
3. Run the apply command once, then the read-only check. Record the release commit, command outcome and ledger versions without recording credentials.
4. Start or update the API using the same release. Verify `/health/live`, `/health/ready`, authenticated library access and rejection of missing credentials. Readiness confirms connectivity only; it does not prove role authorisation is implemented.
5. Keep the current administrator prototype private until production identity, sessions and server-enforced action/library permissions are implemented and tested.

## Failure and recovery

A failed pending batch is rolled back. Investigate the database error and compare history with the intended release. Do not disable checksums, remove history rows or change an already applied file to force a pass.

For incompatible changes after a successful commit, use a reviewed forward migration or the tested restore procedure. The runner deliberately has no automatic downgrade or reset command. A previous API release may be restored only when it is compatible with the resulting schema.

## Existing databases without history

The earlier setup instructions ran SQL directly with `psql`. Such a database may contain the full or partial schema without `schema_migrations`. The runner refuses it to avoid claiming work that it did not verify. Preserve the database and have an operator compare its schema and data with the exact historical release, then design and test a separate adoption plan. This change does not provide an automatic baseline or mutate an existing deployment.
