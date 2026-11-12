import hashlib
import secrets
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from partners.mail import DeliveryUnknown, invitation
from partners.models import BusinessSeed, Contact, Evidence, Policy
from partners.qualification import assess

READ = "partners.read"
RESEARCH = "partners.research"
VERIFY = "partners.verify"
POLICY = "partners.policy.manage"
CONTACT = "partners.contact.verify"
QUEUE = "partners.invitation.queue"
SEND = "partners.invitation.send"
SUPPRESS = "partners.suppress"
ACTIONS = {READ, RESEARCH, VERIFY, POLICY, CONTACT, QUEUE, SEND, SUPPRESS}
SERVICE_ACTIONS = {READ, RESEARCH, QUEUE, SEND}
MAIL_LOCK = 0x43504D41494C


class Denied(Exception):
    pass


class Conflict(Exception):
    pass


class Missing(Exception):
    pass


class Repository:
    def __init__(self, pool):
        self.pool = pool

    def _actor(self, c, subject, action):
        row = c.execute(
            "SELECT * FROM partner_actors WHERE subject=%s FOR SHARE", (subject,)
        ).fetchone()
        if not row or not row["active"] or action not in ACTIONS:
            raise Denied("An active, delegated partner-service identity is required")
        if row["role"] in ("founder", "executive_administrator"):
            return
        if (row["role"] == "service" and action not in SERVICE_ACTIONS) or action not in row[
            "permissions"
        ]:
            raise Denied("This identity has no permission for this action")

    def _audit(self, c, subject, action, reference, detail=None):
        c.execute(
            "INSERT INTO partner_audit(subject,action,reference,detail) VALUES (%s,%s,%s,%s)",
            (subject, action, str(reference), Jsonb(detail or {})),
        )

    def _business(self, c, business_id):
        row = c.execute(
            "SELECT * FROM partner_businesses WHERE id=%s FOR UPDATE", (business_id,)
        ).fetchone()
        if not row:
            raise Missing("Business not found")
        return row

    def authorize(self, subject, action):
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self._actor(cur, subject, action)

    def ingest(self, subject, seed: BusinessSeed):
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self._actor(cur, subject, RESEARCH)
            row = cur.execute(
                "INSERT INTO partner_businesses(id,identity_key,document) VALUES (%s,%s,%s) ON CONFLICT (identity_key) DO NOTHING RETURNING *",
                (uuid4(), seed.identity_key(), Jsonb(seed.model_dump(mode="json"))),
            ).fetchone()
            if row is None:
                row = cur.execute(
                    "SELECT * FROM partner_businesses WHERE identity_key=%s", (seed.identity_key(),)
                ).fetchone()
            self._audit(cur, subject, "business.ingest", row["id"])
            return row

    def list_businesses(self, subject, *, after=None, limit=50):
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self._actor(cur, subject, READ)
            return cur.execute(
                "SELECT * FROM partner_businesses WHERE (%s::uuid IS NULL OR id>%s::uuid) ORDER BY id LIMIT %s",
                (after, after, limit),
            ).fetchall()

    def read_business(self, subject, business_id):
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self._actor(cur, subject, READ)
            business = self._business(cur, business_id)
            evidence = cur.execute(
                "SELECT * FROM partner_evidence WHERE business_id=%s ORDER BY id", (business_id,)
            ).fetchall()
            assessments = cur.execute(
                "SELECT * FROM partner_assessments WHERE business_id=%s ORDER BY created_at DESC LIMIT 20",
                (business_id,),
            ).fetchall()
            return {"business": business, "evidence": evidence, "assessments": assessments}

    def create_policy(self, subject, policy: Policy):
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self._actor(cur, subject, POLICY)
            row = cur.execute(
                "INSERT INTO partner_policies(id,document) VALUES (%s,%s) RETURNING *",
                (uuid4(), Jsonb(policy.model_dump(mode="json"))),
            ).fetchone()
            self._audit(cur, subject, "policy.create_draft", row["id"])
            return row

    def approve_policy(self, subject, policy_id, review):
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self._actor(cur, subject, POLICY)
            row = cur.execute(
                "UPDATE partner_policies SET approved=%s,approved_by=%s,approved_at=now() WHERE id=%s RETURNING *",
                (review.verified, subject, policy_id),
            ).fetchone()
            if not row:
                raise Missing("Policy not found")
            self._audit(cur, subject, "policy.review", policy_id, review.model_dump())
            return row

    def add_evidence(self, subject, business_id, evidence: Evidence):
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self._actor(cur, subject, RESEARCH)
            self._business(cur, business_id)
            row = cur.execute(
                "INSERT INTO partner_evidence(id,business_id,document) VALUES (%s,%s,%s) ON CONFLICT (id) DO NOTHING RETURNING *",
                (evidence.id, business_id, Jsonb(evidence.model_dump(mode="json"))),
            ).fetchone()
            if row is None:
                raise Conflict("Evidence ID already exists; evidence is immutable")
            cur.execute(
                "UPDATE partner_businesses SET revision=revision+1 WHERE id=%s", (business_id,)
            )
            self._audit(cur, subject, "evidence.propose", evidence.id)
            return row

    def review_evidence(self, subject, evidence_id, review):
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self._actor(cur, subject, VERIFY)
            item = cur.execute(
                "SELECT business_id FROM partner_evidence WHERE id=%s", (evidence_id,)
            ).fetchone()
            if not item:
                raise Missing("Evidence not found")
            self._business(cur, item["business_id"])
            row = cur.execute(
                "UPDATE partner_evidence SET verified=%s,active=%s,reviewed_by=%s WHERE id=%s RETURNING *",
                (review.verified, review.verified, subject, evidence_id),
            ).fetchone()
            cur.execute(
                "UPDATE partner_businesses SET revision=revision+1 WHERE id=%s",
                (item["business_id"],),
            )
            self._audit(cur, subject, "evidence.review", evidence_id, review.model_dump())
            return row

    def assess(self, subject, business_id, policy_id):
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self._actor(cur, subject, RESEARCH)
            business = self._business(cur, business_id)
            policy = cur.execute(
                "SELECT * FROM partner_policies WHERE id=%s FOR SHARE", (policy_id,)
            ).fetchone()
            if not policy:
                raise Missing("Policy not found")
            if (
                policy["document"]["country"] != business["document"]["country"]
                or policy["document"]["sector"] != business["document"]["sector"]
            ):
                raise Conflict("Policy country or sector does not match the business")
            evidence = cur.execute(
                "SELECT * FROM partner_evidence WHERE business_id=%s", (business_id,)
            ).fetchall()
            result = assess(Policy.model_validate(policy["document"]), evidence)
            result["policy_approved"] = policy["approved"]
            row = cur.execute(
                "INSERT INTO partner_assessments(id,business_id,policy_id,business_revision,document) VALUES (%s,%s,%s,%s,%s) RETURNING *",
                (uuid4(), business_id, policy_id, business["revision"], Jsonb(result)),
            ).fetchone()
            self._audit(
                cur, subject, "business.assess", row["id"], {"decision": result["decision"]}
            )
            return row

    def save_contact(self, subject, business_id, contact: Contact):
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self._actor(cur, subject, CONTACT)
            self._business(cur, business_id)
            cur.execute(
                "INSERT INTO partner_contacts(business_id,email,document,verified_by) VALUES (%s,%s,%s,%s) ON CONFLICT (business_id) DO UPDATE SET email=EXCLUDED.email,document=EXCLUDED.document,verified_by=EXCLUDED.verified_by,active=true",
                (business_id, contact.email, Jsonb(contact.model_dump(mode="json")), subject),
            )
            self._audit(cur, subject, "contact.verify", business_id, {"basis": contact.basis})
            return {"business_id": business_id, "contact_recorded": True}

    def _guard(self, cur, business, assessment, settings):
        if business["document"]["country"] not in settings.allowed_countries:
            raise Conflict("Country is not enabled for this outreach trial")
        if business["document"]["sector"] not in settings.allowed_sectors:
            raise Conflict("Sector is not enabled for this outreach trial")
        if business["revision"] != assessment["business_revision"]:
            raise Conflict("Business evidence changed; assess again")
        policy = cur.execute(
            "SELECT * FROM partner_policies WHERE id=%s FOR SHARE", (assessment["policy_id"],)
        ).fetchone()
        if not policy or not policy["approved"]:
            raise Conflict("Qualification policy has not been approved or was withdrawn")
        evidence = cur.execute(
            "SELECT * FROM partner_evidence WHERE business_id=%s", (business["id"],)
        ).fetchall()
        if assess(Policy.model_validate(policy["document"]), evidence)["decision"] != "qualified":
            raise Conflict("Current evidence does not meet every partner requirement")
        contact = cur.execute(
            "SELECT * FROM partner_contacts WHERE business_id=%s FOR UPDATE", (business["id"],)
        ).fetchone()
        if not contact or not contact["active"]:
            raise Conflict("A reviewed, current permission-to-contact record is required")
        try:
            permission = Contact.model_validate(contact["document"])
        except ValueError as exc:
            raise Conflict("Permission to contact has expired") from exc
        if (
            not permission.commission_compatible
            or not permission.commission_review_url
            or len(permission.commission_review_notes) < 20
        ):
            raise Conflict(
                "The proposed commercial arrangement needs a documented compatibility review"
            )
        if cur.execute(
            "SELECT 1 FROM partner_suppressions WHERE email=%s", (contact["email"],)
        ).fetchone():
            raise Conflict("The recipient has opted out or is suppressed")
        return contact

    def enqueue(self, subject, business_id, assessment_id, settings):
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self._actor(cur, subject, QUEUE)
            business = self._business(cur, business_id)
            assessment = cur.execute(
                "SELECT * FROM partner_assessments WHERE id=%s AND business_id=%s",
                (assessment_id, business_id),
            ).fetchone()
            if not assessment:
                raise Missing("Assessment not found for this business")
            contact = self._guard(cur, business, assessment, settings)
            existing = cur.execute(
                "SELECT * FROM partner_outbox WHERE business_id=%s FOR UPDATE", (business_id,)
            ).fetchone()
            if (
                existing
                and existing["state"] == "queued"
                and existing["recipient"] == contact["email"]
            ):
                if existing["assessment_id"] != assessment_id:
                    existing = cur.execute(
                        "UPDATE partner_outbox SET assessment_id=%s WHERE id=%s RETURNING *",
                        (assessment_id, existing["id"]),
                    ).fetchone()
                    self._audit(cur, subject, "invitation.assessment_refresh", existing["id"])
                return self._safe_outbox(existing)
            if existing and (existing["state"] != "blocked" or existing["dispatch_at"]):
                raise Conflict("An invitation already exists for this business")
            if cur.execute(
                "SELECT 1 FROM partner_outbox WHERE recipient=%s AND business_id<>%s",
                (contact["email"], business_id),
            ).fetchone():
                raise Conflict("This address already has an invitation")
            token = secrets.token_urlsafe(32)
            digest = hashlib.sha256(token.encode()).hexdigest()
            if existing:
                row = cur.execute(
                    "UPDATE partner_outbox SET assessment_id=%s,recipient=%s,unsubscribe_hash=%s,unsubscribe_token=%s,state='queued',content=NULL WHERE id=%s RETURNING *",
                    (assessment_id, contact["email"], digest, token, existing["id"]),
                ).fetchone()
            else:
                row = cur.execute(
                    "INSERT INTO partner_outbox(id,business_id,assessment_id,recipient,unsubscribe_hash,unsubscribe_token) VALUES (%s,%s,%s,%s,%s,%s) RETURNING *",
                    (uuid4(), business_id, assessment_id, contact["email"], digest, token),
                ).fetchone()
            self._audit(cur, subject, "invitation.queue", row["id"])
            return self._safe_outbox(row)

    @staticmethod
    def _safe_outbox(row):
        return {
            k: row[k]
            for k in (
                "id",
                "business_id",
                "assessment_id",
                "state",
                "provider_id",
                "dispatch_at",
                "created_at",
            )
        }

    def list_invitations(self, subject):
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self._actor(cur, subject, READ)
            return [
                self._safe_outbox(row)
                for row in cur.execute(
                    "SELECT * FROM partner_outbox ORDER BY created_at DESC LIMIT 100"
                ).fetchall()
            ]

    def suppress(self, subject, email, reason):
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self._actor(cur, subject, SUPPRESS)
            self._suppress(cur, email, reason)
            self._audit(
                cur, subject, "recipient.suppress", hashlib.sha256(email.encode()).hexdigest()
            )

    def _suppress(self, cur, email, reason):
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (MAIL_LOCK,))
        cur.execute(
            "INSERT INTO partner_suppressions(email,reason) VALUES (%s,%s) ON CONFLICT (email) DO NOTHING",
            (email, reason),
        )
        cur.execute(
            "UPDATE partner_outbox SET state='blocked' WHERE recipient=%s AND state='queued'",
            (email,),
        )

    def unsubscribe(self, token):
        if len(token) != 43:
            return
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (MAIL_LOCK,))
            row = cur.execute(
                "SELECT recipient,id FROM partner_outbox WHERE unsubscribe_hash=%s",
                (hashlib.sha256(token.encode()).hexdigest(),),
            ).fetchone()
            if row:
                self._suppress(cur, row["recipient"], "Unsubscribed by recipient")
                self._audit(cur, "recipient", "recipient.unsubscribe", row["id"])

    def consume_dispatch_capability(self, cap):
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self._actor(cur, cap.subject, SEND)
            cur.execute(
                "DELETE FROM partner_dispatch_nonces WHERE expires_at<now()-interval '10 minutes'"
            )
            row = cur.execute(
                "INSERT INTO partner_dispatch_nonces(request_id,subject,expires_at) VALUES (%s,%s,to_timestamp(%s)) ON CONFLICT DO NOTHING RETURNING request_id",
                (cap.request_id, cap.subject, cap.expires_at),
            ).fetchone()
            if not row:
                raise Conflict("This dispatch capability has already been used")

    def reserve(self, subject, settings, renderer):
        if not settings.delivery_ready():
            raise Conflict("Email delivery is not enabled and fully configured")
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self._actor(cur, subject, SEND)
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (MAIL_LOCK,))
            count = cur.execute(
                "SELECT count(*) AS count FROM partner_outbox WHERE dispatch_at>=date_trunc('day',now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"
            ).fetchone()["count"]
            if count >= settings.daily_email_limit:
                raise Conflict("Daily outreach limit reached")
            row = cur.execute(
                "SELECT * FROM partner_outbox WHERE state='queued' ORDER BY created_at,id LIMIT 1"
            ).fetchone()
            if not row:
                return None
            business = self._business(cur, row["business_id"])
            row = cur.execute(
                "SELECT * FROM partner_outbox WHERE id=%s FOR UPDATE", (row["id"],)
            ).fetchone()
            assessment = cur.execute(
                "SELECT * FROM partner_assessments WHERE id=%s", (row["assessment_id"],)
            ).fetchone()
            try:
                contact = self._guard(cur, business, assessment, settings)
                if row["recipient"] != contact["email"]:
                    raise Conflict("The verified contact changed")
            except Conflict as exc:
                cur.execute("UPDATE partner_outbox SET state='blocked' WHERE id=%s", (row["id"],))
                self._audit(cur, subject, "invitation.block", row["id"], {"reason": str(exc)})
                return {"blocked": str(row["id"])}
            payload = renderer(business["document"], row, settings)
            cur.execute(
                "UPDATE partner_outbox SET state='dispatching',dispatch_at=now(),content=%s WHERE id=%s",
                (Jsonb(payload), row["id"]),
            )
            self._audit(cur, subject, "invitation.dispatch_started", row["id"])
            return {"id": row["id"], "payload": payload}

    def deliver_reserved(self, subject, reservation, settings, transport):
        # The durable dispatching state prevents automatic resend after a crash.
        # Suppression and the final send share a lock; either can win that boundary.
        with self.pool.connection() as c, c.cursor(row_factory=dict_row) as cur:
            self._actor(cur, subject, SEND)
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (MAIL_LOCK,))
            row = cur.execute(
                "SELECT * FROM partner_outbox WHERE id=%s", (reservation["id"],)
            ).fetchone()
            if not row or row["state"] != "dispatching":
                raise Conflict("Invitation is no longer reserved")
            business = self._business(cur, row["business_id"])
            row = cur.execute(
                "SELECT * FROM partner_outbox WHERE id=%s FOR UPDATE", (row["id"],)
            ).fetchone()
            assessment = cur.execute(
                "SELECT * FROM partner_assessments WHERE id=%s", (row["assessment_id"],)
            ).fetchone()
            try:
                contact = self._guard(cur, business, assessment, settings)
                if (
                    contact["email"] != row["recipient"]
                    or not settings.delivery_ready()
                    or row["content"] != invitation(business["document"], row, settings)
                ):
                    raise Conflict("Delivery identity, template or eligibility changed")
            except Conflict as exc:
                cur.execute("UPDATE partner_outbox SET state='blocked' WHERE id=%s", (row["id"],))
                self._audit(cur, subject, "invitation.block", row["id"], {"reason": str(exc)})
                return {"id": row["id"], "state": "blocked"}
            try:
                provider_id = transport.send(row["content"], str(row["id"]))
            except DeliveryUnknown:
                cur.execute("UPDATE partner_outbox SET state='unknown' WHERE id=%s", (row["id"],))
                self._audit(cur, subject, "invitation.delivery_unknown", row["id"])
                return {"id": row["id"], "state": "unknown"}
            cur.execute(
                "UPDATE partner_outbox SET state='sent',provider_id=%s WHERE id=%s",
                (provider_id, row["id"]),
            )
            self._audit(cur, subject, "invitation.sent", row["id"])
            return {"id": row["id"], "state": "sent"}
