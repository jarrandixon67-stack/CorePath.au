"""Local development storage; production must supply authenticated caller identities.

This is not a public API, encrypted privacy database or multi-tenant deployment.
All methods assume an authenticated trusted application caller; model outputs
must never populate owner/caller IDs or grants.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


class Store:
    def __init__(self, path: str = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS consent (
            owner TEXT PRIMARY KEY, purpose TEXT NOT NULL, enabled INTEGER NOT NULL,
            model_processing INTEGER NOT NULL, sensitive INTEGER NOT NULL,
            categories TEXT NOT NULL, revision INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS observations (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES consent(owner),
            revision INTEGER NOT NULL, category TEXT NOT NULL, statement TEXT NOT NULL,
            kind TEXT NOT NULL, sensitive INTEGER NOT NULL, evidence TEXT NOT NULL,
            state TEXT NOT NULL, share_persy INTEGER NOT NULL DEFAULT 0,
            share_coordinator INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS profile_revision (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1), next_revision INTEGER NOT NULL);
          INSERT OR IGNORE INTO profile_revision
            SELECT 1, coalesce(max(revision),0)+1 FROM consent;
          CREATE TABLE IF NOT EXISTS locations (
            id TEXT PRIMARY KEY, payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS findings (
            id TEXT PRIMARY KEY, domain TEXT NOT NULL, payload TEXT NOT NULL,
            reviewed_by TEXT NOT NULL, reviewed_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS twelve_state (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1), enabled INTEGER NOT NULL,
            generation INTEGER NOT NULL);
          INSERT OR IGNORE INTO twelve_state VALUES (1, 0, 0);
          CREATE TABLE IF NOT EXISTS twelve_reports (
            id TEXT PRIMARY KEY, generation INTEGER NOT NULL, payload TEXT NOT NULL,
            created_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS twelve_report_sources (
            report_id TEXT NOT NULL REFERENCES twelve_reports(id) ON DELETE CASCADE,
            finding_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
            PRIMARY KEY(report_id,finding_id));
        """)

    @contextmanager
    def transaction(self):
        """Lock before reading permissions and hold the lock through acceptance.

        A connection context alone does not start a SQLite transaction until its
        first write. Explicit BEGIN closes the check-then-write race across stores.
        Keep model/network calls outside this short critical section.
        """
        if self.db.in_transaction:
            raise RuntimeError("Use standalone service calls, not nested transactions")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield self.db
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def close(self):
        self.db.close()


def now() -> str:
    return datetime.now(UTC).isoformat()


def identifier() -> str:
    return str(uuid4())


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
