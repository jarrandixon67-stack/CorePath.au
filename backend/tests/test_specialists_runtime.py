import json
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from bot_standards import STANDARD, STANDARD_HASH, STANDARD_VERSION
from specialists.models import InvalidEvidence, Proposal, ProviderUnavailable, Task
from specialists.provider import OpenAIProvider
from specialists.registry import SPECIALISTS, Domain, catalogue
from specialists.runtime import grounded_result
from specialists.settings import Settings


def empty_proposal():
    return Proposal(
        findings=[], options=[], contradictions=[], knowledge_gaps=[], collaboration_requests=[]
    )


def excerpt():
    return {
        "section_id": str(uuid4()),
        "source_id": str(uuid4()),
        "title": "Synthetic source",
        "authors": ["Test Author"],
        "canonical_url": "https://example.org/source",
        "locator": "p. 2",
        "publication_date": "2025-01-01",
        "content": "Evidence for this synthetic test is limited.",
    }


def proposal_for(section):
    return Proposal.model_validate(
        {
            "findings": [
                {
                    "statement": "The synthetic evidence is limited.",
                    "confidence": "low",
                    "limitations": "Synthetic data only.",
                    "citations": [
                        {"section_id": section["section_id"], "quote": section["content"]}
                    ],
                }
            ],
            "options": [
                {
                    "action": "Investigate the limitations.",
                    "finding_indexes": [0],
                    "limitations": "General education only.",
                }
            ],
            "contradictions": [],
            "knowledge_gaps": ["Real evidence is still required."],
            "collaboration_requests": [],
        }
    )


def test_eleven_distinct_bounded_specialists_and_no_profile_provider_dependency():
    assert len(SPECIALISTS) == 11
    assert len({bot.policy_hash for bot in SPECIALISTS.values()}) == 11
    assert all(not item["user_facing"] and not item["life_profile_access"] for item in catalogue())
    for bot in SPECIALISTS.values():
        assert bot.mandate in bot.instructions and bot.boundary in bot.instructions
        assert "Source verification does not establish" in bot.instructions


@pytest.mark.parametrize("domain", list(Domain))
def test_all_specialists_return_grounded_drafts_with_server_owned_provenance(domain):
    section = excerpt()
    result = grounded_result(domain, proposal_for(section), [section])
    assert result["specialist"] == domain.value
    assert result["review_required"] and result["audience"] == "coordinator_internal"
    assert not result["life_profile_access"] and not result["collaboration_executed"]
    citation = result["findings"][0]["citations"][0]
    assert citation["canonical_url"] == section["canonical_url"]
    assert citation["claim_assessment"] == "proposed_not_accepted"


@pytest.mark.parametrize(
    "change",
    [
        "missing_section",
        "invented_quote",
        "unsupported_option",
        "contradiction_missing",
        "contradiction_overlap",
        "self_collaboration",
        "duplicate_collaboration",
    ],
)
def test_fabricated_or_inconsistent_evidence_and_collaboration_are_rejected(change):
    section = excerpt()
    data = proposal_for(section).model_dump(mode="json")
    if change == "missing_section":
        data["findings"][0]["citations"][0]["section_id"] = str(uuid4())
    elif change == "invented_quote":
        data["findings"][0]["citations"][0]["quote"] = "A claim absent from the evidence."
    elif change == "unsupported_option":
        data["options"][0]["finding_indexes"] = [4]
    elif change.startswith("contradiction"):
        data["contradictions"] = [
            {
                "description": "Synthetic disagreement",
                "supporting_sections": [section["section_id"]],
                "challenging_sections": [
                    section["section_id"] if change.endswith("overlap") else str(uuid4())
                ],
            }
        ]
    else:
        target = Domain.NUTRITION if change == "self_collaboration" else Domain.PHYSICAL
        data["collaboration_requests"] = [
            {"domain": target.value, "reason": "Needs Coordinator review."}
        ] * (2 if change.startswith("duplicate") else 1)
    with pytest.raises(InvalidEvidence):
        grounded_result(Domain.NUTRITION, Proposal.model_validate(data), [section])


def test_collaboration_is_a_request_and_never_a_peer_call():
    data = empty_proposal().model_dump(mode="json")
    data["collaboration_requests"] = [
        {"domain": Domain.PHYSICAL.value, "reason": "Compare movement evidence."}
    ]
    result = grounded_result(Domain.NUTRITION, Proposal.model_validate(data), [])
    assert result["collaboration_requests"] and result["collaboration_executed"] is False


def test_task_rejects_profile_fields_and_output_contract_rejects_invented_urls():
    with pytest.raises(ValidationError):
        Task(
            question="Research learning",
            search_terms=["learning"],
            life_profile={"name": "private"},
        )
    section = excerpt()
    data = proposal_for(section).model_dump(mode="json")
    data["findings"][0]["citations"][0]["url"] = "https://example.org/invented"
    with pytest.raises(ValidationError):
        Proposal.model_validate(data)


def test_model_configuration_checks_and_missing_provider_fails_closed():
    with pytest.raises(ValidationError):
        Settings(model_overrides={"unknown-domain": "a-model"})
    assert (
        Settings(model="default", model_overrides={"nutrition": "override"}).model_for(
            Domain.NUTRITION
        )
        == "override"
    )
    with pytest.raises(ProviderUnavailable):
        OpenAIProvider(Settings(openai_api_key=None, model=None)).propose(
            SPECIALISTS[Domain.NUTRITION], {}
        )


def test_provider_uses_distinct_policy_strict_schema_no_tools_and_no_storage(monkeypatch):
    real_client = httpx.Client
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": empty_proposal().model_dump_json()}
                        ],
                    }
                ],
            },
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    settings = Settings(
        openai_api_key="synthetic-test-key", model="test-model", max_output_tokens=500
    )
    for domain in Domain:
        OpenAIProvider(settings).propose(SPECIALISTS[domain], {"question": "General evidence only"})
    assert len({r["instructions"] for r in requests}) == 11
    for domain, request in zip(Domain, requests, strict=True):
        assert STANDARD in request["instructions"]
        assert SPECIALISTS[domain].mandate in request["instructions"]
        assert SPECIALISTS[domain].boundary in request["instructions"]
        assert request["store"] is False and "tools" not in request
        assert request["max_output_tokens"] == 500
        schema = request["text"]["format"]["schema"]
        assert request["text"]["format"]["strict"] is True
        for node in [schema, *schema["$defs"].values()]:
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])


def test_catalogue_exposes_per_domain_requirements_without_granting_tools_or_expertise():
    records = catalogue()
    assert len({tuple(r["tool_requirements"]) for r in records}) == 11
    for record in records:
        assert record["standard_version"] == STANDARD_VERSION
        assert record["standard_hash"] == STANDARD_HASH
        assert record["tool_requirements"] and record["evaluation_focus"]
        assert record["expertise_status"] == "unverified_development_target"
        assert not record["life_profile_access"] and not record["user_facing"]
        assert record["peer_access"] == "coordinator_authorisation_required"


@pytest.mark.parametrize(
    "payload,code,error",
    [
        ({"secret": "upstream-private-details"}, 401, ProviderUnavailable),
        ({"status": "incomplete", "output": []}, 200, InvalidEvidence),
        ({"status": "completed", "output": []}, 200, InvalidEvidence),
        ([], 200, InvalidEvidence),
    ],
)
def test_provider_errors_and_incomplete_outputs_do_not_become_findings(
    monkeypatch, payload, code, error
):
    real_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(lambda _: httpx.Response(code, json=payload)), **kwargs
        ),
    )
    with pytest.raises(error) as caught:
        OpenAIProvider(Settings(openai_api_key="synthetic-test-key", model="test-model")).propose(
            SPECIALISTS[Domain.NUTRITION], {}
        )
    assert "upstream-private-details" not in str(caught.value)
