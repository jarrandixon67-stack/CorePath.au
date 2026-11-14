import json
from typing import Literal
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException
from pydantic import Field, ValidationError

from coordinator.limits import MAX_SPECIALIST_CALLS
from coordinator.models import SpecialistResult
from life_profile.models import Category, Dimension
from persy.models import Missing, PrivacyRequired
from persy.settings import Settings
from specialists.models import (
    BudgetExceeded,
    InvalidEvidence,
    ProviderUnavailable,
    RunConflict,
    StrictModel,
)
from specialists.registry import Domain
from specialists.security import validate_capability

PROFILE_ACTIONS = {
    "context": ("GET", "/context", "profile:context", "personalisation"),
    "review": ("GET", "/review", "profile:review", "owner_review"),
    "consent": ("PUT", "/consent", "profile:consent", "owner_control"),
    "analyse": ("POST", "/analyse", "profile:analyse", "profile_analysis"),
    "decision": ("POST", "/items/{item_id}/decision", "profile:decide", "owner_control"),
    "delete_item": ("DELETE", "/items/{item_id}", "profile:delete", "owner_control"),
    "delete_profile": ("DELETE", "", "profile:delete", "owner_control"),
}


class ApprovedUnderstanding(StrictModel):
    id: UUID
    statement: str = Field(min_length=3, max_length=1000)
    category: Category
    dimensions: list[Dimension] = Field(min_length=1, max_length=8)
    understanding_level: str = Field(pattern="^confirmed_understanding$")


class ApprovedContext(StrictModel):
    approved_understanding: list[ApprovedUnderstanding] = Field(max_length=50)


class TaskEnvelope(StrictModel):
    task_id: UUID
    domain: Domain
    phase: Literal["initial", "collaboration"]
    rationale: str = Field(max_length=600)
    state: Literal["completed", "needs_evidence", "failed"]
    result: SpecialistResult | None
    error_code: str | None = Field(max_length=100)


def render_research(payload):
    """Present validated evidence; do not run another ungrounded paraphrase."""
    if (
        not isinstance(payload, dict)
        or payload.get("audience") != "personal_ai_internal"
        or payload.get("review_required") is not True
        or payload.get("life_profile_access") is not False
        or payload.get("state")
        not in ("completed", "partial", "needs_evidence", "needs_clarification", "failed")
    ):
        raise InvalidEvidence("Invalid Coordinator envelope")
    tasks = payload.get("tasks", [])
    if not isinstance(tasks, list) or len(tasks) > MAX_SPECIALIST_CALLS:
        raise InvalidEvidence("Invalid Coordinator task count")
    tasks = [TaskEnvelope.model_validate(task) for task in tasks]
    if len({task.task_id for task in tasks}) != len(tasks) or len(
        {task.domain for task in tasks}
    ) != len(tasks):
        raise InvalidEvidence("Duplicate Coordinator tasks")
    catalog, gaps, conflicts = {}, [], []
    for task in tasks:
        if (task.result is not None) != (task.state != "failed"):
            raise InvalidEvidence("Coordinator task state and result disagree")
        if not task.result:
            continue
        if task.domain != task.result.specialist.value or task.state != task.result.state:
            raise InvalidEvidence("Mismatched Coordinator task evidence")
        for index, finding in enumerate(task.result.findings):
            catalog[(str(task.task_id), index)] = finding.model_dump(mode="json")
        gaps.extend(task.result.knowledge_gaps)
        conflicts.extend(item.description for item in task.result.contradictions)

    def evidence(items):
        if not isinstance(items, list) or not 1 <= len(items) <= 8:
            raise InvalidEvidence("Invalid evidence references")
        found = []
        for item in items:
            key = (item.get("task_id"), item.get("finding_index"))
            original = catalog.get(key)
            if not original or item.get("finding") != original:
                raise InvalidEvidence("Coordinator evidence did not match its actual task")
            found.append(original)
        return found

    rank = {"low": 0, "moderate": 1, "high": 2}
    cards = []
    for item in payload.get("conclusions", []):
        if (
            len(cards) >= 6
            or not isinstance(item.get("statement"), str)
            or not 3 <= len(item["statement"]) <= 1200
            or item.get("confidence") not in rank
        ):
            raise InvalidEvidence("Invalid conclusion")
        refs = evidence(item.get("evidence"))
        confidence = min([rank[item["confidence"]]] + [rank[f["confidence"]] for f in refs])
        cards.append(
            {
                "statement": item["statement"],
                "confidence": next(k for k, v in rank.items() if v == confidence),
                "limitations": item.get("limitations"),
                "citations": [c for finding in refs for c in finding["citations"]],
            }
        )
    if not cards:
        cards = list(catalog.values())
    if payload["state"] == "completed" and (
        not catalog
        or not payload.get("conclusions")
        or any(task.state != "completed" for task in tasks)
    ):
        raise InvalidEvidence("The Coordinator claimed completion without complete evidence")
    if payload["state"] in ("failed", "needs_evidence", "needs_clarification") and catalog:
        raise InvalidEvidence("Coordinator state and findings disagree")
    if payload["state"] == "needs_clarification" and tasks:
        raise InvalidEvidence("Coordinator dispatched before clarification")
    full_team_assessed = len(tasks) == MAX_SPECIALIST_CALLS and all(task.result for task in tasks)
    if "full_team_assessed" in payload and payload["full_team_assessed"] is not full_team_assessed:
        raise InvalidEvidence("Coordinator full-team claim did not match its actual tasks")
    options = []
    for item in payload.get("options", []):
        if (
            len(options) >= 4
            or not isinstance(item.get("action"), str)
            or not 3 <= len(item["action"]) <= 600
        ):
            raise InvalidEvidence("Invalid practical option")
        refs = evidence(item.get("evidence"))
        options.append(
            {
                "action": item["action"],
                "limitations": item.get("limitations"),
                "citations": [c for finding in refs for c in finding["citations"]],
            }
        )
    for disagreement in payload.get("disagreements", []):
        evidence(disagreement.get("supporting"))
        evidence(disagreement.get("challenging"))
        conflicts.append(disagreement.get("description"))
    gaps.extend(payload.get("knowledge_gaps", []))
    questions = payload.get("clarifying_questions", [])
    if (
        any(not isinstance(text, str) or len(text) > 600 for text in gaps + conflicts + questions)
        or len(gaps) > 66
        or len(conflicts) > 40
        or len(questions) > 3
    ):
        raise InvalidEvidence("Unbounded Coordinator text")
    return {
        "state": payload["state"],
        "message": "Here is the research CorePath returned. These are draft findings for review."
        if cards
        else "CorePath did not return supported findings for this question.",
        "findings": cards,
        "options": options,
        "knowledge_gaps": list(dict.fromkeys(gaps)),
        "disagreements": list(dict.fromkeys(conflicts)),
        "clarifying_questions": questions,
        "review_required": True,
        "assessed_domains": [task.domain.value for task in tasks if task.result],
        "full_team_assessed": full_team_assessed,
        "peer_review_round_executed": False,
        "evidence_note": "Citations establish traceability, not truth or applicability. Confidence is an uncalibrated model judgement.",
    }


class Services:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _request(self, method, url, token, body=None, *, limit=262144):
        try:
            with (
                httpx.Client(
                    timeout=self.settings.service_timeout_seconds, follow_redirects=False
                ) as client,
                client.stream(
                    method, url, headers={"Authorization": "Bearer " + token}, json=body
                ) as response,
            ):
                if response.status_code == 403:
                    raise PrivacyRequired
                if response.status_code == 404:
                    raise Missing
                if response.status_code == 409:
                    raise RunConflict
                if response.status_code == 429:
                    raise BudgetExceeded
                response.raise_for_status()
                chunks, length = [], 0
                for chunk in response.iter_bytes():
                    length += len(chunk)
                    if length > limit:
                        raise InvalidEvidence("Service response exceeded its limit")
                    chunks.append(chunk)
                return json.loads(b"".join(chunks)) if chunks else None
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailable from exc

    def _token(self, member, target, action, request_id, scope, purpose):
        settings = self.settings
        if not settings.exchange_url or not settings.exchange_token:
            raise ProviderUnavailable
        response = self._request(
            "POST",
            settings.exchange_url,
            settings.exchange_token,
            {
                "target": target,
                "action": action,
                "request_id": str(request_id),
                "member_capability": member.assertion,
            },
            limit=16384,
        )
        if (
            not isinstance(response, dict)
            or set(response) != {"capability"}
            or not isinstance(response["capability"], str)
            or len(response["capability"]) > 8192
        ):
            raise InvalidEvidence("Invalid capability exchange")
        profile = target == "life_profile"
        try:
            capability = validate_capability(
                response["capability"],
                public_key=settings.profile_public_key
                if profile
                else settings.coordinator_public_key,
                issuer=settings.profile_issuer if profile else settings.coordinator_issuer,
                audience=settings.profile_audience if profile else settings.coordinator_audience,
                actor="personal_ai",
                scope=scope,
                purpose=purpose,
                domain="*",
            )
        except HTTPException as exc:
            raise ProviderUnavailable from exc
        if (
            capability.expires_at > member.expires_at
            or capability.subject != (member.subject if profile else settings.service_subject)
            or capability.request_id != str(request_id)
        ):
            raise InvalidEvidence("Delegated capability subject or request did not match")
        return response["capability"]

    def profile(self, member, action, body=None, item_id=None):
        if not self.settings.profile_url:
            raise ProviderUnavailable
        method, path, scope, purpose = PROFILE_ACTIONS[action]
        if "{item_id}" in path:
            path = path.format(item_id=str(UUID(str(item_id))))
        token = self._token(member, "life_profile", action, uuid4(), scope, purpose)
        value = self._request(
            method, self.settings.profile_url.rstrip("/") + "/v1/life-profile" + path, token, body
        )
        if action == "context":
            try:
                return ApprovedContext.model_validate(value).model_dump(mode="json")[
                    "approved_understanding"
                ]
            except ValidationError as exc:
                raise InvalidEvidence("Profile service returned unapproved context") from exc
        return value

    def research(self, member, proposal, operation_id):
        if not self.settings.coordinator_url:
            raise ProviderUnavailable
        token = self._token(
            member,
            "coordinator",
            "research",
            operation_id,
            "coordinator:research",
            "research_request",
        )
        try:
            response = self._request(
                "POST",
                self.settings.coordinator_url.rstrip("/") + "/v1/coordinator/research",
                token,
                proposal.model_dump(mode="json"),
            )
            return render_research(response)
        except (ValidationError, TypeError, KeyError, AttributeError) as exc:
            raise InvalidEvidence("Coordinator response failed evidence validation") from exc
