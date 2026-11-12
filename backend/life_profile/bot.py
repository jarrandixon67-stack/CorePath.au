from life_profile.models import AnalyseRequest, Category, Proposal
from life_profile.provider import InvalidProposal, Provider
from life_profile.repository import ConsentRequired, ProfileRepository

SENSITIVE_CATEGORIES = {
    Category.HEALTH,
    Category.RELATIONSHIPS,
    Category.CULTURE,
    Category.CAREER,
}
LEVELS = {
    "user_statement": "known_information",
    "observed_pattern": "observed_pattern",
    "hypothesis": "developing_understanding",
}


def validate_proposal(proposal: Proposal, request: AnalyseRequest, consent) -> list[dict]:
    """Model output cannot create confirmation, evidence or permissions."""
    messages = {message.message_id: message for message in request.messages}
    payloads = []
    for observation in proposal.observations:
        if observation.category not in consent.categories:
            raise InvalidProposal("The model proposed material outside the consented categories.")
        conversation_ids = set()
        for evidence in observation.evidence:
            source = messages.get(evidence.message_id)
            if source is None or evidence.quote not in source.content:
                raise InvalidProposal("An observation did not cite an exact supplied user message.")
            conversation_ids.add(source.conversation_id)
        if observation.kind == "observed_pattern" and len(conversation_ids) < 2:
            raise InvalidProposal("A repeated pattern needs evidence from separate conversations.")
        payload = observation.model_dump(mode="json")
        payload["sensitive"] = observation.sensitive or observation.category in SENSITIVE_CATEGORIES
        if payload["sensitive"] and not consent.sensitive_observations_enabled:
            # Do not retain sensitive output outside the user's permissions.
            continue
        payload.update(
            understanding_level=LEVELS[observation.kind],
            shared_with_personal_ai=False,
            user_corrected=False,
            purpose=request.purpose,
            evidence_role="original_proposal",
        )
        payload["source_context"] = [
            {
                "message_id": messages[e.message_id].message_id,
                "conversation_id": messages[e.message_id].conversation_id,
                "source_type": messages[e.message_id].source_type,
                "observed_at": (
                    messages[e.message_id].observed_at.isoformat()
                    if messages[e.message_id].observed_at
                    else None
                ),
            }
            for e in observation.evidence
        ]
        payloads.append(payload)
    if proposal.follow_up and proposal.follow_up.category not in consent.categories:
        raise InvalidProposal("The follow-up question exceeded the consented categories.")
    return payloads


class LifeProfileBot:
    def __init__(self, repository: ProfileRepository, provider: Provider):
        self.repository, self.provider = repository, provider

    def analyse(
        self, subject: str, request: AnalyseRequest, request_id: str, *, journal_source=None
    ) -> dict:
        journal_messages = [m for m in request.messages if m.source_type == "journal_entry"]
        if journal_messages:
            if (
                journal_source is None
                or len(request.messages) != 1
                or journal_messages[0].message_id != "journal:" + str(journal_source[0])
            ):
                raise ConsentRequired
        elif journal_source is not None:
            raise ConsentRequired
        snapshot = self.repository.snapshot(subject, request_id)
        consent = snapshot["consent"]
        if not consent.analysis_enabled or not consent.external_model_processing:
            raise ConsentRequired
        if request.purpose != consent.purpose:
            raise ConsentRequired
        accepted = [
            {
                "statement": item["statement"],
                "category": item["category"],
                "dimensions": item["dimensions"],
                "user_corrected": item["user_corrected"],
            }
            for item in snapshot["items"]
            if item["state"] == "accepted"
            and item["category"] in consent.categories
            and (not item["sensitive"] or consent.sensitive_observations_enabled)
        ]
        proposal = self.provider.propose(
            {
                "purpose": request.purpose,
                "consent": consent.model_dump(mode="json"),
                "messages": [message.model_dump(mode="json") for message in request.messages],
                "previously_accepted_understanding": accepted,
            }
        )
        payloads = validate_proposal(proposal, request, consent)
        journal_sources = {}
        for item in snapshot["items"]:
            if (
                item["state"] == "accepted"
                and item["category"] in consent.categories
                and (not item["sensitive"] or consent.sensitive_observations_enabled)
            ):
                journal_sources.update(item.get("journal_sources", {}))
        if journal_source is not None:
            journal_sources[str(journal_source[0])] = journal_source[1]
        for payload in payloads:
            if journal_sources:
                payload["journal_sources"] = journal_sources
        if not journal_sources:
            results = self.repository.propose(
                subject, payloads, snapshot["consent_revision"], request_id
            )
        else:
            results = self.repository.propose(
                subject,
                payloads,
                snapshot["consent_revision"],
                request_id,
                journal_source=journal_source,
                journal_sources=journal_sources,
            )
        follow_up = proposal.follow_up
        if (
            follow_up
            and follow_up.category in SENSITIVE_CATEGORIES
            and not consent.sensitive_observations_enabled
        ):
            follow_up = None
        return {
            "proposals": results,
            "follow_up": follow_up.model_dump(mode="json") if follow_up else None,
            "review_required": True,
        }
