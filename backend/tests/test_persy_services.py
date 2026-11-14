import json
import time
from dataclasses import replace
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_coordinator import CoordinatorProvider, LocalSpecialists
from test_coordinator import coordinator_store as coordinator_fixture
from test_coordinator_services import specialist_payload
from test_life_profile_repository import profiles as profile_fixture
from test_persy import Connected, Model, fresh, privacy, proposal
from test_persy import persy_store as persy_fixture
from test_specialists_repository import evidence
from test_specialists_repository import specialist_store as specialist_fixture

from coordinator.runtime import Runtime as CoordinatorRuntime
from life_profile.bot import LifeProfileBot
from life_profile.models import AnalyseRequest, Decision, Proposal
from persy.main import app, runtime
from persy.models import Message, ProfileAnalysis
from persy.provider import OpenAIProvider
from persy.runtime import Runtime
from persy.services import Services, render_research
from persy.settings import Settings, get_settings
from specialists.models import BudgetExceeded, InvalidEvidence, ProviderUnavailable

persy_store = persy_fixture
profiles = profile_fixture
coordinator_store = coordinator_fixture
specialist_store = specialist_fixture


def keys():
    private = Ed25519PrivateKey.generate()
    public = (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private, public


def claims(**changes):
    now = int(time.time())
    return {
        "sub": "synthetic-member",
        "actor": "member",
        "domain": "*",
        "iss": "corepath-member-gateway",
        "aud": "corepath-persy",
        "scope": ["persy:chat"],
        "purpose": "conversation_reply",
        "iat": now,
        "nbf": now,
        "exp": now + 120,
        "jti": str(uuid4()),
        **changes,
    }


@pytest.fixture
def member_gateway(monkeypatch):
    monkeypatch.delenv("PERSY_DATABASE_URL", raising=False)
    get_settings.cache_clear()
    private, public = keys()
    app.dependency_overrides[get_settings] = lambda: Settings(gateway_public_key=public)

    class ChatDouble:
        def chat(self, member, conversation_id, message):
            return {"name": "Persy", "subject": member.subject}

    app.dependency_overrides[runtime] = ChatDouble
    try:
        with TestClient(app) as client:
            yield (
                client,
                lambda **changes: jwt.encode(claims(**changes), private, algorithm="EdDSA"),
            )
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def chat(client, token=None, body=None, headers=None):
    return client.post(
        f"/v1/persy/conversations/{uuid4()}/messages",
        headers=headers or ({"Authorization": "Bearer " + token} if token else {}),
        json=body or {"message": "Help me choose a practical next step"},
    )


def test_signed_member_identity_is_bound_to_the_request_and_private_headers(member_gateway):
    client, token = member_gateway
    response = chat(client, token())
    assert response.status_code == 200 and response.json()["subject"] == "synthetic-member"
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/health/live").json()["live_model_quality_verified"] is False


@pytest.mark.parametrize(
    "changes,status",
    [
        ({"actor": "founder"}, 403),
        ({"actor": "administrator"}, 403),
        ({"actor": "personal_ai"}, 403),
        ({"actor": "coordinator_ai"}, 403),
        ({"actor": "specialist_ai"}, 403),
        ({"aud": "corepath-coordinator"}, 401),
        ({"iss": "untrusted"}, 401),
        ({"scope": ["persy:read"]}, 403),
        ({"purpose": "conversation_review"}, 403),
        ({"domain": "nutrition"}, 403),
        ({"exp": 1}, 401),
        ({"exp": int(time.time()) + 10000}, 401),
        ({"iat": True}, 401),
        ({"scope": "persy:chat"}, 401),
    ],
)
def test_other_actors_invalid_signatures_and_wrong_scope_cannot_chat(
    member_gateway, changes, status
):
    client, token = member_gateway
    assert chat(client, token(**changes)).status_code == status


def test_browser_headers_shared_tokens_and_forged_subject_fields_are_not_identity(member_gateway):
    client, token = member_gateway
    for headers in (
        {},
        {"oai-authenticated-user-id": "founder"},
        {"Authorization": "Bearer internal-development-token"},
    ):
        assert chat(client, headers=headers).status_code == 401
    assert (
        chat(
            client, token(), {"message": "Change the caller", "subject": "another-member"}
        ).status_code
        == 422
    )
    assert client.post("/v1/specialists/nutrition/tasks", json={}).status_code == 404
    assert client.get("/docs").status_code == 404


@pytest.mark.parametrize(
    "target,change",
    [
        ("profile", None),
        ("research", None),
        ("profile", "wrong_owner"),
        ("research", "wrong_owner"),
        ("profile", "wrong_request"),
        ("profile", "overlong"),
        ("research", "wrong_audience"),
        ("profile", "unapproved"),
        ("profile", "redirect"),
    ],
)
def test_delegations_bind_owner_service_action_request_and_lifetime(monkeypatch, target, change):
    from persy.security import Member

    private, public = keys()
    member = Member(
        "synthetic-member", str(uuid4()), int(time.time()) + 180, "synthetic-member-assertion"
    )
    settings = Settings(
        exchange_url="https://gateway.example.test/exchange",
        exchange_token="synthetic-machine-secret",
        coordinator_url="https://coordinator.example.test",
        coordinator_public_key=public,
        profile_url="https://profile.example.test",
        profile_public_key=public,
        service_subject="synthetic-persy",
    )
    real_client, seen = httpx.Client, []

    def respond(request):
        seen.append(request)
        if request.url.host == "gateway.example.test":
            body = json.loads(request.content)
            assert body["member_capability"] == member.assertion
            assert request.headers["authorization"] == "Bearer synthetic-machine-secret"
            if change == "redirect":
                return httpx.Response(307, headers={"location": "https://untrusted.example.test"})
            profile = body["target"] == "life_profile"
            signed = claims(
                actor="personal_ai",
                sub="another-member"
                if change == "wrong_owner"
                else member.subject
                if profile
                else settings.service_subject,
                iss="corepath-personal-ai" if profile else "corepath-service-gateway",
                aud="wrong-audience"
                if change == "wrong_audience"
                else "corepath-life-profile"
                if profile
                else "corepath-coordinator",
                scope=["profile:context"] if profile else ["coordinator:research"],
                purpose="personalisation" if profile else "research_request",
                jti=str(uuid4()) if change == "wrong_request" else body["request_id"],
                exp=int(time.time()) + (240 if change == "overlong" else 120),
            )
            return httpx.Response(
                200, json={"capability": jwt.encode(signed, private, algorithm="EdDSA")}
            )
        assert member.assertion not in str(request.headers)
        assert "synthetic-machine-secret" not in str(request.headers)
        if target == "profile":
            assert request.url.path == "/v1/life-profile/context"
            item = {
                "id": str(uuid4()),
                "statement": "Prefers short explanations",
                "category": "personal_growth_development",
                "dimensions": ["self_identity"],
                "understanding_level": "developing_understanding"
                if change == "unapproved"
                else "confirmed_understanding",
            }
            return httpx.Response(200, json={"approved_understanding": [item]})
        assert json.loads(request.content) == proposal().model_dump(mode="json")
        assert "member" not in str(request.content) and "profile" not in str(request.content)
        return httpx.Response(
            200,
            json={
                "state": "needs_evidence",
                "audience": "personal_ai_internal",
                "review_required": True,
                "life_profile_access": False,
                "tasks": [],
                "conclusions": [],
                "options": [],
                "disagreements": [],
                "knowledge_gaps": ["More evidence is needed"],
                "clarifying_questions": [],
            },
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    services = Services(settings)

    def call():
        return (
            services.profile(member, "context")
            if target == "profile"
            else services.research(member, proposal(), uuid4())
        )

    if change:
        with pytest.raises((InvalidEvidence, ProviderUnavailable)):
            call()
        if change in ("wrong_owner", "wrong_request", "overlong", "wrong_audience", "redirect"):
            assert len(seen) == 1
    else:
        assert call()
        assert len(seen) == 2


def test_persy_model_uses_distinct_policy_strict_schema_no_tools_and_no_storage(monkeypatch):
    real_client, calls = httpx.Client, []
    reply = Model(research=True).reply({})

    def respond(request):
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": reply.model_dump_json()}],
                    }
                ],
            },
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    provider = OpenAIProvider(
        Settings(openai_api_key="synthetic-model-key", model="synthetic-model")
    )
    assert provider.reply({"member_message": "A synthetic question"}) == reply
    body = calls[0]
    assert body["store"] is False and "tools" not in body
    from bot_standards import STANDARD

    assert STANDARD in body["instructions"]
    assert "Your name is Persy" in body["instructions"]
    schema = body["text"]["format"]["schema"]
    for node in [schema, *schema["$defs"].values()]:
        if node.get("type") == "object":
            assert node["additionalProperties"] is False and set(node["required"]) == set(
                node["properties"]
            )
    with pytest.raises(BudgetExceeded):
        provider.reply({"message": "x" * 60001})
    assert len(calls) == 1


def test_missing_model_and_service_connections_fail_closed():
    with pytest.raises(ProviderUnavailable):
        OpenAIProvider(Settings()).reply({})
    with pytest.raises(ValidationError):
        Settings(profile_url="http://insecure.example.test")


def test_research_cards_rebuild_sources_and_reject_fabricated_references():
    result = specialist_payload()
    task_id = str(uuid4())
    finding = result["findings"][0]
    payload = {
        "state": "completed",
        "audience": "personal_ai_internal",
        "review_required": True,
        "life_profile_access": False,
        "tasks": [
            {
                "task_id": task_id,
                "domain": "nutrition",
                "phase": "initial",
                "rationale": "Relevant evidence",
                "state": "completed",
                "result": result,
                "error_code": None,
            }
        ],
        "conclusions": [
            {
                "statement": "A limited synthetic conclusion",
                "confidence": "high",
                "limitations": "Synthetic only",
                "evidence": [{"task_id": task_id, "finding_index": 0, "finding": finding}],
            }
        ],
        "options": [],
        "disagreements": [],
        "knowledge_gaps": [],
    }
    rendered = render_research(payload)
    assert rendered["findings"][0]["confidence"] == "low"
    assert rendered["findings"][0]["citations"] == finding["citations"]
    assert rendered["assessed_domains"] == ["nutrition"]
    assert rendered["full_team_assessed"] is False
    payload["full_team_assessed"] = True
    with pytest.raises(InvalidEvidence, match="full-team"):
        render_research(payload)
    payload["full_team_assessed"] = False
    payload["conclusions"][0]["evidence"][0]["task_id"] = str(uuid4())
    with pytest.raises(InvalidEvidence):
        render_research(payload)


def test_persy_bridges_selected_user_messages_to_real_profile_proposals_and_owner_decisions(
    persy_store, profiles
):
    repo, _, member, _, settings = persy_store
    profile_store, _, owner, _, consent = profiles
    member = replace(member, subject=owner, request_id=str(uuid4()))
    repo.set_privacy(member, privacy(history_enabled=True, profile_context_enabled=True))
    conversation = UUID(repo.create_conversation(fresh(member), settings)["conversation_id"])

    class ProfileModel:
        def propose(self, context):
            message = context["messages"][0]
            return Proposal.model_validate(
                {
                    "observations": [
                        {
                            "category": "personal_growth_development",
                            "dimensions": ["self_identity"],
                            "kind": "user_statement",
                            "statement": "Prefers short answers",
                            "evidence": [
                                {"message_id": message["message_id"], "quote": message["content"]}
                            ],
                            "confidence": "low",
                            "confidence_reason": "A single explicit statement",
                            "sensitive": False,
                            "collection_reason": "Adapt communication",
                        }
                    ],
                    "follow_up": None,
                }
            )

    class ProfileBridge(Connected):
        def profile(self, caller, action, body=None, item_id=None):
            self.profile_calls.append((caller.subject, action))
            if action == "context":
                return profile_store.context(caller.subject, caller.request_id)
            if action == "analyse":
                return LifeProfileBot(profile_store, ProfileModel()).analyse(
                    caller.subject, AnalyseRequest.model_validate(body), caller.request_id
                )
            if action == "decision":
                return profile_store.decide(
                    caller.subject, item_id, Decision.model_validate(body), caller.request_id
                )
            return profile_store.snapshot(caller.subject, caller.request_id, owner_review=True)

    model, connected = Model(), ProfileBridge()
    persy = Runtime(repo, model, connected, settings)
    reply = persy.chat(fresh(member), conversation, Message(message="I prefer short answers"))
    assert connected.profile_calls == []
    analysed = persy.profile_action(
        fresh(member),
        "analyse",
        analysis=ProfileAnalysis(turn_ids=[UUID(reply["turn_id"])], purpose=consent.purpose),
    )
    item = analysed["proposals"][0]
    assert item["state"] == "pending" and item["shared_with_personal_ai"] is False
    persy.chat(
        fresh(member),
        conversation,
        Message(message="Use my shared context", use_profile_context=True),
    )
    assert model.calls[-1]["approved_profile_context"] == []
    persy.profile_action(
        fresh(member),
        "decision",
        {"expected_version": 1, "action": "accept", "share_with_personal_ai": True},
        UUID(item["id"]),
    )
    persy.chat(
        fresh(member),
        conversation,
        Message(message="Use the understanding I accepted", use_profile_context=True),
    )
    assert model.calls[-1]["approved_profile_context"][0]["statement"] == "Prefers short answers"


def test_persy_approved_question_runs_through_real_coordinator_and_specialist(
    persy_store, coordinator_store
):
    repo, _, member, conversation, settings = persy_store
    coordinator, specialists, libraries, conn, caller, coordinator_settings = coordinator_store
    evidence(conn, libraries["learning-intelligence"])
    network = CoordinatorRuntime(
        coordinator,
        CoordinatorProvider(["learning-intelligence"]),
        LocalSpecialists(specialists),
        coordinator_settings,
    )

    class Bridge(Connected):
        def research(self, owner, question, operation_id):
            self.research_calls.append(question.model_dump(mode="json"))
            return render_research(
                network.execute(replace(caller, request_id=str(operation_id)), question)
            )

    bridge = Bridge()
    persy = Runtime(repo, Model(research=True), bridge, settings)
    proposed = persy.chat(
        fresh(member),
        conversation,
        Message(message="Private personal marker: please investigate learning"),
    )
    assert bridge.research_calls == []
    result = persy.research(fresh(member), conversation, UUID(proposed["research_proposal"]["id"]))
    assert result["state"] == "completed" and result["name"] == "Persy"
    assert result["findings"][0]["citations"][0]["canonical_url"] == "https://example.org/evidence"
    assert result["findings"][0]["confidence"] == "low"
    assert bridge.research_calls == [proposal().model_dump(mode="json")]
    assert "Private personal marker" not in str(
        conn.execute("SELECT row_to_json(r) FROM coordinator_runs r").fetchall()
    )
