import json

import httpx
import pytest
from pydantic import ValidationError

from bot_standards import STANDARD
from life_profile.bot import LifeProfileBot
from life_profile.models import AnalyseRequest, Category, Consent, Proposal
from life_profile.provider import InvalidProposal, OpenAIProvider, ProviderUnavailable
from life_profile.repository import ConsentRequired
from life_profile.settings import Settings


def consent(**changes):
    values = {
        "analysis_enabled": True,
        "external_model_processing": True,
        "categories": [Category.GROWTH],
        "purpose": "Adapt communication",
    }
    return Consent(**(values | changes))


def request(**changes):
    return AnalyseRequest.model_validate(
        {
            "purpose": "Adapt communication",
            "messages": [
                {
                    "message_id": "message-1",
                    "conversation_id": "conversation-1",
                    "source_type": "conversation",
                    "speaker": "user",
                    "content": "I prefer short answers.",
                }
            ],
        }
        | changes
    )


def proposal(**changes):
    observation = {
        "category": "personal_growth_development",
        "dimensions": ["mental"],
        "kind": "user_statement",
        "statement": "Prefers concise explanations.",
        "evidence": [{"message_id": "message-1", "quote": "I prefer short answers."}],
        "confidence": "moderate",
        "confidence_reason": "Explicit preference in the supplied message.",
        "sensitive": False,
        "collection_reason": "Adapt the level of detail in responses.",
    }
    return Proposal.model_validate({"observations": [observation | changes], "follow_up": None})


class MemoryRepository:
    def __init__(self, permission=None, items=None):
        self.consent = permission or consent()
        self.items = items or []
        self.saved = []

    def snapshot(self, subject, request_id):
        return {"consent": self.consent, "consent_revision": 1, "items": self.items}

    def propose(self, subject, payloads, consent_revision, request_id):
        self.saved.extend(payloads)
        return [{"state": "pending", **p} for p in payloads]


class ModelDouble:
    def __init__(self, output=None):
        self.output = output or proposal()
        self.inputs = []

    def propose(self, context):
        self.inputs.append(context)
        return self.output


def test_analysis_creates_only_unshared_pending_proposals():
    store, model = MemoryRepository(), ModelDouble()
    result = LifeProfileBot(store, model).analyse("synthetic-person", request(), "test-request")
    assert result["review_required"] is True
    assert result["follow_up"] is None
    assert result["proposals"][0]["state"] == "pending"
    assert store.saved[0]["understanding_level"] == "known_information"
    assert store.saved[0]["shared_with_personal_ai"] is False
    assert store.saved[0]["source_context"][0]["conversation_id"] == "conversation-1"
    assert "subject" not in model.inputs[0]


@pytest.mark.parametrize(
    "permission",
    [
        consent(analysis_enabled=False),
        consent(external_model_processing=False),
        consent(purpose="Another purpose"),
    ],
)
def test_model_is_not_called_without_permission_for_this_purpose(permission):
    store, model = MemoryRepository(permission), ModelDouble()
    with pytest.raises(ConsentRequired):
        LifeProfileBot(store, model).analyse("synthetic-person", request(), "test-request")
    assert model.inputs == []
    assert store.saved == []


@pytest.mark.parametrize(
    "evidence",
    [
        [{"message_id": "invented", "quote": "I prefer short answers."}],
        [{"message_id": "message-1", "quote": "I have an anxiety disorder."}],
    ],
)
def test_invented_sources_or_quotes_never_reach_storage(evidence):
    store = MemoryRepository()
    with pytest.raises(InvalidProposal):
        LifeProfileBot(store, ModelDouble(proposal(evidence=evidence))).analyse(
            "synthetic-person", request(), "test-request"
        )
    assert store.saved == []


def test_one_conversation_cannot_establish_a_repeated_pattern():
    store = MemoryRepository()
    with pytest.raises(InvalidProposal, match="separate conversations"):
        LifeProfileBot(store, ModelDouble(proposal(kind="observed_pattern"))).analyse(
            "synthetic-person", request(), "test-request"
        )
    assert store.saved == []


def test_distinct_conversations_can_support_a_provisional_pattern():
    inputs = request()
    second = inputs.messages[0].model_copy(
        update={"message_id": "message-2", "conversation_id": "conversation-2"}
    )
    inputs.messages.append(second)
    output = proposal(
        kind="observed_pattern",
        evidence=[
            {"message_id": "message-1", "quote": "I prefer short answers."},
            {"message_id": "message-2", "quote": "I prefer short answers."},
        ],
    )
    result = LifeProfileBot(MemoryRepository(), ModelDouble(output)).analyse(
        "synthetic-person", inputs, "test-request"
    )
    assert result["proposals"][0]["state"] == "pending"
    assert result["proposals"][0]["understanding_level"] == "observed_pattern"


def test_unconsented_categories_are_rejected():
    store = MemoryRepository()
    with pytest.raises(InvalidProposal):
        LifeProfileBot(store, ModelDouble(proposal(category="health_wellbeing"))).analyse(
            "synthetic-person", request(), "test-request"
        )
    assert store.saved == []


def test_health_is_sensitive_even_if_model_mislabels_it():
    store = MemoryRepository(consent(categories=[Category.HEALTH]))
    result = LifeProfileBot(store, ModelDouble(proposal(category="health_wellbeing"))).analyse(
        "synthetic-person", request(), "test-request"
    )
    assert result["proposals"] == []
    assert store.saved == []


def test_model_cannot_output_confirmed_understanding():
    with pytest.raises(ValidationError):
        proposal(kind="confirmed_understanding")


def test_private_journal_and_non_user_sources_are_rejected():
    raw = request().model_dump(mode="json")
    raw["messages"][0]["source_type"] = "private_journal"
    with pytest.raises(ValidationError):
        AnalyseRequest.model_validate(raw)
    raw["messages"][0]["source_type"] = "conversation"
    raw["messages"][0]["speaker"] = "assistant"
    with pytest.raises(ValidationError):
        AnalyseRequest.model_validate(raw)


def test_only_accepted_in_scope_understanding_is_sent_to_model():
    common = {
        "statement": "Approved preference",
        "category": Category.GROWTH,
        "dimensions": ["mental"],
        "user_corrected": False,
        "sensitive": False,
    }
    store = MemoryRepository(
        items=[
            common | {"state": "accepted"},
            common | {"state": "pending", "statement": "Unreviewed guess"},
            common | {"state": "rejected", "statement": "Rejected guess"},
            common | {"state": "accepted", "category": Category.CAREER},
        ]
    )
    model = ModelDouble()
    LifeProfileBot(store, model).analyse("synthetic-person", request(), "test-request")
    assert len(model.inputs[0]["previously_accepted_understanding"]) == 1
    assert (
        model.inputs[0]["previously_accepted_understanding"][0]["statement"]
        == "Approved preference"
    )


def test_unconfigured_model_never_falls_back_to_fabricated_inference():
    with pytest.raises(ProviderUnavailable):
        OpenAIProvider(Settings(openai_api_key=None, model=None)).propose({})


def test_provider_uses_structured_output_without_storing_responses(monkeypatch):
    captured = {}

    def handle(req):
        captured.update(json.loads(req.content))
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": proposal().model_dump_json()}],
                    }
                ],
            },
        )

    real_client = httpx.Client
    monkeypatch.setattr(
        "life_profile.provider.httpx.Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    output = OpenAIProvider(
        Settings(model="configured-test-model", openai_api_key="synthetic-key")
    ).propose({})
    assert output.observations[0].kind == "user_statement"
    assert captured["store"] is False
    assert STANDARD in captured["instructions"]
    assert "write accepted profile facts" in captured["instructions"]
    assert captured["text"]["format"]["strict"] is True
    assert captured["text"]["format"]["schema"]["additionalProperties"] is False


def test_provider_failure_does_not_echo_upstream_private_content(monkeypatch):
    real_client = httpx.Client
    transport = httpx.MockTransport(
        lambda _req: httpx.Response(500, text="private synthetic disclosure")
    )
    monkeypatch.setattr(
        "life_profile.provider.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    with pytest.raises(ProviderUnavailable) as error:
        OpenAIProvider(
            Settings(model="configured-test-model", openai_api_key="synthetic-key")
        ).propose({})
    assert "private synthetic disclosure" not in str(error.value)


def test_a_sensitive_follow_up_is_not_requested_without_sensitive_consent():
    output = Proposal.model_validate(
        {
            "observations": [],
            "follow_up": {
                "question": "What health goals are relevant?",
                "reason": "Understand the selected goal.",
                "category": "health_wellbeing",
            },
        }
    )
    store = MemoryRepository(consent(categories=[Category.HEALTH]))
    result = LifeProfileBot(store, ModelDouble(output)).analyse(
        "synthetic-person", request(), "test-request"
    )
    assert result["follow_up"] is None
