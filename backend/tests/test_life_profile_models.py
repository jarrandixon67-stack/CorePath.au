import pytest
from pydantic import ValidationError
from test_life_profile_bot import request

from life_profile.models import AnalyseRequest, Consent, Decision, Proposal


def test_consent_defaults_never_enable_analysis_or_sharing():
    permission = Consent(purpose="Record my preferences")
    assert not permission.analysis_enabled
    assert not permission.external_model_processing
    assert not permission.personalisation_enabled
    assert not permission.sensitive_observations_enabled


def test_enabled_analysis_requires_selected_categories():
    with pytest.raises(ValidationError):
        Consent(analysis_enabled=True, purpose="Adapt communication")


@pytest.mark.parametrize(
    "extra", [{"user_id": "another-person"}, {"response_time_ms": 1}, {"typing_patterns": {}}]
)
def test_unknown_identity_and_interaction_fields_are_not_accepted(extra):
    raw = request().model_dump(mode="json")
    raw["messages"][0].update(extra)
    with pytest.raises(ValidationError):
        AnalyseRequest.model_validate(raw)


def test_review_cannot_reject_and_share_the_same_observation():
    with pytest.raises(ValidationError):
        Decision(expected_version=1, action="reject", share_with_personal_ai=True)


def test_correction_requires_actual_user_supplied_text():
    with pytest.raises(ValidationError):
        Decision(expected_version=1, action="correct")


def test_structured_output_schema_requires_every_field_and_forbids_extras():
    schema = Proposal.model_json_schema()
    for item in [schema, *schema["$defs"].values()]:
        if item.get("type") == "object":
            assert item["additionalProperties"] is False
            assert set(item["required"]) == set(item["properties"])
