import json
from uuid import UUID

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient
from test_coordinator import CoordinatorProvider
from test_coordinator import coordinator_store as coordinator_fixture
from test_life_profile_repository import add_proposal
from test_life_profile_repository import profiles as profile_fixture
from test_persy import Connected, Model
from test_persy import persy_store as persy_fixture
from test_persy_services import keys
from test_specialists_repository import EvidenceProvider, evidence
from test_specialists_repository import specialist_store as specialist_fixture

from app.trial_metrics import model_call, snapshot
from coordinator import main as coordinator_api
from coordinator.evaluate import load_cases
from coordinator.runtime import Runtime as CoordinatorRuntime
from coordinator.transport import HTTPSpecialistClient
from life_profile import main as profile_api
from life_profile.settings import Settings as ProfileSettings
from persy import trial
from persy.main import app, repository, runtime
from persy.runtime import Runtime
from persy.services import Services
from persy.settings import Settings, get_settings
from service_gateway import main as exchange
from specialists import main as specialist_api
from specialists.runtime import Runtime as SpecialistRuntime
from specialists.settings import Settings as SpecialistSettings

persy_store = persy_fixture
coordinator_store = coordinator_fixture
specialist_store = specialist_fixture
profiles = profile_fixture
ORIGIN = "https://corepathcommunity.com"
HEADERS = {"Origin": ORIGIN}
PASSWORD = "synthetic trial password"


@pytest.fixture
def browser(monkeypatch, persy_store):
    repo, _, owner, _, settings = persy_store
    private, public = keys()
    sign = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    salt = bytes(16)
    verifier = salt.hex() + ":" + trial.password_digest(PASSWORD, salt).hex()
    trial_settings = trial.TrialSettings(
        origin=ORIGIN,
        accounts=json.dumps({subject: verifier for subject in (owner.subject, "another")}),
        administrator=owner.subject,
        member_signing_key=sign,
    )
    monkeypatch.setattr(trial, "config", lambda: trial_settings)
    # security.py imports the configuration callable as well.
    monkeypatch.setattr("persy.security.config", lambda: trial_settings)
    monkeypatch.setattr("persy.main.repository", lambda _request: repo)
    auth_settings = Settings(gateway_public_key=public)
    app.dependency_overrides[get_settings] = lambda: auth_settings
    app.dependency_overrides[repository] = lambda: repo
    app.dependency_overrides[runtime] = lambda: Runtime(repo, Model(), Connected(), settings)
    trial.accounts.cache_clear()
    trial.attempts.clear()
    try:
        yield TestClient(app, base_url=ORIGIN), owner.subject, trial_settings
    finally:
        trial.accounts.cache_clear()
        trial.sessions.clear()
        app.dependency_overrides.clear()


def login(client, name, headers=HEADERS):
    return client.post(
        "/trial/session", headers=headers, json={"username": name, "password": PASSWORD}
    )


def test_trial_browser_sign_in_chat_isolation_and_logout(browser):
    client, owner, _ = browser
    privacy = "/v1/persy/privacy"
    conversations = "/v1/persy/conversations"
    page = client.get("/")
    assert page.status_code == 200 and "Ask Percy" in page.text
    assert '<form id="login" method="post" action="/trial/session">' in page.text
    assert '<button id="send-chat" disabled>' in page.text
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert client.get("/trial.js").status_code == 200
    assert client.get(privacy).status_code == 401
    assert login(client, owner, {"Origin": "https://elsewhere.invalid"}).status_code == 403
    assert login(client, "unapproved").status_code == 401
    response = login(client, owner)
    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert all(flag in cookie.lower() for flag in ("httponly", "secure", "samesite=strict"))
    token = client.cookies.get(trial.COOKIE)
    assert client.get("/trial/metrics").status_code == 200
    created = client.post(conversations, headers=HEADERS).json()
    path = conversations + "/" + created["conversation_id"]
    assert (
        client.post(path + "/messages", json={"message": "Hello", "max_specialists": 3}).status_code
        == 403
    )
    assert (
        client.post(
            path + "/messages", json={"message": "Hello", "max_specialists": 3}, headers=HEADERS
        ).status_code
        == 200
    )
    assert client.delete("/trial/session", headers=HEADERS).status_code == 204
    other = TestClient(app, base_url=ORIGIN)
    assert login(other, "another").status_code == 204
    assert other.get("/trial/metrics").status_code == 403
    assert (
        other.put(
            privacy,
            headers=HEADERS,
            json={"expected_revision": 0, "model_processing_enabled": True},
        ).status_code
        == 200
    )
    assert other.get(path).status_code == 404
    assert other.delete(path, headers=HEADERS).status_code == 404
    client.cookies.set(trial.COOKIE, token)
    assert client.get(privacy).status_code == 401


def test_trial_close_erases_conversations_and_revokes_invitation(browser, monkeypatch):
    client, owner, _ = browser
    deleted = []

    class Profile:
        def __init__(self, _settings):
            pass

        def profile(self, member, action):
            assert member.subject == owner
            deleted.append(action)

    monkeypatch.setattr("persy.main.Services", Profile)
    assert login(client, owner).status_code == 204
    token = client.cookies.get(trial.COOKIE)
    created = client.post("/v1/persy/conversations", headers=HEADERS).json()
    assert UUID(created["conversation_id"])
    assert client.delete("/trial/account", headers=HEADERS).status_code == 204
    assert deleted == ["delete_profile"]
    client.cookies.set(trial.COOKIE, token)
    assert client.get("/v1/persy/privacy").status_code == 401
    assert login(client, owner).status_code == 403


def test_trial_roster_and_sign_in_rate_cap(browser):
    client, _, settings = browser
    for _ in range(8):
        assert login(client, "outside-roster").status_code == 401
    assert login(client, "outside-roster").status_code == 429
    verifier = next(iter(json.loads(settings.accounts).values()))
    settings.accounts = json.dumps({f"member-{index}": verifier for index in range(21)})
    trial.accounts.cache_clear()
    assert login(client, "member-0").status_code == 503


@pytest.mark.parametrize(
    "case",
    [
        case
        for case in load_cases()
        if len(case.required_domains) == 1 and case.id != "injection-in-question"
    ],
    ids=lambda case: case.id,
)
def test_trial_routes_a_reviewed_question_through_the_signed_service_chain(
    browser, persy_store, coordinator_store, profiles, monkeypatch, case
):
    client, owner, browser_settings = browser
    personal_repo, _, _, _, personal_settings = persy_store
    coord_repo, specialist_repo, libraries, conn, caller, coord_settings = coordinator_store
    profile_repo, _, _, _, consent = profiles
    (domain,) = case.required_domains
    evidence(conn, libraries[domain.value])

    class PercyModel(Model):
        def reply(self, context):
            assert context["member_message"] == case.question
            reply = super().reply(context)
            reply.research_proposal.question = case.question
            return reply

    class RoutingModel(CoordinatorProvider):
        def plan(self, context):
            assert context["question"] == case.question
            return super().plan(context)

    coord_model = RoutingModel([domain])
    service_key, service_public = keys()
    service_private = service_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    profile_key, profile_public = keys()
    profile_private = profile_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    member_public = app.dependency_overrides[get_settings]().gateway_public_key
    percy_secret, coordinator_secret = "p" * 32, "c" * 32
    monkeypatch.setattr(
        exchange,
        "settings",
        lambda: exchange.Settings(
            signing_private_key=service_private,
            profile_signing_private_key=profile_private,
            member_public_key=member_public,
            percy_machine_token=percy_secret,
            coordinator_machine_token=coordinator_secret,
            percy_subject=caller.subject,
            coordinator_subject=coord_settings.service_subject,
            allowed_member_subjects=",".join(json.loads(browser_settings.accounts)),
        ),
    )
    coord_settings = coord_settings.model_copy(
        update={
            "gateway_public_key": service_public,
            "specialist_public_key": service_public,
            "exchange_url": "https://exchange.test/exchange/coordinator",
            "exchange_token": coordinator_secret,
            "specialist_url": "https://specialist.test",
        }
    )
    specialist_settings = SpecialistSettings(gateway_public_key=service_public)
    personal_settings = personal_settings.model_copy(
        update={
            "coordinator_url": "https://coordinator.test",
            "profile_url": "https://profile.test",
            "profile_public_key": profile_public,
            "coordinator_public_key": service_public,
            "exchange_url": "https://exchange.test/exchange/percy",
            "exchange_token": percy_secret,
            "service_subject": caller.subject,
        }
    )
    specialist_api.app.dependency_overrides[specialist_api.get_settings] = lambda: (
        specialist_settings
    )
    specialist_api.app.dependency_overrides[specialist_api.runtime] = lambda: SpecialistRuntime(
        specialist_repo, EvidenceProvider(), specialist_settings
    )
    coordinator_api.app.dependency_overrides[coordinator_api.get_settings] = lambda: coord_settings
    coordinator_api.app.dependency_overrides[coordinator_api.runtime] = lambda: CoordinatorRuntime(
        coord_repo, coord_model, HTTPSpecialistClient(coord_settings), coord_settings
    )
    app.dependency_overrides[runtime] = lambda: Runtime(
        personal_repo, PercyModel(research=True), Services(personal_settings), personal_settings
    )
    profile_api.app.dependency_overrides[profile_api.get_settings] = lambda: ProfileSettings(
        gateway_public_key=profile_public
    )
    profile_api.app.dependency_overrides[profile_api.repository] = lambda: profile_repo
    monkeypatch.setattr("persy.main.get_settings", lambda: personal_settings)
    hosts = {
        "exchange.test": TestClient(exchange.app),
        "profile.test": TestClient(profile_api.app),
        "coordinator.test": TestClient(coordinator_api.app),
        "specialist.test": TestClient(specialist_api.app),
    }
    calls = []

    def send(request):
        calls.append(request.url.path)
        result = hosts[request.url.host].request(
            request.method, request.url.path, headers=dict(request.headers), content=request.content
        )
        return httpx.Response(result.status_code, content=result.content, headers=result.headers)

    http_client = httpx.Client

    def local_client(**kwargs):
        return http_client(transport=httpx.MockTransport(send), **kwargs)

    monkeypatch.setattr(httpx, "Client", local_client)
    try:
        assert login(client, owner).status_code == 204
        created = client.post("/v1/persy/conversations", headers=HEADERS)
        assert created.status_code == 200
        path = "/v1/persy/conversations/" + created.json()["conversation_id"]
        chat = client.post(
            path + "/messages",
            headers=HEADERS,
            json={"message": case.question, "max_specialists": 3},
        )
        assert chat.status_code == 200
        assert chat.json()["message"] == "Let's choose one manageable next step."
        assert calls == []
        proposed = chat.json()["research_proposal"]
        result = client.post(
            path + "/research/" + proposed["id"], headers=HEADERS, json={"approve": True}
        )
        assert result.status_code == 200, result.json()
        assert result.json()["assessed_domains"] == [domain.value]
        assert (
            result.json()["findings"][0]["citations"][0]["canonical_url"]
            == "https://example.org/evidence"
        )
        assert calls == [
            "/exchange/percy",
            "/v1/coordinator/research",
            "/exchange/coordinator",
            f"/v1/specialists/{domain.value}/tasks",
        ]
        profile = "/v1/persy/profile"
        assert client.get(profile).status_code == 404
        assert (
            client.put(
                profile + "/consent", headers=HEADERS, json=consent.model_dump(mode="json")
            ).status_code
            == 200
        )
        item = add_proposal(profile_repo, owner)
        reviewed = client.get(profile)
        assert reviewed.status_code == 200
        assert reviewed.json()["items"][0]["id"] == item["id"]
        decision = client.post(
            profile + "/items/" + item["id"] + "/decision",
            headers=HEADERS,
            json={
                "action": "correct",
                "corrected_statement": "Prefers practical examples",
                "expected_version": 1,
            },
        )
        assert decision.status_code == 200
        assert client.get(profile).json()["items"][0]["statement"] == "Prefers practical examples"
        assert client.delete("/trial/account", headers=HEADERS).status_code == 204
        with profile_repo.pool.connection() as db:
            assert (
                db.execute("SELECT 1 FROM life_profiles WHERE subject = %s", (owner,)).fetchone()
                is None
            )
    finally:
        specialist_api.app.dependency_overrides.clear()
        coordinator_api.app.dependency_overrides.clear()
        profile_api.app.dependency_overrides.clear()
        profile_repo.delete_profile(owner)


def test_monitoring_records_aggregates_and_redacts_provider_details(monkeypatch, caplog):
    monkeypatch.setenv("TRIAL_PERCY_USD_PER_MILLION", "0.40,1.60")
    caplog.set_level("INFO", logger="uvicorn.error")
    with (
        pytest.raises(ValueError, match="synthetic-private"),
        model_call("test.percy.model", "PERCY") as event,
    ):
        event["usage"] = {"input_tokens": 4000, "output_tokens": 600}
        raise ValueError("synthetic-private")
    values = snapshot()["test.percy.model"]
    assert values["input_tokens"] == 4000
    assert values["output_tokens"] == 600
    assert values["estimated_usd_micros"] == 2560
    assert values["errors"] == 1
    assert "test.percy.model" in caplog.text
    assert "synthetic-private" not in caplog.text
