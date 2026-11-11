import json
import time
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_coordinator import assignment
from test_specialists_runtime import excerpt, proposal_for

from coordinator.evaluate import load_cases
from coordinator.evaluate import main as evaluate
from coordinator.main import app, repository, runtime
from coordinator.models import Plan
from coordinator.provider import OpenAIProvider
from coordinator.settings import Settings, get_settings
from coordinator.transport import HTTPSpecialistClient
from specialists.models import BudgetExceeded, InvalidEvidence, ProviderUnavailable
from specialists.registry import Domain
from specialists.runtime import grounded_result


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
        "sub": "synthetic-personal-ai",
        "actor": "personal_ai",
        "domain": "*",
        "scope": ["coordinator:research"],
        "purpose": "research_request",
        "iss": "corepath-service-gateway",
        "aud": "corepath-coordinator",
        "iat": now,
        "nbf": now,
        "exp": now + 120,
        "jti": str(uuid4()),
        **changes,
    }


@pytest.fixture
def coordinator_gateway(monkeypatch):
    monkeypatch.delenv("COORDINATOR_DATABASE_URL", raising=False)
    get_settings.cache_clear()
    private, public = keys()
    app.dependency_overrides[get_settings] = lambda: Settings(gateway_public_key=public)

    class ServiceDouble:
        def execute(self, caller, request):
            return {"subject": caller.subject, "state": "needs_evidence"}

        def read(self, caller, run_id, settings):
            return {"id": str(run_id), "subject": caller.subject}

    app.dependency_overrides[runtime] = ServiceDouble
    app.dependency_overrides[repository] = ServiceDouble
    try:
        with TestClient(app) as client:
            yield (
                client,
                lambda **changes: jwt.encode(claims(**changes), private, algorithm="EdDSA"),
            )
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def post(client, token=None, headers=None):
    return client.post(
        "/v1/coordinator/research",
        headers=headers or ({"Authorization": "Bearer " + token} if token else {}),
        json={
            "question": "Investigate general learning evidence",
            "allowed_domains": [Domain.LEARNING.value],
        },
    )


def test_only_signed_personal_ai_requests_and_scoped_status_access_are_accepted(
    coordinator_gateway,
):
    client, token = coordinator_gateway
    response = post(client, token())
    assert response.status_code == 200 and response.json()["subject"] == "synthetic-personal-ai"
    assert response.headers["cache-control"] == "no-store"
    status = client.get(
        f"/v1/coordinator/research/{uuid4()}",
        headers={
            "Authorization": "Bearer "
            + token(scope=["coordinator:read"], purpose="research_status")
        },
    )
    assert status.status_code == 200


@pytest.mark.parametrize(
    "changes,status",
    [
        ({"actor": "founder"}, 403),
        ({"actor": "administrator"}, 403),
        ({"actor": "specialist_ai"}, 403),
        ({"actor": "coordinator_ai"}, 403),
        ({"actor": "life_profiling_ai"}, 403),
        ({"aud": "corepath-specialists"}, 401),
        ({"scope": ["specialist:dispatch"]}, 403),
        ({"purpose": "research_status"}, 403),
        ({"domain": "nutrition"}, 403),
        ({"exp": 1}, 401),
        ({"exp": int(time.time()) + 10000}, 401),
        ({"iss": "unknown"}, 401),
    ],
)
def test_other_roles_or_wrongly_scoped_capabilities_cannot_coordinate(
    coordinator_gateway, changes, status
):
    client, token = coordinator_gateway
    assert post(client, token(**changes)).status_code == status


def test_browser_headers_shared_tokens_and_profile_routes_cannot_bypass_the_gateway(
    coordinator_gateway,
):
    client, _ = coordinator_gateway
    for headers in (
        {},
        {"oai-authenticated-user-id": "founder"},
        {"Authorization": "Bearer internal-development-token"},
    ):
        assert post(client, headers=headers).status_code == 401
    assert client.get("/v1/life-profile").status_code == 404
    assert client.post("/v1/chat", json={}).status_code == 404
    assert client.get("/health/live").json()["live_model_quality_verified"] is False


def specialist_payload(domain=Domain.NUTRITION):
    section = excerpt()
    return {
        "run_id": str(uuid4()),
        "state": "completed",
        **grounded_result(domain, proposal_for(section), [section]),
    }


@pytest.mark.parametrize(
    "change",
    [
        None,
        "wrong_domain",
        "wrong_subject",
        "wrong_request",
        "wrong_result",
        "redirect",
        "accepted_knowledge",
        "oversize",
    ],
)
def test_exchange_is_bound_to_request_and_service_and_never_follows_redirects(monkeypatch, change):
    private, public = keys()
    seen = []
    task_id = uuid4()
    real_client = httpx.Client

    def respond(request):
        seen.append(request)
        if request.url.host == "gateway.example.test":
            body = json.loads(request.content)
            assert body["request_id"] == str(task_id) and body["domain"] == "nutrition"
            assert request.headers["authorization"] == "Bearer synthetic-exchange-secret"
            if change == "redirect":
                return httpx.Response(307, headers={"location": "https://untrusted.example.test"})
            token = jwt.encode(
                claims(
                    sub="other-service" if change == "wrong_subject" else "synthetic-coordinator",
                    actor="coordinator_ai",
                    aud="corepath-specialists",
                    domain="physical-development" if change == "wrong_domain" else "nutrition",
                    purpose="dispatch",
                    scope=["specialist:dispatch"],
                    jti=str(uuid4()) if change == "wrong_request" else str(task_id),
                ),
                private,
                algorithm="EdDSA",
            )
            return httpx.Response(200, json={"capability": token})
        assert request.url.host == "specialists.example.test"
        assert request.url.path == "/v1/specialists/nutrition/tasks"
        assert "synthetic-exchange-secret" not in request.headers["authorization"]
        result = specialist_payload(
            Domain.PHYSICAL if change == "wrong_result" else Domain.NUTRITION
        )
        if change == "accepted_knowledge":
            result["findings"][0]["citations"][0]["claim_assessment"] = "accepted"
        if change == "oversize":
            return httpx.Response(200, content=b"x" * 262145)
        return httpx.Response(200, json=result)

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    settings = Settings(
        service_subject="synthetic-coordinator",
        specialist_public_key=public,
        exchange_token="synthetic-exchange-secret",
        exchange_url="https://gateway.example.test/exchange",
        specialist_url="https://specialists.example.test",
    )
    if change:
        with pytest.raises((InvalidEvidence, ProviderUnavailable)):
            HTTPSpecialistClient(settings).dispatch(assignment(Domain.NUTRITION), task_id)
    else:
        assert (
            HTTPSpecialistClient(settings)
            .dispatch(assignment(Domain.NUTRITION), task_id)
            .specialist
            == Domain.NUTRITION
        )
    if change in ("wrong_domain", "wrong_subject", "wrong_request", "redirect"):
        assert len(seen) == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://insecure.example.test",
        "https://user:password@example.test",
        "https://example.test?arbitrary=target",
        "https://example.test#fragment",
    ],
)
def test_service_destinations_are_operator_configured_fixed_https_urls(url):
    with pytest.raises(ValidationError):
        Settings(specialist_url=url)


def test_model_planner_uses_strict_required_schema_and_has_no_tools(monkeypatch):
    real_client = httpx.Client
    seen = []
    plan = Plan(
        decision="research",
        rationale="Investigate reviewed nutrition evidence.",
        questions=[],
        assignments=[assignment(Domain.NUTRITION)],
    )

    def respond(request):
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": plan.model_dump_json()}],
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
    assert provider.plan({"question": "General research question"}) == plan
    body = seen[0]
    assert body["store"] is False and "tools" not in body
    schema = body["text"]["format"]["schema"]
    for node in [schema, *schema["$defs"].values()]:
        if node.get("type") == "object":
            assert node["additionalProperties"] is False and set(node["required"]) == set(
                node["properties"]
            )
    with pytest.raises(BudgetExceeded):
        provider.plan({"question": "x" * 80001})
    assert len(seen) == 1


def test_missing_connections_fail_closed_without_manufactured_answers():
    with pytest.raises(ProviderUnavailable):
        OpenAIProvider(Settings(openai_api_key=None, model=None)).plan({})
    with pytest.raises(ProviderUnavailable):
        HTTPSpecialistClient(Settings()).dispatch(assignment(Domain.NUTRITION), uuid4())


def test_quality_fixtures_cover_all_domains_but_fixture_validation_is_not_a_quality_score(capsys):
    cases = load_cases()
    assert {domain for case in cases for domain in case.required_domains} == set(Domain)
    assert evaluate([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {"fixture_cases_validated": 14, "live_model_evaluated": False}
