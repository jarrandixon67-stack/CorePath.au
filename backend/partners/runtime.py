"""Bounded assessment-to-invitation workflow; delivery is a separate durable worker."""

from partners.repository import QUEUE, RESEARCH, Conflict


def evaluate_batch(repo, subject, business_ids, policy_id, settings):
    repo.authorize(subject, RESEARCH)
    repo.authorize(subject, QUEUE)
    results = []
    for business_id in dict.fromkeys(business_ids):
        report = repo.assess(subject, business_id, policy_id)
        result = {
            "business_id": str(business_id),
            "assessment_id": str(report["id"]),
            "decision": report["document"]["decision"],
            "invitation_state": "not_queued",
        }
        if report["document"]["decision"] == "qualified":
            try:
                outbox = repo.enqueue(subject, business_id, report["id"], settings)
                result["invitation_state"] = outbox["state"]
            except Conflict as exc:
                result["reason"] = str(exc)
        results.append(result)
    return {
        "results": results,
        "emails_sent": 0,
        "note": "Only eligible contacts are queued. The enabled delivery worker sends them separately.",
    }
