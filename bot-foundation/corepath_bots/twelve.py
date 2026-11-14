"""Founder-controlled synthesis of reviewed, explicitly public general findings."""

import json
import hashlib

from pydantic import Field, model_validator

from .contracts import Claim, Domain, Model, Source, TwelveReport
from .provider import Provider
from .storage import Store, encode, identifier, now
from .team import InvalidEvidence, validate_contribution
from .contracts import Contribution


class PublicFinding(Model):
    id: str = Field(min_length=1, max_length=100)
    domain: Domain
    claim: Claim
    sources: list[Source] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def distinct_sources(self):
        if len({source.id for source in self.sources}) != len(self.sources):
            raise ValueError("Reviewed finding source IDs must be distinct")
        return self


class KnowledgeReview:
    def __init__(self, store: Store):
        self.store = store

    def accept(self, finding: PublicFinding, *, reviewer: str,
               reviewed_as_nonpersonal: bool, independent_review_complete: bool):
        if not reviewer or not reviewed_as_nonpersonal or not independent_review_complete:
            raise PermissionError("Independent evidence and nonpersonal-data review are required")
        finding = PublicFinding.model_validate(finding)
        validate_contribution(finding.domain, Contribution(
            relevant=True, summary="Reviewed general finding", claims=[finding.claim],
            questions=[], gaps=[], peer_requests=[], referral_reason=None), finding.sources)
        with self.store.transaction() as db:
            db.execute("INSERT INTO findings VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET domain=excluded.domain,payload=excluded.payload,reviewed_by=excluded.reviewed_by,reviewed_at=excluded.reviewed_at",
                       (finding.id, finding.domain.value, finding.model_dump_json(), reviewer, now()))

    def retract(self, finding_id):
        with self.store.transaction() as db:
            db.execute("DELETE FROM findings WHERE id=?", (finding_id,))


class Twelve:
    def __init__(self, store: Store, provider: Provider, *, founder_id: str):
        if not founder_id:
            raise ValueError("Configure the authenticated founder's identity")
        self.store, self.provider, self.founder_id = store, provider, founder_id

    def _founder(self, actor):
        if actor != self.founder_id:
            raise PermissionError("Only the founder can direct 12")

    def enable(self, actor):
        self._founder(actor)
        with self.store.transaction() as db:
            db.execute("UPDATE twelve_state SET enabled=1,generation=generation+1 WHERE singleton=1")

    def shutdown(self, actor):
        self._founder(actor)
        with self.store.transaction() as db:
            db.execute("UPDATE twelve_state SET enabled=0,generation=generation+1 WHERE singleton=1")

    def status(self, actor):
        if actor not in {self.founder_id, "chief-of-staff"}:
            raise PermissionError("Status is available only to founder and coordinator")
        return dict(self.store.db.execute("SELECT enabled,generation FROM twelve_state WHERE singleton=1").fetchone())

    def _active(self, generation=None):
        status = self.status(self.founder_id)
        if not status["enabled"] or (generation is not None and generation != status["generation"]):
            raise PermissionError("12 is disabled or this work was revoked")
        return status["generation"]

    def run(self, actor, assignment="Review general findings and identify useful cross-field ideas."):
        self._founder(actor)
        if not 5 <= len(assignment) <= 2000:
            raise ValueError("Use a bounded founder assignment")
        generation = self._active()
        count = self.store.db.execute("SELECT count(*) FROM findings").fetchone()[0]
        if count > 100:
            raise ValueError("Reviewed archive exceeds one batch; integrate explicit paginated review before running 12")
        rows = self.store.db.execute("SELECT id,payload FROM findings ORDER BY id LIMIT 100").fetchall()
        if not rows:
            return {"state": "needs_reviewed_findings", "report_id": None}
        findings = [json.loads(r["payload"]) for r in rows]
        if len(encode(findings)) > 60000:
            raise ValueError("Select a smaller reviewed batch before running 12")
        output = self.provider.generate("12", "founder_assigned_synthesis", {
            "assignment": assignment,
            "reviewed_general_findings": findings,
            "available_tools": [],
            "instructions": "Return proposals only; do not execute tests or expand permissions. Report findings missing from any of the eleven disciplines as gaps.",
        }, TwelveReport)
        self._active(generation)  # Discard work if killed while the model was running.
        report = TwelveReport.model_validate(output)
        ids = {r["id"] for r in rows}
        for idea in report.ideas:
            if not set(idea.evidence_ids) <= ids or len(set(idea.evidence_ids)) != len(idea.evidence_ids):
                raise InvalidEvidence("12 cited missing or duplicate reviewed findings")
        item_id = identifier()
        # Lock before rechecking both shutdown and sources, not on the later
        # INSERT; otherwise another connection could revoke either in between.
        with self.store.transaction() as db:
            self._active(generation)
            current = {r["id"]: r["payload"] for r in db.execute("SELECT id,payload FROM findings")}
            if any(current.get(r["id"]) != r["payload"] for r in rows):
                raise InvalidEvidence("Reviewed evidence was retracted or changed during processing")
            db.execute("INSERT INTO twelve_reports VALUES(?,?,?,?)", (item_id, generation, report.model_dump_json(), now()))
            db.executemany("INSERT INTO twelve_report_sources VALUES(?,?,?)",
                           [(item_id, r["id"], hashlib.sha256(r["payload"].encode()).hexdigest()) for r in rows])
        return {"state": "proposed", "report_id": item_id,
                "audience": "founder_only", "report": report.model_dump(mode="json")}

    def reports(self, actor):
        self._founder(actor)
        result = []
        with self.store.transaction() as db:
            for row in db.execute("SELECT id,payload,created_at FROM twelve_reports ORDER BY created_at DESC"):
                sources = db.execute("""SELECT s.fingerprint,f.payload FROM twelve_report_sources s
                           LEFT JOIN findings f ON f.id=s.finding_id WHERE s.report_id=?""", (row["id"],)).fetchall()
                current = bool(sources) and all(
                    s["payload"] is not None and hashlib.sha256(s["payload"].encode()).hexdigest() == s["fingerprint"]
                    for s in sources)
                result.append({"id": row["id"], "created_at": row["created_at"],
                               "evidence_state": "current" if current else "needs_review",
                               "report": json.loads(row["payload"])})
        return result

    def erase_local_records(self, actor):
        """Disable 12 and logically delete its reports; not physical/backup erasure."""
        self._founder(actor)
        with self.store.transaction() as db:
            db.execute("UPDATE twelve_state SET enabled=0,generation=generation+1 WHERE singleton=1")
            db.execute("DELETE FROM twelve_reports")
        return {"disabled": True, "local_reports_deleted": True,
                "scope": "Logical deletion in this local database only; reviewed specialist knowledge is retained."}
