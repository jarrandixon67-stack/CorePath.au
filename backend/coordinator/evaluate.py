"""Small, synthetic routing evaluation. Does not certify overall bot quality."""

import argparse
import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from coordinator.policy import POLICY_HASH
from coordinator.provider import OpenAIProvider
from coordinator.runtime import validate_assignments
from coordinator.settings import Settings
from specialists.models import BudgetExceeded, InvalidEvidence, ProviderUnavailable, StrictModel
from specialists.registry import Domain, catalogue


class Case(StrictModel):
    id: str = Field(min_length=3, max_length=100)
    question: str = Field(min_length=5, max_length=2000)
    required_domains: list[Domain] = Field(max_length=3)
    decision: Literal["research", "clarify"]


def load_cases():
    raw = json.loads(Path(__file__).with_name("evaluation_cases.json").read_text())
    cases = [Case.model_validate(item) for item in raw]
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("Evaluation case IDs must be distinct")
    return cases


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Call the configured model once per synthetic case; incurs provider usage",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    cases = load_cases()
    if not args.live:
        print(json.dumps({"fixture_cases_validated": len(cases), "live_model_evaluated": False}))
        return 0
    settings = Settings()
    if not settings.openai_api_key or not settings.model or not args.output:
        parser.error(
            "--live requires a configured model/key and --output; do not enter secrets in chat"
        )
    rows = []
    provider = OpenAIProvider(settings)
    for case in cases:
        try:
            plan = provider.plan(
                {
                    "question": case.question,
                    "allowed_specialists": catalogue(),
                    "remaining_calls": 3,
                }
            )
            validate_assignments(plan.assignments, list(Domain), 3)
            selected = {item.domain for item in plan.assignments}
            passed = plan.decision == case.decision and set(case.required_domains) == selected
            rows.append({"case": case.id, "passed": passed, "plan": plan.model_dump(mode="json")})
        except (InvalidEvidence, ProviderUnavailable, BudgetExceeded):
            rows.append({"case": case.id, "passed": False, "error": "unavailable_or_invalid_plan"})
    report = {
        "model": settings.model,
        "policy_hash": POLICY_HASH,
        "scope": "synthetic_routing_only",
        "overall_bot_quality_verified": False,
        "passed": sum(row["passed"] for row in rows),
        "total": len(rows),
        "results": rows,
    }
    args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps({key: value for key, value in report.items() if key != "results"}))
    return 0 if report["passed"] == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
