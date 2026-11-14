from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_coordinator import CoordinatorProvider
from test_persy import Model

from coordinator.models import ResearchRequest, SpecialistResult
from coordinator.runtime import Runtime as Coordinator
from coordinator.settings import Settings
from persy.main import app
from persy.models import Message
from persy.runtime import Runtime as Persy
from specialists.models import BudgetExceeded
from specialists.registry import Domain


class MemoryCoordinatorStore:
    def __init__(self, capacity=11):
        self.capacity, self.used = capacity, 0

    def start(self, *args):
        return uuid4()

    def check(self, *args):
        return {"max_calls": self.capacity, "calls_used": self.used}

    def save_plan(self, *args):
        pass

    def reserve(self, *args):
        self.used += 1
        return uuid4()

    def task_done(self, *args):
        pass

    def finish(self, *args):
        pass

    def fail(self, *args):
        pass


class EmptySpecialists:
    def __init__(self):
        self.calls = []

    def dispatch(self, assignment, task_id):
        self.calls.append(assignment.domain)
        return SpecialistResult(
            run_id=uuid4(),
            state="needs_evidence",
            specialist=assignment.domain,
            findings=[],
            options=[],
            contradictions=[],
            knowledge_gaps=["No approved evidence."],
            collaboration_requests=[],
            collaboration_executed=False,
            review_required=True,
            audience="coordinator_internal",
            life_profile_access=False,
        )


def test_all_eleven_permissions_in_auto_do_not_force_all_eleven_calls():
    store, specialists = MemoryCoordinatorStore(), EmptySpecialists()
    result = Coordinator(
        store, CoordinatorProvider([Domain.NUTRITION]), specialists, Settings()
    ).execute(
        None,
        ResearchRequest(
            question="Investigate this general question.", allowed_domains=list(Domain)
        ),
    )
    assert specialists.calls == [Domain.NUTRITION]
    assert result["assessed_domains"] == [Domain.NUTRITION.value]
    assert not result["full_team_requested"] and not result["full_team_assessed"]
    assert result["budget_is_ceiling_not_target"]


def test_auto_all_eleven_actual_coverage_matches_persy_report_contract():
    result = Coordinator(
        MemoryCoordinatorStore(), CoordinatorProvider(list(Domain)), EmptySpecialists(), Settings()
    ).execute(
        None,
        ResearchRequest(
            question="Investigate every relevant discipline.", allowed_domains=list(Domain)
        ),
    )
    assert result["full_team_assessed"] and not result["full_team_requested"]
    from persy.services import render_research

    assert render_research(result)["full_team_assessed"]


def test_explicit_full_team_cannot_silently_downgrade_to_lower_server_capacity():
    specialists = EmptySpecialists()
    with pytest.raises(BudgetExceeded):
        Coordinator(
            MemoryCoordinatorStore(2),
            CoordinatorProvider([Domain.NUTRITION]),
            specialists,
            Settings(),
        ).execute(
            None,
            ResearchRequest(
                question="An explicitly approved full-team question.",
                allowed_domains=list(Domain),
                specialist_mode="full",
            ),
        )
    assert not specialists.calls


class MemoryPersyStore:
    def begin(self, *args):
        return (
            uuid4(),
            {
                "profile_context_enabled": False,
                "history_enabled": False,
                "communication_style": "plain",
            },
            None,
        )

    def check(self, *args):
        pass

    def finish(self, member, operation, turn, proposal, settings):
        self.proposal = proposal
        return {"payload": proposal.model_dump(mode="json")}

    def fail(self, *args):
        pass


@pytest.mark.parametrize("ceiling", [1, 2, 10, 11])
def test_member_ceiling_overrides_model_proposal_and_keeps_all_fields_available(ceiling):
    store, model = MemoryPersyStore(), Model(research=True)
    result = Persy(store, model, SimpleNamespace(), SimpleNamespace()).chat(
        None, uuid4(), Message(message="A synthetic general question.", max_specialists=ceiling)
    )
    assert store.proposal.specialist_mode == "auto"
    assert store.proposal.max_specialist_calls == ceiling
    assert set(store.proposal.allowed_domains) == set(Domain)
    assert result["research_proposal"]["payload"] == store.proposal.model_dump(mode="json")
    assert model.calls[0]["specialist_preferences"]["max_specialists"] == ceiling


def test_explicit_full_team_needs_complete_permission_but_default_is_auto():
    assert Message(message="Hello.").specialist_mode == "auto"
    with pytest.raises(ValidationError):
        Message(message="Hello.", specialist_mode="full", max_specialists=2)
    with pytest.raises(ValidationError):
        Message(message="Hello.", max_specialists=True)
    with pytest.raises(ValidationError):
        ResearchRequest(
            question="A full-team request.",
            allowed_domains=[Domain.NUTRITION],
            specialist_mode="full",
        )


def test_base_offer_is_1999_aud_minor_units_without_unlimited_or_live_checkout_claims():
    with TestClient(app) as client:
        response = client.get("/v1/persy/membership")
    assert response.status_code == 200
    offer = response.json()
    assert (offer["price_minor"], offer["currency"], offer["billing_interval"]) == (
        1999,
        "AUD",
        "month",
    )
    assert offer["gst_included"] and offer["specialist_mode"] == "auto"
    assert offer["all_eleven_specialists_available"]
    assert not offer["checkout_enabled"] and not offer["unlimited_ai_usage"]
