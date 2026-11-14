"""Clearly synthetic provider for repeatable offline integration checks."""

from .contracts import Domain, Source


def demo_sources():
    return [Source(
        id="synthetic-demo", title="Synthetic integration fixture, not real-world evidence",
        url="https://example.invalid/corepath-demo", checked_at="2026-11-14",
        content="This is a synthetic demonstration of the CorePath collaboration workflow.",
        domains=list(Domain), approved_for_model=True, public=True,
    )]


class DemoProvider:
    def __init__(self):
        self.calls = []

    def generate(self, role_id, stage, context, contract):
        self.calls.append((role_id, stage, context))
        if stage == "select_necessary_specialists":
            return {"domains": [Domain.PERSONAL.value], "rationale": "Synthetic single-domain routing fixture only."}
        if role_id in {d.value for d in Domain}:
            return {
                "relevant": True, "summary": f"Synthetic workflow contribution from {role_id}.",
                "claims": [{"statement": "This output demonstrates workflow only; it is not researched advice.",
                            "citations": [{"source_id": "synthetic-demo", "quote": "This is a synthetic demonstration"}],
                            "confidence": "low", "limitations": "Synthetic fixture; no real-world claim is established."}],
                "questions": [], "gaps": ["Live evidence and model quality have not been evaluated."],
                "peer_requests": [], "referral_reason": None,
            }
        if role_id == "chief-of-staff":
            available = list(context["contributions"])
            return {
                "conclusions": [] if not available else [{
                    "statement": "All available contributions here are synthetic workflow fixtures.",
                    "references": [{"domain": available[0], "index": 0}],
                    "confidence": "low", "limitations": "This demonstrates routing and validation, not specialist expertise."}],
                "disagreements": [], "gaps": ["No live research was performed."], "questions": [],
                "feedback": [{"domain": d.value, "contribution": "Synthetic contribution received." if d.value in available else "Contribution unavailable.",
                              "improvement": "Evaluate with reviewed evidence and live-model scenarios before deployment."} for d in map(Domain, context.get("assigned_domains", list(Domain)))],
            }
        if role_id == "persy":
            return {"opening": "Here is the demonstration team's draft.",
                    "conclusion_indexes": list(range(len(context["synthesis"]["conclusions"]))),
                    "closing_question": None}
        if role_id == "12":
            return {"ideas": [], "issues": ["Synthetic execution only; no research conclusion is established."]}
        raise ValueError("Demo provider does not implement this role")
