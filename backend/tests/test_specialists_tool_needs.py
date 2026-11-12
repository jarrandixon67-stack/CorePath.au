import json
import stat

import httpx
import pytest
from pydantic import ValidationError

from bot_standards import STANDARD, STANDARD_HASH
from specialists import tool_needs
from specialists.models import InvalidEvidence, ToolNeeds
from specialists.registry import Domain
from specialists.settings import Settings


def response():
    return ToolNeeds.model_validate(
        {
            "requests": [
                {
                    "name": "Validated laboratory-unit checker",
                    "priority": "minimum_required",
                    "purpose": "Reject incompatible units before interpreting a supplied value.",
                    "required_data": ["Analyte, value, original units and lab reference interval."],
                    "privacy_requirements": "Purpose-specific consent and minimal retained data.",
                    "source_requirements": "Reviewed lab methods and supported conversion rules.",
                    "validation_before_use": "Independent clinical review and unit-conversion cases.",
                    "alternative_without_tool": "Explain the missing information and do not guess.",
                }
            ],
            "knowledge_gaps": ["Clinical interpretation has not been validated."],
            "evaluation_needs": ["Check misleading values and missing reference intervals."],
        }
    )


def test_preparation_never_constructs_a_model_or_claims_consultation(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Preparing briefs must not call a provider or read model settings")

    monkeypatch.setattr(tool_needs, "OpenAIProvider", forbidden)
    monkeypatch.setattr(tool_needs, "Settings", forbidden)
    path = tmp_path / "briefs.json"
    assert tool_needs.main(["--output", str(path)]) == 0
    report = json.loads(path.read_text())
    assert len(report["briefs"]) == 11 and report["results"] == []
    assert not report["live_model_consulted"] and not report["permissions_granted"]
    assert not report["expertise_verified"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_live_consultation_uses_selected_domain_model_and_has_no_callable_tools(
    tmp_path, monkeypatch
):
    real_client, calls = httpx.Client, []

    def respond(request):
        assert str(request.url) == "https://api.openai.com/v1/responses"
        payload = json.loads(request.content)
        calls.append(payload)
        assert "tools" not in payload and payload["store"] is False
        assert payload["text"]["format"]["strict"] is True
        assert payload["text"]["format"]["name"] == "specialist_tool_needs"
        assert "cannot grant yourself" in payload["instructions"]
        assert STANDARD in payload["instructions"]
        context = json.loads(payload["input"][0]["content"])
        assert context["discipline"] == Domain.NUTRITION and context["current_tools"] == []
        assert "blood" in context["development_requirements"]
        assert context["standard_hash"] == STANDARD_HASH
        assert context["developer_proposed_tools"] and context["evaluation_focus"]
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": response().model_dump_json()}],
                    }
                ],
            },
        )

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw)
    )
    monkeypatch.setattr(
        tool_needs,
        "Settings",
        lambda: Settings(
            model="shared-model",
            openai_api_key="synthetic-not-a-real-key",
            model_overrides={Domain.NUTRITION.value: "nutrition-model"},
        ),
    )
    path = tmp_path / "responses.json"
    args = ["--live", "--domain", "nutrition", "--output", str(path)]
    assert tool_needs.main(args) == 0
    report = json.loads(path.read_text())
    assert len(calls) == 1 and calls[0]["model"] == "nutrition-model"
    assert report["live_model_consulted"] and not report["expertise_verified"]
    row = report["results"][0]
    assert row["state"] == "live_model_response" and row["response"]["requests"]
    assert not row["permissions_granted"] and row["review_required"]
    assert row["standard_hash"] == report["standard_hash"] == STANDARD_HASH
    assert len(row["brief_hash"]) == len(row["specialist_policy_hash"]) == 64
    assert len(row["consultation_policy_hash"]) == 64
    # An existing report must fail before another paid call and remain unchanged.
    original = path.read_bytes()
    with pytest.raises(SystemExit):
        tool_needs.main(args)
    assert len(calls) == 1 and path.read_bytes() == original


@pytest.mark.parametrize("failure", ["unavailable", "invalid", "incomplete"])
def test_failed_consultations_are_not_reported_as_bot_answers(tmp_path, monkeypatch, failure):
    real_client, calls = httpx.Client, []

    def respond(request):
        calls.append(request)
        if failure == "unavailable":
            return httpx.Response(503, text="synthetic-private-provider-details")
        data = response().model_dump(mode="json")
        data["permissions_granted"] = True
        return httpx.Response(
            200,
            json={
                "status": "incomplete" if failure == "incomplete" else "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(data)}],
                    }
                ],
            },
        )

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw)
    )
    monkeypatch.setattr(
        tool_needs, "Settings", lambda: Settings(model="test", openai_api_key="synthetic-key")
    )
    path = tmp_path / "failed.json"
    assert tool_needs.main(["--live", "--domain", "nutrition", "--output", str(path)]) == 1
    report = json.loads(path.read_text())
    row = report["results"][0]
    assert len(calls) == 1 and row["response"] is None
    assert row["state"] == (
        "provider_unavailable" if failure == "unavailable" else "invalid_model_response"
    )
    assert not row["permissions_granted"] and not row["expertise_verified"]
    assert "synthetic-private-provider-details" not in path.read_text()


def test_missing_configuration_and_duplicate_domains_fail_without_provider_calls(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(tool_needs, "Settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(
        tool_needs, "OpenAIProvider", lambda *a: pytest.fail("No provider may be constructed")
    )
    path = tmp_path / "missing.json"
    with pytest.raises(SystemExit):
        tool_needs.main(["--live", "--output", str(path)])
    assert not path.exists()
    with pytest.raises(SystemExit):
        tool_needs.main(["--domain", "nutrition", "--domain", "nutrition"])


def test_tool_request_is_a_bounded_proposal_not_a_permission_contract():
    data = response().model_dump(mode="json")
    data["requests"][0]["execute"] = "anything"
    with pytest.raises(ValidationError):
        ToolNeeds.model_validate(data)
    data = response().model_dump(mode="json")
    data["requests"] *= 7
    with pytest.raises(ValidationError):
        ToolNeeds.model_validate(data)
    assert all(
        brief["current_tools"] == [] for brief in map(tool_needs.consultation_context, Domain)
    )


def test_consultation_rejects_output_masquerading_as_a_tool_grant(monkeypatch):
    class InvalidProvider:
        def assess_tools(self, specialist, context):
            raise InvalidEvidence("synthetic-internal-error")

    row = tool_needs.consult(Domain.FINANCIAL, InvalidProvider(), Settings(model="test"))
    assert row["state"] == "invalid_model_response" and row["response"] is None
    assert not row["permissions_granted"]
