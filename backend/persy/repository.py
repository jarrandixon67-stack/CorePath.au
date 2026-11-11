import time
from uuid import uuid4

from psycopg.rows import dict_row

from persy.models import Missing, Privacy, PrivacyChange, PrivacyRequired, ResearchProposal
from persy.policy import POLICY_HASH
from persy.settings import Settings
from persy.vault import Vault, owner_key
from specialists.models import AccessDenied, BudgetExceeded, RunConflict

MODEL_KINDS = ("chat", "research", "profile_analysis")


class Repository:
    def __init__(self, pool, vault: Vault):
        self.pool, self.vault = pool, vault

    def _owner(self, member):
        if member.expires_at <= time.time():
            raise AccessDenied
        return owner_key(member.subject)

    def _lock(self, conn, key):
        conn.execute("SET LOCAL lock_timeout = '5s'")
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 3))", (key,))

    def _member(self, conn, member):
        key = self._owner(member)
        row = (
            conn.cursor(row_factory=dict_row)
            .execute("SELECT * FROM persy_members WHERE owner_key = %s AND is_active", (key,))
            .fetchone()
        )
        if not row:
            raise PrivacyRequired
        return row

    def _nonce(self, conn, key, request_id):
        if conn.execute(
            "SELECT 1 FROM persy_nonces WHERE owner_key = %s AND request_id = %s", (key, request_id)
        ).fetchone():
            raise RunConflict
        conn.execute(
            "INSERT INTO persy_nonces (owner_key, request_id) VALUES (%s, %s)", (key, request_id)
        )

    def _audit(self, conn, key, request_id, action, target=None):
        conn.execute(
            "INSERT INTO persy_audit (owner_key, request_id, action, target_id) VALUES (%s, %s, %s, %s)",
            (key, request_id, action, target),
        )

    def privacy(self, member):
        with self.pool.connection() as conn:
            key = self._owner(member)
            row = (
                conn.cursor(row_factory=dict_row)
                .execute("SELECT * FROM persy_members WHERE owner_key = %s", (key,))
                .fetchone()
            )
            if row and not row["is_active"]:
                raise AccessDenied
            return {
                "revision": row["revision"] if row else 0,
                "privacy": {name: row[name] for name in Privacy.model_fields}
                if row
                else Privacy().model_dump(),
            }

    def set_privacy(self, member, change: PrivacyChange):
        key = self._owner(member)
        with self.pool.connection() as conn:
            self._lock(conn, key)
            row = conn.execute(
                "SELECT revision, is_active FROM persy_members WHERE owner_key = %s", (key,)
            ).fetchone()
            if row and not row[1]:
                raise AccessDenied
            if change.expected_revision != (row[0] if row else 0):
                raise RunConflict
            self._nonce(conn, key, member.request_id)
            conn.execute(
                "INSERT INTO persy_members (owner_key, model_processing_enabled, history_enabled, profile_context_enabled, communication_style) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (owner_key) DO UPDATE SET model_processing_enabled = EXCLUDED.model_processing_enabled, history_enabled = EXCLUDED.history_enabled, profile_context_enabled = EXCLUDED.profile_context_enabled, communication_style = EXCLUDED.communication_style, revision = persy_members.revision + 1, updated_at = now()",
                (
                    key,
                    change.model_processing_enabled,
                    change.history_enabled,
                    change.profile_context_enabled,
                    change.communication_style,
                ),
            )
            if not change.history_enabled:
                conn.execute(
                    "UPDATE persy_operations SET payload_ciphertext = NULL WHERE owner_key = %s",
                    (key,),
                )
            conn.execute(
                "UPDATE persy_research_proposals SET state = 'cancelled', payload_ciphertext = NULL WHERE owner_key = %s AND state IN ('pending', 'running')",
                (key,),
            )
            self._audit(conn, key, member.request_id, "privacy.update")
        return self.privacy(member)

    def create_conversation(self, member, settings: Settings):
        key = self._owner(member)
        with self.pool.connection() as conn:
            self._lock(conn, key)
            self._member(conn, member)
            self._nonce(conn, key, member.request_id)
            if (
                conn.execute(
                    "SELECT count(*) FROM persy_conversations WHERE owner_key = %s", (key,)
                ).fetchone()[0]
                >= settings.max_conversations
            ):
                raise BudgetExceeded
            conversation_id = conn.execute(
                "INSERT INTO persy_conversations (owner_key) VALUES (%s) RETURNING id", (key,)
            ).fetchone()[0]
            self._audit(conn, key, member.request_id, "conversation.create", conversation_id)
            return {"conversation_id": str(conversation_id)}

    def _conversation(self, conn, key, conversation_id):
        row = (
            conn.cursor(row_factory=dict_row)
            .execute(
                "SELECT * FROM persy_conversations WHERE id = %s AND owner_key = %s",
                (conversation_id, key),
            )
            .fetchone()
        )
        if not row:
            raise Missing
        return row

    def begin(self, member, kind, settings: Settings, conversation_id=None, proposal_id=None):
        key = self._owner(member)
        with self.pool.connection() as conn:
            self._lock(conn, key)
            privacy = self._member(conn, member)
            if kind in MODEL_KINDS and not privacy["model_processing_enabled"]:
                raise PrivacyRequired
            conversation = (
                self._conversation(conn, key, conversation_id) if conversation_id else None
            )
            self._nonce(conn, key, member.request_id)
            conn.execute(
                "UPDATE persy_operations SET state = 'failed', completed_at = now(), error_code = 'execution_lease_expired' WHERE owner_key = %s AND state = 'running' AND lease_expires_at <= now()",
                (key,),
            )
            conn.execute(
                "UPDATE persy_research_proposals SET state = 'failed', payload_ciphertext = NULL WHERE owner_key = %s AND state = 'running' AND id IN (SELECT proposal_id FROM persy_operations WHERE owner_key = %s AND state = 'failed')",
                (key, key),
            )
            if kind in MODEL_KINDS:
                recent, running = conn.execute(
                    "SELECT count(*), count(*) FILTER (WHERE state = 'running') FROM persy_operations WHERE owner_key = %s AND kind = ANY(%s) AND created_at > now() - interval '24 hours'",
                    (key, list(MODEL_KINDS)),
                ).fetchone()
                if (
                    recent >= settings.max_operations_per_24h
                    or running >= settings.max_concurrent_operations
                ):
                    raise BudgetExceeded
                if (
                    conversation_id
                    and conn.execute(
                        "SELECT 1 FROM persy_operations WHERE conversation_id = %s AND state = 'running' AND kind IN ('chat', 'research')",
                        (conversation_id,),
                    ).fetchone()
                ):
                    raise RunConflict
            if (
                kind == "chat"
                and conn.execute(
                    "SELECT count(*) FROM persy_operations WHERE conversation_id = %s AND kind = 'chat'",
                    (conversation_id,),
                ).fetchone()[0]
                >= settings.max_turns
            ):
                raise BudgetExceeded
            proposal = None
            if proposal_id:
                row = (
                    conn.cursor(row_factory=dict_row)
                    .execute(
                        "SELECT * FROM persy_research_proposals WHERE id = %s AND owner_key = %s AND conversation_id = %s FOR UPDATE",
                        (proposal_id, key, conversation_id),
                    )
                    .fetchone()
                )
                if not row:
                    raise Missing
                if (
                    row["state"] != "pending"
                    or row["privacy_revision"] != privacy["revision"]
                    or row["expires_at"].timestamp() <= time.time()
                ):
                    raise RunConflict
                proposal = ResearchProposal.model_validate(
                    self.vault.open(row["payload_ciphertext"], key, proposal_id, "proposal")
                )
                conn.execute(
                    "UPDATE persy_research_proposals SET state = 'running', approved_at = now() WHERE id = %s",
                    (proposal_id,),
                )
            operation_id = conn.execute(
                "INSERT INTO persy_operations (owner_key, conversation_id, request_id, kind, privacy_revision, conversation_revision, policy_hash, model_id, lease_expires_at, proposal_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, to_timestamp(%s), %s) RETURNING id",
                (
                    key,
                    conversation_id,
                    member.request_id,
                    kind,
                    privacy["revision"],
                    conversation["revision"] if conversation else None,
                    POLICY_HASH,
                    settings.model if kind == "chat" else None,
                    min(member.expires_at, time.time() + settings.lease_seconds),
                    proposal_id,
                ),
            ).fetchone()[0]
            self._audit(conn, key, member.request_id, kind + ".start", operation_id)
            return operation_id, privacy, proposal

    def _active(self, conn, member, operation_id):
        privacy = self._member(conn, member)
        row = (
            conn.cursor(row_factory=dict_row)
            .execute(
                "SELECT * FROM persy_operations WHERE id = %s AND owner_key = %s AND state = 'running' AND lease_expires_at > clock_timestamp() FOR UPDATE",
                (operation_id, privacy["owner_key"]),
            )
            .fetchone()
        )
        if not row or row["privacy_revision"] != privacy["revision"]:
            raise RunConflict
        if row["kind"] in MODEL_KINDS and not privacy["model_processing_enabled"]:
            raise PrivacyRequired
        if row["conversation_id"]:
            conversation = self._conversation(conn, privacy["owner_key"], row["conversation_id"])
            if conversation["revision"] != row["conversation_revision"]:
                raise RunConflict
        elif row["kind"] in ("chat", "research"):
            raise RunConflict
        return row, privacy

    def check(self, member, operation_id):
        with self.pool.connection() as conn:
            self._active(conn, member, operation_id)

    def finish(
        self,
        member,
        operation_id,
        payload=None,
        proposal: ResearchProposal | None = None,
        settings=None,
    ):
        key = self._owner(member)
        with self.pool.connection() as conn:
            self._lock(conn, key)
            row, privacy = self._active(conn, member, operation_id)
            encrypted = (
                self.vault.seal(payload, key, operation_id, "turn")
                if payload and privacy["history_enabled"] and row["kind"] in ("chat", "research")
                else None
            )
            conn.execute(
                "UPDATE persy_operations SET state = 'completed', payload_ciphertext = %s, completed_at = now() WHERE id = %s",
                (encrypted, operation_id),
            )
            if row["conversation_id"]:
                conn.execute(
                    "UPDATE persy_conversations SET revision = revision + 1 WHERE id = %s",
                    (row["conversation_id"],),
                )
            pending = None
            if proposal:
                proposal_id = uuid4()
                blob = self.vault.seal(
                    proposal.model_dump(mode="json"), key, proposal_id, "proposal"
                )
                conn.execute(
                    "INSERT INTO persy_research_proposals (id, owner_key, conversation_id, privacy_revision, payload_ciphertext, expires_at) VALUES (%s, %s, %s, %s, %s, to_timestamp(%s))",
                    (
                        proposal_id,
                        key,
                        row["conversation_id"],
                        privacy["revision"],
                        blob,
                        time.time() + settings.proposal_seconds,
                    ),
                )
                pending = {
                    "id": str(proposal_id),
                    "review_required": True,
                    **proposal.model_dump(mode="json"),
                }
            if row["proposal_id"]:
                conn.execute(
                    "UPDATE persy_research_proposals SET state = 'completed', payload_ciphertext = NULL WHERE id = %s",
                    (row["proposal_id"],),
                )
            self._audit(conn, key, member.request_id, row["kind"] + ".complete", operation_id)
            return pending

    def fail(self, member, operation_id, code):
        key = owner_key(member.subject)
        with self.pool.connection() as conn:
            row = conn.execute(
                "UPDATE persy_operations SET state = 'failed', payload_ciphertext = NULL, error_code = %s, completed_at = now() WHERE id = %s AND owner_key = %s AND state = 'running' RETURNING proposal_id",
                (code, operation_id, key),
            ).fetchone()
            if row:
                if row[0]:
                    conn.execute(
                        "UPDATE persy_research_proposals SET state = 'failed', payload_ciphertext = NULL WHERE id = %s AND state = 'running'",
                        (row[0],),
                    )
                self._audit(conn, key, member.request_id, "operation.failed", operation_id)

    def history(self, member, conversation_id, *, limit=50):
        key = self._owner(member)
        with self.pool.connection() as conn:
            self._member(conn, member)
            self._conversation(conn, key, conversation_id)
            rows = (
                conn.cursor(row_factory=dict_row)
                .execute(
                    "SELECT id, payload_ciphertext, created_at FROM persy_operations WHERE owner_key = %s AND conversation_id = %s AND state = 'completed' AND payload_ciphertext IS NOT NULL ORDER BY created_at DESC, id DESC LIMIT %s",
                    (key, conversation_id, min(limit, 50)),
                )
                .fetchall()
            )
            return [
                {
                    "turn_id": str(row["id"]),
                    "created_at": row["created_at"].isoformat(),
                    **self.vault.open(row["payload_ciphertext"], key, row["id"], "turn"),
                }
                for row in reversed(rows)
            ]

    def selected_messages(self, member, turn_ids):
        if len(set(turn_ids)) != len(turn_ids):
            raise RunConflict
        key = self._owner(member)
        with self.pool.connection() as conn:
            privacy = self._member(conn, member)
            if not privacy["history_enabled"]:
                raise PrivacyRequired
            messages = []
            for turn_id in turn_ids:
                row = (
                    conn.cursor(row_factory=dict_row)
                    .execute(
                        "SELECT id, conversation_id, payload_ciphertext FROM persy_operations WHERE id = %s AND owner_key = %s AND kind = 'chat' AND state = 'completed' AND payload_ciphertext IS NOT NULL",
                        (turn_id, key),
                    )
                    .fetchone()
                )
                if not row:
                    raise Missing
                value = self.vault.open(row["payload_ciphertext"], key, row["id"], "turn")
                messages.append(
                    {
                        "message_id": str(row["id"]),
                        "conversation_id": str(row["conversation_id"]),
                        "source_type": "conversation",
                        "speaker": "user",
                        "content": value["user_message"],
                    }
                )
            return messages

    def delete_conversation(self, member, conversation_id):
        key = self._owner(member)
        with self.pool.connection() as conn:
            self._lock(conn, key)
            self._member(conn, member)
            self._conversation(conn, key, conversation_id)
            self._nonce(conn, key, member.request_id)
            conn.execute(
                "UPDATE persy_operations SET payload_ciphertext = NULL WHERE conversation_id = %s",
                (conversation_id,),
            )
            conn.execute(
                "UPDATE persy_operations SET state = 'failed', error_code = 'conversation_deleted', completed_at = now() WHERE conversation_id = %s AND state = 'running'",
                (conversation_id,),
            )
            conn.execute(
                "DELETE FROM persy_conversations WHERE id = %s AND owner_key = %s",
                (conversation_id, key),
            )
            self._audit(conn, key, member.request_id, "conversation.delete", conversation_id)

    def conversations(self, member):
        with self.pool.connection() as conn:
            privacy = self._member(conn, member)
            rows = (
                conn.cursor(row_factory=dict_row)
                .execute(
                    "SELECT id, created_at FROM persy_conversations WHERE owner_key = %s ORDER BY created_at DESC, id DESC LIMIT 200",
                    (privacy["owner_key"],),
                )
                .fetchall()
            )
            return [dict(row) for row in rows]
