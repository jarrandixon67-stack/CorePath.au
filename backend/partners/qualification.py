"""Evidence coverage is distinct from eligibility, reputation and commercial terms."""

from datetime import UTC, datetime, timedelta

from partners.models import Criterion, Evidence, Kind, Policy

ALLOWED_KINDS = {
    Criterion.IDENTITY: {Kind.REGISTRY, Kind.REGULATOR},
    Criterion.PRICING: {Kind.WEBSITE, Kind.REGULATOR},
    Criterion.QUALITY: {Kind.INDEPENDENT, Kind.REGULATOR},
    Criterion.COMPLAINTS: {Kind.WEBSITE, Kind.REGULATOR},
    Criterion.SAFETY: {Kind.REGULATOR, Kind.REGISTRY},
    Criterion.HEALTH_SCOPE: {Kind.REGISTRY, Kind.REGULATOR},
    Criterion.HEALTH_CLAIMS: {
        Kind.INDEPENDENT,
        Kind.REGULATOR,
        Kind.TRADITIONAL,
        Kind.EXPERIENCE,
        Kind.WEBSITE,
    },
    Criterion.HEALTH_CONSENT: {Kind.WEBSITE, Kind.REGULATOR},
    Criterion.HEALTH_PRIVACY: {Kind.WEBSITE, Kind.REGULATOR},
}


def assess(policy: Policy, evidence: list[dict], *, now=None):
    now = now or datetime.now(UTC)
    outcomes = []
    for criterion in policy.requirements:
        current = []
        for record in evidence:
            item = Evidence.model_validate(record["document"])
            if (
                record["verified"]
                and record["active"]
                and item.criterion == criterion
                and item.kind in ALLOWED_KINDS[criterion]
                and now - timedelta(days=policy.max_age_days) <= item.checked_at <= now
                and item.valid_until > now
            ):
                current.append(item)
        known = {item.result for item in current if item.result != "unknown"}
        if len(known) > 1:
            outcome, reason = "review", "Conflicting current evidence needs review."
        elif known:
            outcome, reason = next(iter(known)), "Supported by reviewed current evidence."
        else:
            outcome, reason = "review", "Missing, expired or unverified evidence."
        outcomes.append(
            {
                "criterion": criterion.value,
                "result": outcome,
                "reason": reason,
                "evidence_ids": [str(e.id) for e in current],
            }
        )
    passed = sum(o["result"] == "pass" for o in outcomes)
    known_count = sum(o["result"] in ("pass", "fail") for o in outcomes)
    decision = (
        "not_qualified"
        if any(o["result"] == "fail" for o in outcomes)
        else "review"
        if any(o["result"] == "review" for o in outcomes)
        else "qualified"
    )
    return {
        "decision": decision,
        "criteria": outcomes,
        "coverage_percent": round(known_count / len(outcomes) * 100),
        "score": round(passed / len(outcomes) * 100) if known_count == len(outcomes) else None,
        "meaning": "CorePath partnership requirements met; not a consumer star rating.",
        "assessed_at": now.isoformat(),
    }
