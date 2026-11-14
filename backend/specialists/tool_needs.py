"""Prepare or run bounded specialist tool-needs consultations, never tool grants."""

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from bot_standards import STANDARD_HASH, STANDARD_VERSION
from specialists.models import InvalidEvidence, ProviderUnavailable
from specialists.provider import TOOL_NEEDS_INSTRUCTIONS, OpenAIProvider
from specialists.registry import SPECIALISTS, Domain
from specialists.settings import Settings

REQUIREMENTS = """Understand brief questions without inventing missing context.
Offer evidence-supported practical solutions, with concise plain explanations.
Distinguish best practice from a smallest useful step when appropriate, keeping
essential safety and legal steps. Request relevant peer expertise only through
the Coordinator; a full team is the Coordinator plus all eleven specialists.
Explicitly scoped research may use fewer without claiming a full-team discussion.
Nutrition's target includes anatomy, hormones, muscles, organs, nutrient needs
and interactions. Explain generally what laboratory markers can and cannot show;
refer clinical interpretation and specialised diets to qualified professionals.
Any future report extraction needs separate consent, accurate units/provenance,
owner correction and clinician review. It is not authority to diagnose deficiency,
prescribe from isolated results or assume every issue is measurable in blood.
Finance's target includes checked mathematics, Australian financial law, markets,
budgeting and Centrelink. Require dated official rules, jurisdiction, transparent
assumptions and estimates, without inventing rates or guaranteeing entitlements.
Personalised capabilities require a separate consented minimal-data pathway;
the current research runtime accepts general non-identifying questions only.
"""


def consultation_context(domain: Domain):
    bot = SPECIALISTS[domain]
    return {
        "discipline": domain.value,
        "name": bot.name,
        "mandate": bot.mandate,
        "current_boundary": bot.boundary,
        "standard_version": STANDARD_VERSION,
        "standard_hash": STANDARD_HASH,
        "developer_proposed_tools": list(bot.tool_requirements),
        "evaluation_focus": list(bot.evaluation_focus),
        "development_requirements": REQUIREMENTS,
        "current_tools": [],
        "current_tools_note": "This planning consultation has no callable tools or user data.",
    }


def consult(domain, provider, settings):
    context = consultation_context(domain)
    row = {
        "domain": domain.value,
        "model": settings.model_for(domain),
        "standard_version": STANDARD_VERSION,
        "standard_hash": STANDARD_HASH,
        "consulted_at": datetime.now(UTC).isoformat(),
        "brief_hash": hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest(),
        "consultation_policy_hash": hashlib.sha256(TOOL_NEEDS_INSTRUCTIONS.encode()).hexdigest(),
        "specialist_policy_hash": SPECIALISTS[domain].policy_hash,
        "permissions_granted": False,
        "review_required": True,
        "expertise_verified": False,
        "response": None,
    }
    try:
        response = provider.assess_tools(SPECIALISTS[domain], context)
        row.update(state="live_model_response", response=response.model_dump(mode="json"))
    except ProviderUnavailable:
        row["state"] = "provider_unavailable"
    except InvalidEvidence:
        row["state"] = "invalid_model_response"
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", action="append", choices=[d.value for d in Domain])
    parser.add_argument(
        "--live", action="store_true", help="One paid provider call per selected discipline"
    )
    parser.add_argument("--output", type=Path, help="New report file; never overwrites a report")
    args = parser.parse_args(argv)
    domains = [Domain(d) for d in args.domain] if args.domain else list(Domain)
    if len(set(domains)) != len(domains):
        parser.error("Choose each discipline at most once")
    report = {
        "scope": "tool_needs_planning_only",
        "standard_version": STANDARD_VERSION,
        "standard_hash": STANDARD_HASH,
        "live_model_consulted": False,
        "permissions_granted": False,
        "expertise_verified": False,
        "briefs": [consultation_context(domain) for domain in domains],
        "results": [],
    }
    settings = None
    if args.live:
        settings = Settings()
        if (
            not settings.openai_api_key
            or not all(settings.model_for(d) for d in domains)
            or not args.output
        ):
            parser.error(
                "--live requires configured specialist model(s)/key and --output; "
                "use the secret manager, never credentials in chat or command arguments"
            )

    # Reserve the report before paid work. Fail without calls if it exists or
    # cannot be created. The report contains model suggestions, never a grant.
    output = None
    if args.output:
        try:
            descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            output = os.fdopen(descriptor, "w", encoding="utf-8")
        except OSError:
            parser.error("Cannot create a new report at --output")
    try:
        if args.live:
            provider = OpenAIProvider(settings)
            report["results"] = [consult(domain, provider, settings) for domain in domains]
            report["live_model_consulted"] = any(
                row["state"] == "live_model_response" for row in report["results"]
            )
        serialised = json.dumps(report, indent=2)
        if output:
            output.write(serialised + "\n")
        print(
            json.dumps(
                {
                    "disciplines": len(domains),
                    "live_model_consulted": report["live_model_consulted"],
                    "responses_received": sum(
                        row["state"] == "live_model_response" for row in report["results"]
                    ),
                    "permissions_granted": False,
                    "expertise_verified": False,
                }
            )
            if output
            else serialised
        )
    finally:
        if output:
            output.close()
    return 1 if any(row["state"] != "live_model_response" for row in report["results"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
