import json
from uuid import UUID

from cryptography.fernet import Fernet
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from life_profile.models import Consent, Decision


class ProfileMissing(Exception):
    pass


class ProfileConflict(Exception):
    pass


class ConsentRequired(Exception):
    pass


class ProfileRepository:
    """Only the dedicated Life Profiling process receives this database/key pair."""

    def __init__(self, pool: ConnectionPool, cipher: Fernet):
        self.pool, self.cipher = pool, cipher

    def encrypt(self, value: dict) -> bytes:
        return self.cipher.encrypt(json.dumps(value, ensure_ascii=False).encode())

    def decrypt(self, value: bytes) -> dict:
        return json.loads(self.cipher.decrypt(bytes(value)))

    def audit(self, conn, subject: str, action: str, request_id: str, target_id=None):
        conn.execute(
            """INSERT INTO life_profile_audit (subject, action, target_id, request_id)
               VALUES (%s, %s, %s, %s)""",
            (subject, action, target_id, request_id),
        )

    def _profile(self, conn, subject: str, *, lock: bool = False):
        query = "SELECT * FROM life_profiles WHERE subject = %s" + (" FOR UPDATE" if lock else "")
        row = conn.cursor(row_factory=dict_row).execute(query, (subject,)).fetchone()
        if row is None:
            raise ProfileMissing
        return row, Consent.model_validate(self.decrypt(row["consent_ciphertext"]))

    def _items(self, conn, subject: str) -> list[dict]:
        rows = (
            conn.cursor(row_factory=dict_row)
            .execute(
                "SELECT * FROM life_profile_items WHERE subject = %s ORDER BY created_at, id",
                (subject,),
            )
            .fetchall()
        )
        return [
            {
                "id": str(row["id"]),
                "state": row["state"],
                "version": row["version"],
                "created_at": row["created_at"].isoformat(),
                "updated_at": row["updated_at"].isoformat(),
                **self.decrypt(row["payload_ciphertext"]),
            }
            for row in rows
        ]

    def set_consent(self, subject: str, consent: Consent, request_id: str) -> int:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO life_profiles (subject, consent_ciphertext)
                VALUES (%s, %s)
                ON CONFLICT (subject) DO UPDATE
                SET consent_ciphertext = EXCLUDED.consent_ciphertext,
                    consent_revision = life_profiles.consent_revision + 1,
                    updated_at = now()
                RETURNING consent_revision
                """,
                (subject, self.encrypt(consent.model_dump(mode="json"))),
            ).fetchone()
            self.audit(conn, subject, "consent.update", request_id)
            return row[0]

    def snapshot(self, subject: str, request_id: str, *, owner_review: bool = False) -> dict:
        with self.pool.connection() as conn:
            row, consent = self._profile(conn, subject)
            items = self._items(conn, subject)
            if owner_review:
                self.audit(conn, subject, "profile.owner_review", request_id)
            return {"consent": consent, "consent_revision": row["consent_revision"], "items": items}

    def propose(
        self, subject: str, payloads: list[dict], consent_revision: int, request_id: str
    ) -> list[dict]:
        with self.pool.connection() as conn:
            row, consent = self._profile(conn, subject, lock=True)
            if row["consent_revision"] != consent_revision:
                raise ProfileConflict("Consent changed while the analysis was running.")
            if not consent.analysis_enabled or not consent.external_model_processing:
                raise ConsentRequired
            results = []
            for payload in payloads:
                if payload["category"] not in consent.categories:
                    raise ConsentRequired
                if payload["sensitive"] and not consent.sensitive_observations_enabled:
                    raise ConsentRequired
                item = conn.execute(
                    """INSERT INTO life_profile_items (subject, payload_ciphertext)
                       VALUES (%s, %s) RETURNING id, version""",
                    (subject, self.encrypt(payload)),
                ).fetchone()
                self.audit(conn, subject, "observation.propose", request_id, item[0])
                results.append(
                    {"id": str(item[0]), "version": item[1], "state": "pending", **payload}
                )
            return results

    def decide(self, subject: str, item_id: UUID, decision: Decision, request_id: str) -> dict:
        with self.pool.connection() as conn:
            _, consent = self._profile(conn, subject, lock=True)
            row = (
                conn.cursor(row_factory=dict_row)
                .execute(
                    "SELECT * FROM life_profile_items WHERE id = %s AND subject = %s FOR UPDATE",
                    (item_id, subject),
                )
                .fetchone()
            )
            if row is None:
                raise ProfileMissing
            if row["version"] != decision.expected_version:
                raise ProfileConflict("The observation changed; review the current version first.")
            payload = self.decrypt(row["payload_ciphertext"])
            if decision.action == "correct":
                payload["statement"] = decision.corrected_statement
                payload["user_corrected"] = True
                # A correction can introduce new sensitive information. Do not
                # automatically treat it as safe to send to another AI.
                payload["sensitive"] = True
            if decision.share_with_personal_ai and (
                not consent.personalisation_enabled
                or payload["category"] not in consent.categories
                or (payload["sensitive"] and not consent.sensitive_observations_enabled)
            ):
                raise ConsentRequired
            state = "rejected" if decision.action == "reject" else "accepted"
            payload["shared_with_personal_ai"] = decision.share_with_personal_ai
            payload["understanding_level"] = (
                "confirmed_understanding" if state == "accepted" else payload["understanding_level"]
            )
            conn.execute(
                """INSERT INTO life_profile_item_versions
                   (item_id, version, state, payload_ciphertext) VALUES (%s, %s, %s, %s)""",
                (item_id, row["version"], row["state"], row["payload_ciphertext"]),
            )
            conn.execute(
                """UPDATE life_profile_items SET state = %s, version = version + 1,
                   payload_ciphertext = %s, updated_at = now() WHERE id = %s AND subject = %s""",
                (state, self.encrypt(payload), item_id, subject),
            )
            self.audit(conn, subject, "observation." + decision.action, request_id, item_id)
            return {"id": str(item_id), "version": row["version"] + 1, "state": state, **payload}

    def context(self, subject: str, request_id: str) -> list[dict]:
        with self.pool.connection() as conn:
            _, consent = self._profile(conn, subject, lock=True)
            if not consent.personalisation_enabled:
                raise ConsentRequired
            items = self._items(conn, subject)
            self.audit(conn, subject, "context.personalisation", request_id)
            return [
                {
                    key: item[key]
                    for key in ("id", "statement", "category", "dimensions", "understanding_level")
                }
                for item in items
                if item["state"] == "accepted"
                and item["shared_with_personal_ai"]
                and item["category"] in consent.categories
                and (not item["sensitive"] or consent.sensitive_observations_enabled)
            ]

    def delete_item(self, subject: str, item_id: UUID, request_id: str):
        with self.pool.connection() as conn:
            self._profile(conn, subject, lock=True)
            deleted = conn.execute(
                "DELETE FROM life_profile_items WHERE id = %s AND subject = %s RETURNING id",
                (item_id, subject),
            ).fetchone()
            if deleted is None:
                raise ProfileMissing
            self.audit(conn, subject, "observation.delete", request_id, item_id)

    def delete_profile(self, subject: str):
        with self.pool.connection() as conn:
            # Cascades include encrypted versions, consent, items and audit rows.
            conn.execute("DELETE FROM life_profiles WHERE subject = %s", (subject,))
