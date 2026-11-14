"""Founder-controlled synthesis of reviewed, explicitly public general findings."""

import json

from pydantic import Field

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
        with self.store.db as db:
            db.execute("INSERT INTO findings VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET domain=excluded.domain,payload=excluded.payload,reviewed_by=excluded.reviewed_by,reviewed_at=excluded.reviewed_at",
                       (finding.id, finding.domain.value, finding.model_dump_json(), reviewer, now()))

    def retract(self, finding_id):
        with self.store.db as db:
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
        with self.store.db as db:
            db.execute("UPDATE twelve_state SET enabled=1,generation=generation+1 WHERE singleton=1")

    def shutdown(self, actor):
        self._founder(actor)
        with self.store.db as db:
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
        # Retraction during a request invalidates the result before saving.
        current = {r["id"]: r["payload"] for r in self.store.db.execute("SELECT id,payload FROM findings")}
        if any(current.get(r["id"]) != r["payload"] for r in rows):
            raise InvalidEvidence("Reviewed evidence was retracted or changed during processing")
        item_id = identifier()
        with self.store.db as db:
            self._active(generation)
            db.execute("INSERT INTO twelve_reports VALUES(?,?,?,?)", (item_id, generation, report.model_dump_json(), now()))
        return {"state": "proposed", "report_id": item_id,
                "audience": "founder_only", "report": report.model_dump(mode="json")}

    def reports(self, actor):
        self._founder(actor)
        return [{"id": r["id"], "created_at": r["created_at"], "report": json.loads(r["payload"])}
                for r in self.store.db.execute("SELECT id,payload,created_at FROM twelve_reports ORDER BY created_at DESC")]

    def erase_local_records(self, actor):
        """Disable 12 and logically delete its reports; not physical/backup erasure."""
        self.shutdown(actor)
        with self.store.db as db:
            db.execute("DELETE FROM twelve_reports")
        return {"disabled": True, "local_reports_deleted": True,
                "scope": "Logical deletion in this local database only; reviewed specialist knowledge is retained."}
