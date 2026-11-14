"""Owner-scoped, opt-in profile proposals and separately stored public locations."""

import json
from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator

from .contracts import Model
from .provider import Provider
from .storage import Store, encode, identifier, now

CATEGORIES = {"identity", "direction", "circumstances", "habits", "emotions",
              "relationships", "barriers", "preferences"}


class Message(Model):
    id: str = Field(min_length=1, max_length=100)
    conversation_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=5000)
    categories: list[str] = Field(min_length=1, max_length=8)
    sensitive: bool

    @model_validator(mode="after")
    def reviewed_categories(self):
        if len(set(self.categories)) != len(self.categories) or not set(self.categories) <= CATEGORIES:
            raise ValueError("Classify excerpts using distinct supported categories before processing")
        return self


class Evidence(Model):
    message_id: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=3, max_length=600)


class Observation(Model):
    category: Literal["identity", "direction", "circumstances", "habits", "emotions",
                      "relationships", "barriers", "preferences"]
    statement: str = Field(min_length=3, max_length=1000)
    kind: Literal["user_statement", "observed_pattern", "hypothesis"]
    sensitive: bool
    evidence: list[Evidence] = Field(min_length=1, max_length=8)


class FollowUp(Model):
    question: str = Field(min_length=3, max_length=400)
    purpose: str = Field(min_length=3, max_length=400)
    category: Literal["identity", "direction", "circumstances", "habits", "emotions",
                      "relationships", "barriers", "preferences"]
    direct: bool


class ProfileProposal(Model):
    observations: list[Observation] = Field(max_length=5)
    follow_up: FollowUp | None


class Consent(Model):
    purpose: str = Field(min_length=3, max_length=300)
    analysis_enabled: bool
    model_processing: bool
    sensitive_enabled: bool
    categories: list[str] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def categories_known(self):
        if len(set(self.categories)) != len(self.categories) or not set(self.categories) <= CATEGORIES:
            raise ValueError("Choose distinct supported profile categories")
        return self


class LifeProfile:
    def __init__(self, store: Store, provider: Provider | None = None):
        self.store, self.provider = store, provider

    def set_consent(self, owner: str, consent: Consent):
        if not owner:
            raise ValueError("Authenticated owner is required")
        consent = Consent.model_validate(consent)
        with self.store.transaction() as db:
            # A database-wide monotonic revision prevents an old in-flight
            # proposal matching a deleted and recreated owner's consent.
            revision = db.execute("SELECT next_revision FROM profile_revision WHERE singleton=1").fetchone()[0]
            db.execute("UPDATE profile_revision SET next_revision=next_revision+1 WHERE singleton=1")
            db.execute("""INSERT INTO consent VALUES(?,?,?,?,?,?,?)
              ON CONFLICT(owner) DO UPDATE SET purpose=excluded.purpose,
              enabled=excluded.enabled, model_processing=excluded.model_processing,
              sensitive=excluded.sensitive, categories=excluded.categories, revision=excluded.revision""",
                       (owner, consent.purpose, consent.analysis_enabled, consent.model_processing,
                        consent.sensitive_enabled, encode(consent.categories), revision))
            # Changed purpose/categories/permissions require fresh sharing decisions.
            db.execute("UPDATE observations SET share_persy=0, share_coordinator=0 WHERE owner=?", (owner,))
        return revision

    def _consent(self, owner):
        row = self.store.db.execute("SELECT * FROM consent WHERE owner=?", (owner,)).fetchone()
        if not row or not row["enabled"]:
            raise PermissionError("Profile analysis consent is absent or withdrawn")
        return row

    def _messages(self, consent, purpose, messages):
        if not consent["model_processing"] or consent["purpose"] != purpose:
            raise PermissionError("Model processing and exact purpose must be authorised")
        messages = [Message.model_validate(m) for m in messages]
        if not 1 <= len(messages) <= 20 or len({m.id for m in messages}) != len(messages):
            raise ValueError("Supply 1–20 distinct, reviewed excerpts from this owner")
        if sum(len(m.text) for m in messages) > 30000:
            raise ValueError("Profile input exceeds the context budget")
        categories = set(json.loads(consent["categories"]))
        for message in messages:
            if not set(message.categories) <= categories:
                raise PermissionError("Input excerpt contains an unconsented category")
            if (message.sensitive or set(message.categories) & {"identity", "emotions", "relationships"}) and not consent["sensitive"]:
                raise PermissionError("Sensitive input needs permission before model processing")
        return messages

    def analyse(self, owner: str, purpose: str, messages: list[Message], *,
                ready_for_direct_question: bool = False) -> dict:
        consent = self._consent(owner)
        messages = self._messages(consent, purpose, messages)
        if self.provider is None:
            raise RuntimeError("A profile model provider is not configured")
        proposal = ProfileProposal.model_validate(self.provider.generate(
            "life-profile", "propose_understanding", {
                "purpose": purpose, "categories": json.loads(consent["categories"]),
                "sensitive_enabled": bool(consent["sensitive"]),
                "ready_for_direct_question": ready_for_direct_question,
                "messages": [m.model_dump(mode="json") for m in messages],
            }, ProfileProposal))
        return self.record_proposal(owner, purpose, messages, proposal,
                                    consent_revision=consent["revision"],
                                    ready_for_direct_question=ready_for_direct_question)

    def record_proposal(self, owner, purpose, messages, proposal: ProfileProposal, *,
                        consent_revision: int, ready_for_direct_question=False):
        # Network/model execution happens outside this permission/write lock.
        with self.store.transaction():
            return self._record_proposal(owner, purpose, messages, proposal,
                                        consent_revision=consent_revision,
                                        ready_for_direct_question=ready_for_direct_question)

    def _record_proposal(self, owner, purpose, messages, proposal, *,
                         consent_revision, ready_for_direct_question):
        consent = self._consent(owner)
        if consent["purpose"] != purpose or consent["revision"] != consent_revision:
            raise PermissionError("Profile consent changed while processing")
        proposal = ProfileProposal.model_validate(proposal)
        messages = self._messages(consent, purpose, messages)
        indexed = {m.id: m for m in messages}
        categories = set(json.loads(consent["categories"]))
        records = []
        for observation in proposal.observations:
            if observation.category not in categories:
                raise PermissionError("Observation exceeds consented categories")
            sensitive = observation.sensitive or observation.category in {"emotions", "relationships", "identity"}
            if sensitive and not consent["sensitive"]:
                continue
            conversations = set()
            for evidence in observation.evidence:
                message = indexed.get(evidence.message_id)
                if message is None or evidence.quote not in message.text:
                    raise ValueError("Profile evidence must match supplied owner messages")
                if observation.category not in message.categories:
                    raise PermissionError("Observation category is outside its reviewed source excerpt")
                conversations.add(message.conversation_id)
            if observation.kind == "observed_pattern" and len(conversations) < 2:
                raise ValueError("A pattern needs separate conversations")
            item_id = identifier()
            records.append((item_id, owner, consent_revision, observation.category,
                            observation.statement, observation.kind, sensitive,
                            encode([{**e.model_dump(), "conversation_id": indexed[e.message_id].conversation_id}
                                    for e in observation.evidence]), "proposed", 0, 0, now()))
        follow_up = proposal.follow_up
        if follow_up and (follow_up.category not in categories or
                          (follow_up.direct and not ready_for_direct_question) or
                          (follow_up.category in {"identity", "emotions", "relationships"} and not consent["sensitive"])):
            follow_up = None
        self.store.db.executemany("INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", records)
        return {"proposal_ids": [r[0] for r in records], "review_required": True,
                "follow_up": follow_up.model_dump() if follow_up else None}

    def review(self, owner, item_id, decision: Literal["accept", "reject"], *,
               correction: str | None = None, share_persy=False, share_coordinator=False):
        with self.store.transaction():
            self._review(owner, item_id, decision, correction=correction,
                         share_persy=share_persy, share_coordinator=share_coordinator)

    def _review(self, owner, item_id, decision, *, correction, share_persy, share_coordinator):
        consent = self._consent(owner)
        if decision not in {"accept", "reject"}:
            raise ValueError("Decision must be accept or reject")
        row = self.store.db.execute("SELECT * FROM observations WHERE id=? AND owner=?", (item_id, owner)).fetchone()
        if row is None:
            raise KeyError("Observation not found")
        if row["category"] not in json.loads(consent["categories"]) or (row["sensitive"] and not consent["sensitive"]):
            raise PermissionError("Current consent excludes this observation")
        statement = row["statement"] if correction is None else correction.strip()
        if not 3 <= len(statement) <= 1000:
            raise ValueError("Correction must be between 3 and 1000 characters")
        sensitive = bool(row["sensitive"]) or correction is not None
        if sensitive and not consent["sensitive"] and (share_persy or share_coordinator):
            raise PermissionError("A correction can add sensitive content; sharing needs explicit sensitive permission")
        self.store.db.execute("""UPDATE observations SET statement=?, kind=?, state=?, sensitive=?,
                       share_persy=?, share_coordinator=?, updated_at=? WHERE id=? AND owner=?""",
                       (statement, "owner_corrected" if correction else row["kind"],
                        "accepted" if decision == "accept" else "rejected",
                        sensitive,
                        bool(share_persy) and decision == "accept",
                        bool(share_coordinator) and decision == "accept", now(), item_id, owner))

    def context(self, caller_role, owner, categories: set[str], limit: int = 20):
        if caller_role not in {"persy", "chief-of-staff"}:
            raise PermissionError("Only Persy and the Chief of Staff can request profile context")
        with self.store.transaction():
            return self._context(caller_role, owner, categories, limit)

    def _context(self, caller_role, owner, categories, limit):
        consent = self._consent(owner)
        if not categories or not categories <= CATEGORIES or not 1 <= limit <= 50:
            raise ValueError("Request explicit categories and a bounded context")
        allowed = categories & set(json.loads(consent["categories"]))
        # Column selection is a fixed role mapping, never a caller SQL fragment.
        column = "share_persy" if caller_role == "persy" else "share_coordinator"
        rows = self.store.db.execute(
            f"SELECT id,category,statement,kind,sensitive,updated_at FROM observations WHERE owner=? AND state='accepted' AND {column}=1 ORDER BY updated_at DESC,id", (owner,))
        result = []
        for row in rows:
            if row["category"] in allowed and (not row["sensitive"] or consent["sensitive"]):
                result.append({k: row[k] for k in ("id", "category", "statement", "kind", "updated_at")})
                if len(result) == limit:
                    break
        return result

    def inspect(self, owner):
        return [dict(r) for r in self.store.db.execute("SELECT * FROM observations WHERE owner=? ORDER BY updated_at,id", (owner,))]

    def delete(self, owner, item_id):
        with self.store.db as db:
            return db.execute("DELETE FROM observations WHERE id=? AND owner=?", (item_id, owner)).rowcount

    def erase_owner(self, owner):
        with self.store.transaction() as db:
            db.execute("DELETE FROM observations WHERE owner=?", (owner,))
            db.execute("DELETE FROM consent WHERE owner=?", (owner,))


class LocationFact(Model):
    topic: str = Field(min_length=1, max_length=100)
    statement: str = Field(min_length=3, max_length=1500)
    source_url: str = Field(pattern=r"^https://", max_length=2000)
    checked_at: datetime
    review_after: datetime
    attribution: str = Field(min_length=3, max_length=400)

    @model_validator(mode="after")
    def dates(self):
        if (self.checked_at.tzinfo is None or self.review_after.tzinfo is None or
            self.checked_at > datetime.now(UTC) or self.review_after <= self.checked_at):
            raise ValueError("Use a past timezone-aware check and a later review date")
        return self


class Location(Model):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    region: str = Field(max_length=200)
    kind: Literal["city", "town", "rural", "remote"]
    timezone: str = Field(min_length=1, max_length=100)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    facts: list[LocationFact] = Field(max_length=100)
    gaps: list[str] = Field(max_length=50)

    @model_validator(mode="after")
    def valid_timezone(self):
        ZoneInfo(self.timezone)
        return self


class LocationDirectory:
    """Public, operator-reviewed records. No private-profile data enters this API."""

    def __init__(self, store: Store):
        self.store = store

    def put(self, location: Location, *, reviewed_public_record: bool):
        if not reviewed_public_record:
            raise PermissionError("Public source and privacy review is required")
        location = Location.model_validate(location)
        with self.store.db as db:
            db.execute("INSERT INTO locations VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                       (location.id, location.model_dump_json()))

    def get(self, location_id):
        row = self.store.db.execute("SELECT payload FROM locations WHERE id=?", (location_id,)).fetchone()
        if row is None:
            raise KeyError("Location not found; research is needed")
        value = json.loads(row[0])
        for fact in value["facts"]:
            fact["needs_refresh"] = datetime.fromisoformat(fact["review_after"]) <= datetime.now(UTC)
        return value

    def search(self, name: str, limit: int = 20):
        if not 1 <= limit <= 100 or not name.strip():
            raise ValueError("Use a place name and bounded result count")
        result = []
        # Literal matching avoids SQL wildcard surprises; directory scale needs a
        # real geographic index in the production integration.
        for row in self.store.db.execute("SELECT id,payload FROM locations ORDER BY id"):
            value = json.loads(row["payload"])
            if name.casefold() in value["name"].casefold():
                result.append(self.get(row["id"]))
                if len(result) == limit:
                    break
        return result
