"""Encrypted owner journal; only included, current records may inform profiling."""

from datetime import date
from typing import Literal
from uuid import UUID

from psycopg.rows import dict_row
from pydantic import ConfigDict, Field, field_validator

from life_profile.bot import LifeProfileBot
from life_profile.models import AnalyseRequest, Consent, SourceMessage, StrictModel
from life_profile.provider import InvalidProposal, ProviderUnavailable
from life_profile.repository import (
    ConsentRequired,
    ProfileConflict,
    ProfileMissing,
    ProfileRepository,
)


class JournalSettings(StrictModel):
    default_include_in_profile: bool = True
    disclosure_version: Literal[1]
    expected_version: int = Field(ge=0)


class EntryContent(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    title: str = Field(default="", max_length=120)
    content: str = Field(min_length=1, max_length=4000)
    entry_date: date
    include_in_profile: bool | None = None
    disclosure_version: Literal[1]

    @field_validator("content")
    @classmethod
    def meaningful_content(cls, value):
        if not value.strip():
            raise ValueError("Write an entry before saving.")
        return value


class EntryCreate(EntryContent):
    client_reference: UUID


class EntryUpdate(EntryContent):
    expected_version: int = Field(ge=1)
    include_in_profile: bool


class JournalStore:
    def __init__(self, profiles: ProfileRepository):
        self.profiles = profiles

    def _owner(self, conn, subject):
        # Saving a journal does not grant analysis or external processing consent.
        consent = Consent(purpose="Understand my life through reflection")
        conn.execute(
            """INSERT INTO life_profiles(subject, consent_ciphertext) VALUES (%s, %s)
               ON CONFLICT(subject) DO NOTHING""",
            (subject, self.profiles.encrypt(consent.model_dump(mode="json"))),
        )
        self.profiles._profile(conn, subject, lock=True)

    def _settings(self, conn, subject):
        row = (
            conn.cursor(row_factory=dict_row)
            .execute("SELECT * FROM life_profile_journal_settings WHERE subject = %s", (subject,))
            .fetchone()
        )
        if row is None:
            return {"default_include_in_profile": True, "disclosure_version": 1, "version": 0}
        return {**self.profiles.decrypt(row["payload_ciphertext"]), "version": row["version"]}

    def settings(self, subject):
        with self.profiles.pool.connection() as conn:
            return self._settings(conn, subject)

    def set_settings(self, subject, settings: JournalSettings, request_id):
        with self.profiles.pool.connection() as conn:
            self._owner(conn, subject)
            current = self._settings(conn, subject)
            if current["version"] != settings.expected_version:
                raise ProfileConflict("Journal preferences changed. Reload before saving.")
            payload = settings.model_dump(exclude={"expected_version"})
            conn.execute(
                """INSERT INTO life_profile_journal_settings(subject, payload_ciphertext)
                   VALUES (%s, %s) ON CONFLICT(subject) DO UPDATE
                   SET payload_ciphertext = EXCLUDED.payload_ciphertext,
                       version = life_profile_journal_settings.version + 1""",
                (subject, self.profiles.encrypt(payload)),
            )
            self.profiles.audit(conn, subject, "journal.settings", request_id)
            return {**payload, "version": current["version"] + 1}

    def _row(self, conn, subject, entry_id, *, lock=False):
        row = (
            conn.cursor(row_factory=dict_row)
            .execute(
                "SELECT * FROM life_profile_journal_entries WHERE subject = %s AND id = %s"
                + (" FOR UPDATE" if lock else ""),
                (subject, entry_id),
            )
            .fetchone()
        )
        if row is None:
            raise ProfileMissing
        return row

    def _view(self, row):
        return {
            **self.profiles.decrypt(row["payload_ciphertext"]),
            "id": str(row["id"]),
            "version": row["version"],
            "include_in_profile": row["include_in_profile"],
            "analysis_state": row["analysis_state"],
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
        }

    def get(self, subject, entry_id, request_id):
        with self.profiles.pool.connection() as conn:
            row = self._row(conn, subject, entry_id)
            self.profiles.audit(conn, subject, "journal.read", request_id, entry_id)
            return self._view(row)

    def list(self, subject, request_id, before=None):
        with self.profiles.pool.connection() as conn:
            values = [subject]
            cursor = ""
            if before:
                row = self._row(conn, subject, before)
                cursor = " AND (created_at, id) < (%s, %s)"
                values.extend([row["created_at"], before])
            rows = (
                conn.cursor(row_factory=dict_row)
                .execute(
                    "SELECT * FROM life_profile_journal_entries WHERE subject = %s"
                    + cursor
                    + " ORDER BY created_at DESC, id DESC LIMIT 51",
                    values,
                )
                .fetchall()
            )
            entries = []
            for row in rows[:50]:
                entry = self._view(row)
                entry["excerpt"] = entry.pop("content")[:140]
                entries.append(entry)
            # A new owner may have no profile row; do not create one on a read.
            if rows:
                self.profiles.audit(conn, subject, "journal.list", request_id)
            return {
                "entries": entries,
                "next_cursor": str(rows[49]["id"]) if len(rows) > 50 else None,
            }

    @staticmethod
    def _payload(data):
        return data.model_dump(mode="json", include={"title", "content", "entry_date"})

    def create(self, subject, data: EntryCreate, request_id):
        with self.profiles.pool.connection() as conn:
            self._owner(conn, subject)
            deleted = conn.execute(
                """SELECT 1 FROM life_profile_journal_deleted_references
                   WHERE subject=%s AND client_reference=%s""",
                (subject, data.client_reference),
            ).fetchone()
            if deleted:
                raise ProfileConflict("This entry was deleted. Start a new entry to write again.")
            old = (
                conn.cursor(row_factory=dict_row)
                .execute(
                    "SELECT * FROM life_profile_journal_entries WHERE subject=%s AND client_reference=%s",
                    (subject, data.client_reference),
                )
                .fetchone()
            )
            payload = self._payload(data)
            if old:
                if (
                    old["version"] != 1
                    or self.profiles.decrypt(old["payload_ciphertext"]) != payload
                ):
                    raise ProfileConflict(
                        "This save reference already belongs to a different revision."
                    )
                if (
                    data.include_in_profile is not None
                    and data.include_in_profile != old["include_in_profile"]
                ):
                    raise ProfileConflict("This save reference has a different inclusion choice.")
                return self._view(old), False
            include = data.include_in_profile
            if include is None:
                include = self._settings(conn, subject)["default_include_in_profile"]
            row = (
                conn.cursor(row_factory=dict_row)
                .execute(
                    """INSERT INTO life_profile_journal_entries
                   (subject, client_reference, payload_ciphertext, include_in_profile, analysis_state)
                   VALUES (%s, %s, %s, %s, %s) RETURNING *""",
                    (
                        subject,
                        data.client_reference,
                        self.profiles.encrypt(payload),
                        include,
                        "pending" if include else "excluded",
                    ),
                )
                .fetchone()
            )
            self.profiles.audit(conn, subject, "journal.create", request_id, row["id"])
            return self._view(row), True

    def _retract(self, conn, subject, entry_id, request_id):
        rows = conn.execute(
            """DELETE FROM life_profile_items i USING life_profile_journal_observations j
               WHERE i.id=j.item_id AND i.subject=j.subject AND j.subject=%s AND j.entry_id=%s
               RETURNING i.id""",
            (subject, entry_id),
        ).fetchall()
        for row in rows:
            self.profiles.audit(conn, subject, "observation.source_retracted", request_id, row[0])

    def update(self, subject, entry_id, data: EntryUpdate, request_id):
        with self.profiles.pool.connection() as conn:
            self.profiles._profile(conn, subject, lock=True)
            old = self._row(conn, subject, entry_id, lock=True)
            if old["version"] != data.expected_version:
                raise ProfileConflict("This entry changed. Reload before editing.")
            if (
                self.profiles.decrypt(old["payload_ciphertext"]) == self._payload(data)
                and old["include_in_profile"] == data.include_in_profile
            ):
                return self._view(old)
            self._retract(conn, subject, entry_id, request_id)
            row = (
                conn.cursor(row_factory=dict_row)
                .execute(
                    """UPDATE life_profile_journal_entries SET payload_ciphertext=%s,
                   include_in_profile=%s, version=version+1, analysed_version=NULL,
                   analysis_state=%s, updated_at=now() WHERE subject=%s AND id=%s RETURNING *""",
                    (
                        self.profiles.encrypt(self._payload(data)),
                        data.include_in_profile,
                        "pending" if data.include_in_profile else "excluded",
                        subject,
                        entry_id,
                    ),
                )
                .fetchone()
            )
            self.profiles.audit(conn, subject, "journal.update", request_id, entry_id)
            return self._view(row)

    def delete(self, subject, entry_id, expected_version, request_id):
        with self.profiles.pool.connection() as conn:
            self.profiles._profile(conn, subject, lock=True)
            row = self._row(conn, subject, entry_id, lock=True)
            if row["version"] != expected_version:
                raise ProfileConflict("This entry changed. Reload before deleting.")
            self._retract(conn, subject, entry_id, request_id)
            conn.execute(
                """INSERT INTO life_profile_journal_deleted_references(subject, client_reference)
                   VALUES (%s, %s) ON CONFLICT DO NOTHING""",
                (subject, row["client_reference"]),
            )
            conn.execute(
                "DELETE FROM life_profile_journal_entries WHERE subject=%s AND id=%s",
                (subject, entry_id),
            )
            self.profiles.audit(conn, subject, "journal.delete", request_id, entry_id)

    def outcome(self, subject, entry_id, version, state):
        with self.profiles.pool.connection() as conn:
            conn.execute(
                """UPDATE life_profile_journal_entries SET analysis_state=%s
                   WHERE subject=%s AND id=%s AND version=%s AND include_in_profile
                   AND analysed_version IS DISTINCT FROM version""",
                (state, subject, entry_id, version),
            )


class JournalService:
    def __init__(self, store: JournalStore, bot: LifeProfileBot):
        self.store, self.bot = store, bot

    def analyse(self, subject, entry_id, request_id):
        entry = self.store.get(subject, entry_id, request_id)
        if not entry["include_in_profile"] or entry["analysis_state"] == "processed":
            return {"entry": entry}
        try:
            snapshot = self.store.profiles.snapshot(subject, request_id)
            request = AnalyseRequest(
                purpose=snapshot["consent"].purpose,
                messages=[
                    SourceMessage(
                        message_id="journal:" + str(entry_id),
                        conversation_id="journal:" + str(entry_id),
                        source_type="journal_entry",
                        speaker="user",
                        content=entry["content"],
                    )
                ],
            )
            self.bot.analyse(
                subject, request, request_id, journal_source=(entry_id, entry["version"])
            )
        except ConsentRequired:
            self.store.outcome(subject, entry_id, entry["version"], "awaiting_consent")
        except (ProviderUnavailable, InvalidProposal):
            self.store.outcome(subject, entry_id, entry["version"], "unavailable")
        except ProfileConflict:
            # A simultaneous edit/exclusion wins; never persist stale proposals.
            pass
        return {"entry": self.store.get(subject, entry_id, request_id)}
