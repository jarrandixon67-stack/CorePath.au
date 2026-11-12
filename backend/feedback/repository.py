import hashlib
import hmac
import json
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from psycopg.rows import dict_row

from partners.repository import Conflict, Denied, Missing
from persy.vault import Vault

OWNER_ACTIONS = {"feedback.submit", "feedback.own", "feedback.prompt"}
STAFF_ACTIONS = {
    "feedback.read",
    "feedback.moderate",
    "feedback.import_reviews",
    "feedback.targets.manage",
}
ANALYSE = "feedback.analyse"


class Repository:
    def __init__(self, pool, settings):
        if not settings.encryption_key or not settings.owner_hash_key:
            raise Conflict("Feedback encryption and owner hashing are not configured")
        self.pool, self.settings = pool, settings
        self.cipher = Fernet(settings.encryption_key.encode())
        self.vault = Vault(self.cipher)

    def owner_key(self, subject):
        return hmac.new(
            self.settings.owner_hash_key.encode(), subject.encode(), hashlib.sha256
        ).hexdigest()

    def seal_record(self, value, owner, record_id, target, kind):
        return self.vault.seal(value, owner, record_id, "feedback:" + target + ":" + kind)

    def record(self, row):
        value = self.vault.open(
            row["payload"],
            row["owner_key"],
            row["id"],
            "feedback:" + row["target"] + ":" + row["source_kind"],
        )
        if row["source_kind"] == "member" and value.get("allow_ai_analysis") != row.get(
            "ai_allowed", True
        ):
            raise InvalidToken("Feedback consent binding did not match")
        return value

    def seal_theme(self, value, record_id, target):
        return self.vault.seal(value, target, record_id, "feedback_theme")

    def theme(self, row):
        return self.vault.open(row["payload"], row["target"], row["id"], "feedback_theme")

    def actor(self, cur, subject, action):
        row = cur.execute(
            "SELECT * FROM feedback_actors WHERE subject=%s FOR SHARE", (subject,)
        ).fetchone()
        if not row or not row["active"]:
            raise Denied("An active feedback identity is required")
        if action in OWNER_ACTIONS and row["role"] != "service":
            return
        if row["role"] in ("founder", "executive_administrator") and action in STAFF_ACTIONS | {
            ANALYSE
        }:
            return
        if action in row["permissions"] and (
            row["role"] == "administrator" or (row["role"] == "service" and action == ANALYSE)
        ):
            return
        raise Denied("This feedback identity has no permission for the action")

    def audit(self, cur, subject, action, reference):
        cur.execute(
            "INSERT INTO feedback_audit(actor_key,action,reference) VALUES (%s,%s,%s)",
            (self.owner_key(subject), action, str(reference)),
        )

    def target(self, cur, target):
        row = cur.execute(
            "SELECT * FROM feedback_targets WHERE target=%s AND active", (target,)
        ).fetchone()
        if not row:
            raise Missing("Feedback target is not registered or active")

    def register_target(self, subject, target):
        from uuid import UUID

        if target != "corepath":
            try:
                target = "business:" + str(UUID(target.removeprefix("business:")))
            except ValueError as exc:
                raise Conflict("Use a partner business UUID target") from exc
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self.actor(cur, subject, "feedback.targets.manage")
            cur.execute(
                "INSERT INTO feedback_targets(target,kind) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (target, "corepath" if target == "corepath" else "business"),
            )
            self.audit(cur, subject, "target.register", target)
        return {"target": target}

    def prompt(self, subject, target):
        owner = self.owner_key(subject)
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self.actor(cur, subject, "feedback.prompt")
            self.target(cur, target)
            cur.execute(
                "INSERT INTO feedback_preferences(owner_key) VALUES (%s) ON CONFLICT DO NOTHING",
                (owner,),
            )
            preference = cur.execute(
                "SELECT * FROM feedback_preferences WHERE owner_key=%s FOR UPDATE", (owner,)
            ).fetchone()
            if not preference["allow_requests"]:
                return {"show_prompt": False}
            recent = cur.execute(
                "SELECT 1 FROM feedback_preferences WHERE owner_key=%s AND last_any_prompt_at>now()-(%s*interval '1 day')",
                (owner, self.settings.global_prompt_cooldown_days),
            ).fetchone()
            if recent:
                return {"show_prompt": False}
            row = cur.execute(
                "INSERT INTO feedback_prompts(owner_key,target) VALUES (%s,%s) ON CONFLICT(owner_key,target) DO UPDATE SET last_prompt_at=now() WHERE feedback_prompts.last_prompt_at < now()-(%s * interval '1 day') RETURNING target",
                (owner, target, self.settings.prompt_cooldown_days),
            ).fetchone()
            if row:
                cur.execute(
                    "UPDATE feedback_preferences SET last_any_prompt_at=now() WHERE owner_key=%s",
                    (owner,),
                )
            self.audit(cur, subject, "prompt.check", target)
            return {
                "show_prompt": bool(row),
                "target": target,
                "questions": [
                    "What worked well for you?",
                    "What did not work, or could be better?",
                    "What would you like us to change?",
                ],
                "note": "Both positive and negative feedback are welcome. Skip any question. Feedback is private to the CorePath quality team; avoid identifiable health details. AI analysis is optional.",
            }

    def preference(self, subject, allow):
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self.actor(cur, subject, "feedback.own")
            cur.execute(
                "INSERT INTO feedback_preferences(owner_key,allow_requests) VALUES (%s,%s) ON CONFLICT(owner_key) DO UPDATE SET allow_requests=EXCLUDED.allow_requests",
                (self.owner_key(subject), allow),
            )
            self.audit(cur, subject, "prompt.preference", "owner")
        return {"allow_requests": allow}

    def submit(self, subject, target, entry):
        owner = self.owner_key(subject)
        key = "member:" + owner + ":" + str(entry.client_reference)
        record_id = uuid4()
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self.actor(cur, subject, "feedback.submit")
            self.target(cur, target)
            row = cur.execute(
                "INSERT INTO feedback_records(id,target,owner_key,source_key,source_kind,payload,ai_allowed) VALUES (%s,%s,%s,%s,'member',%s,%s) ON CONFLICT(source_key) DO NOTHING RETURNING id,active",
                (
                    record_id,
                    target,
                    owner,
                    key,
                    self.seal_record(
                        entry.model_dump(mode="json"), owner, record_id, target, "member"
                    ),
                    entry.allow_ai_analysis,
                ),
            ).fetchone()
            if row is None:
                row = cur.execute(
                    "SELECT * FROM feedback_records WHERE source_key=%s", (key,)
                ).fetchone()
                if not row["active"] or row["target"] != target:
                    raise Conflict(
                        "This feedback reference is withdrawn or belongs to another target"
                    )
                if self.record(row) != entry.model_dump(mode="json"):
                    raise Conflict(
                        "This feedback reference already contains different content or consent"
                    )
            self.audit(cur, subject, "feedback.submit", row["id"])
            return {"id": str(row["id"]), "saved": True}

    def own(self, subject):
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self.actor(cur, subject, "feedback.own")
            rows = cur.execute(
                "SELECT * FROM feedback_records WHERE owner_key=%s AND active ORDER BY created_at DESC LIMIT 100",
                (self.owner_key(subject),),
            ).fetchall()
            return [
                {
                    "id": str(r["id"]),
                    "target": r["target"],
                    "content": self.record(r),
                    "allow_ai_analysis": r["ai_allowed"],
                    "version": r["version"],
                }
                for r in rows
            ]

    def _retract(self, cur, record_id):
        cur.execute(
            "UPDATE feedback_themes SET state='retracted',payload=NULL WHERE %s=ANY(source_ids)",
            (record_id,),
        )

    def change(self, subject, record_id, allow=None, delete=False, moderate=False):
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self.actor(cur, subject, "feedback.moderate" if moderate else "feedback.own")
            cur.execute("SELECT pg_advisory_xact_lock(485018100)")
            row = cur.execute(
                "SELECT * FROM feedback_records WHERE id=%s FOR UPDATE", (record_id,)
            ).fetchone()
            if not row or (not moderate and row["owner_key"] != self.owner_key(subject)):
                raise Missing("Feedback not found for this owner")
            if (delete and not row["active"]) or (
                not delete and row["active"] and row["ai_allowed"] == allow
            ):
                return {"updated": True}
            if delete:
                cur.execute(
                    "UPDATE feedback_records SET active=false,ai_allowed=false,payload=NULL,version=version+1 WHERE id=%s",
                    (record_id,),
                )
            else:
                if not row["active"]:
                    raise Conflict("Withdrawn feedback cannot be restored by a late request")
                payload = self.record(row)
                payload["allow_ai_analysis"] = allow
                cur.execute(
                    "UPDATE feedback_records SET ai_allowed=%s,payload=%s,version=version+1 WHERE id=%s",
                    (
                        allow,
                        self.seal_record(
                            payload, row["owner_key"], row["id"], row["target"], row["source_kind"]
                        ),
                        record_id,
                    ),
                )
            self._retract(cur, record_id)
            self.audit(
                cur,
                subject,
                "feedback.withdraw" if delete else "feedback.analysis_consent",
                record_id,
            )
            return {"updated": True}

    def import_review(self, subject, target, review):
        from urllib.parse import urlsplit

        namespace = urlsplit(review.source_url).hostname
        contributor = self.owner_key("review:" + namespace + ":" + review.contributor_reference)
        key = "review:" + namespace + ":" + review.source_reference
        record_id = uuid4()
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self.actor(cur, subject, "feedback.import_reviews")
            self.target(cur, target)
            row = cur.execute(
                "INSERT INTO feedback_records(id,target,owner_key,source_key,source_kind,payload,ai_allowed,reported_at) VALUES (%s,%s,%s,%s,'public_review',%s,true,%s) ON CONFLICT(source_key) DO NOTHING RETURNING id",
                (
                    record_id,
                    target,
                    contributor,
                    key,
                    self.seal_record(
                        {
                            "review": review.text,
                            "source_url": review.source_url,
                            "permission_notes": review.permission_notes,
                            "reviewed_at": review.reviewed_at.isoformat(),
                            "published_at": review.published_at.isoformat(),
                        },
                        contributor,
                        record_id,
                        target,
                        "public_review",
                    ),
                    review.published_at,
                ),
            ).fetchone()
            if not row:
                raise Conflict("This external review is already registered")
            self.audit(cur, subject, "review.import", row["id"])
            return {"id": str(row["id"])}

    def snapshot(self, subject, target):
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self.actor(cur, subject, ANALYSE)
            self.target(cur, target)
            rows = cur.execute(
                "SELECT * FROM feedback_analysis_sources WHERE target=%s AND reported_at>=now()-(%s * interval '1 day') ORDER BY reported_at DESC LIMIT 10",
                (target, self.settings.analysis_window_days),
            ).fetchall()
            result = []
            used = 0
            for row in rows:
                payload = self.record(row)
                content = {
                    field: payload.get(field, "")
                    for field in ("positive", "negative", "suggestions", "review")
                }
                length = len(json.dumps(content))
                if used + length > self.settings.max_context_chars:
                    break
                used += length
                row["content"] = content
                del row["payload"]
                result.append(row)
            return result

    def save_themes(self, subject, target, snapshot, themes):
        from feedback.bot import grounded_themes

        accepted = grounded_themes(snapshot, themes, self.settings.min_contributors)
        inventory = {str(r["id"]): r for r in snapshot}
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self.actor(cur, subject, ANALYSE)
            self.target(cur, target)
            cur.execute("SELECT pg_advisory_xact_lock(485018100)")
            saved = []
            for theme in accepted:
                ids = {citation["record_id"] for citation in theme["citations"]}
                for record_id in ids:
                    row = cur.execute(
                        "SELECT version FROM feedback_analysis_sources WHERE id=%s AND target=%s",
                        (record_id, target),
                    ).fetchone()
                    if not row or row["version"] != inventory[record_id]["version"]:
                        raise Conflict("Feedback consent or source changed during analysis")
                fingerprint = hashlib.sha256(
                    json.dumps(
                        {
                            "target": target,
                            "kind": theme["kind"],
                            "category": theme["category"],
                            "severity": theme["severity"],
                            "sources": sorted((i, inventory[i]["version"]) for i in ids),
                        },
                        sort_keys=True,
                    ).encode()
                ).hexdigest()
                theme_id = uuid4()
                row = cur.execute(
                    "INSERT INTO feedback_themes(id,target,fingerprint,kind,severity,contributor_count,source_ids,payload) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(fingerprint) DO NOTHING RETURNING id",
                    (
                        theme_id,
                        target,
                        fingerprint,
                        theme["kind"],
                        theme["severity"],
                        theme["contributor_count"],
                        list(ids),
                        self.seal_theme(theme, theme_id, target),
                    ),
                ).fetchone()
                if row:
                    self.audit(cur, subject, "theme.raise_for_review", row["id"])
                    saved.append(str(row["id"]))
            return {
                "theme_ids": saved,
                "review_required": True,
                "records_considered": len(snapshot),
                "note": "Signals for human review, not substantiated findings or automatic rating changes.",
            }

    def staff_records(self, subject, target):
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self.actor(cur, subject, "feedback.read")
            self.target(cur, target)
            rows = cur.execute(
                "SELECT * FROM feedback_records WHERE target=%s AND active ORDER BY created_at DESC LIMIT 100",
                (target,),
            ).fetchall()
            self.audit(cur, subject, "feedback.staff_review", target)
            return [
                {
                    "id": str(r["id"]),
                    "source_kind": r["source_kind"],
                    "content": self.record(r),
                    "allow_ai_analysis": r["ai_allowed"],
                }
                for r in rows
            ]

    def themes(self, subject, target):
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self.actor(cur, subject, "feedback.read")
            self.target(cur, target)
            rows = cur.execute(
                "SELECT * FROM feedback_themes WHERE target=%s ORDER BY created_at DESC LIMIT 100",
                (target,),
            ).fetchall()
            return [
                {
                    "id": str(r["id"]),
                    "state": r["state"],
                    "content": self.theme(r) if r["payload"] else None,
                }
                for r in rows
            ]

    def resolve(self, subject, theme_id, resolution):
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self.actor(cur, subject, "feedback.moderate")
            row = cur.execute(
                "SELECT * FROM feedback_themes WHERE id=%s FOR UPDATE", (theme_id,)
            ).fetchone()
            if not row:
                raise Missing("Feedback theme not found")
            if row["state"] == "retracted":
                raise Conflict("Retracted feedback cannot be restored by a resolution")
            payload = self.theme(row)
            payload["resolution"] = resolution.reason
            cur.execute(
                "UPDATE feedback_themes SET state=%s,payload=%s WHERE id=%s",
                (resolution.state, self.seal_theme(payload, theme_id, row["target"]), theme_id),
            )
            self.audit(cur, subject, "theme." + resolution.state, theme_id)
            return {"state": resolution.state}
