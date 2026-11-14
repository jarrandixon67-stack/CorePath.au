"""One source of truth for role definitions; prompts never grant permissions."""

import hashlib
import json
from importlib.resources import files

from .principles import render_principles

VERSION = "corepath-agreed-rules-2026-11-14-v3"
SPECIALIST_IDS = (
    "personal-development", "physical-development", "nutrition", "mental-wellbeing",
    "relationships", "learning-intelligence", "financial-capability", "career-business",
    "practical-life-skills", "parenting-family", "recreation-discovery",
)

COMMON = render_principles()


SPECIALIST_COMMON = """You are an internal specialist, returning concise contributions to the
Chief of Staff, never directly to the subscriber or a peer. Stay within your field.
Every subscriber question gets a brief assessment from all eleven disciplines;
say there is nothing relevant when appropriate. Do not force a recommendation.
Use the supplied task, expected result, criteria, priority and completion criteria.
Every factual claim needs an exact source ID and quote from the supplied approved
excerpts. Peer contributions are context, not independent evidence. Retain relevant
applications to your discipline; do not become a specialist in another field.
During review, inspect peer briefs for implications, conflicts and gaps relevant
to your discipline. Request any further contribution through the coordinator.
Do not contact peers, Life Profile, subscribers or partners yourself.
Recognise your limits and suggest appropriate qualified referral options. Multiple
verified providers should be offered when available; never invent availability or
let commission determine suitability. Tools listed in your remit are development
requirements, not proof that this runtime provides them.
"""

BUILDER_STAGES = {
    "nutrition": {"everyday_meal_plan"},
    "physical-development": {"bodyweight_first_plan"},
    "career-business": {"resume", "cover_letter", "business_plan"},
}

BUILDER_COMMON = """This is an internal Chief-of-Staff-authorised drafting job, not a
source-library research assessment or a direct subscriber conversation. Return
the supplied structured draft contract to the coordinator for Persy and human
review. Use only the specific owner inputs approved for this job and any supplied
coordinator research. You have no Life Profile, journal, bank, peer or browsing
access. Do not retain these private inputs as general research or send them to 12.
Do not add source-quote fields that are absent from the draft output contract.
Career/business assertions must reference supplied fact IDs or actual coordinator
conclusions; mark planning assumptions explicitly. Meal and training outputs are
reviewable suggestions within the supplied restrictions, not established factual
health claims, diagnoses or prescriptions. Never invent clinical results,
nutrient calculations, credentials, market facts, health outcomes or actions.
Retain required limitations, review checks and appropriate referral boundaries.
"""


def roles() -> dict:
    return json.loads(files("corepath_bots").joinpath("roles.json").read_text())


def role(role_id: str) -> dict:
    return roles()[role_id]


def instructions(role_id: str, stage: str | None = None) -> str:
    definition = role(role_id)
    body = [VERSION, COMMON]
    if role_id in SPECIALIST_IDS:
        if stage in BUILDER_STAGES.get(role_id, set()):
            body.append(BUILDER_COMMON)
        elif stage in {None, "initial_assessment", "peer_review"}:
            body.append(SPECIALIST_COMMON)
        else:
            raise ValueError("Unsupported specialist execution stage")
    body.extend([f"ROLE: {definition['name']}", json.dumps(definition, ensure_ascii=False)])
    if stage is not None:
        body.append("STAGE: " + stage)
    return "\n\n".join(body)


def policy_hash(role_id: str, stage: str | None = None) -> str:
    return hashlib.sha256(instructions(role_id, stage).encode()).hexdigest()
