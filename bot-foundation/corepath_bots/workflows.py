"""Concrete specialist builders, using reviewed inputs and explicit scope gates.

These produce drafts only. They neither publish documents nor impersonate a
clinician. The trusted application supplies permissions and clinician flags.
"""

from typing import Literal

from pydantic import Field, model_validator

from .contracts import Model
from .provider import Provider


class MealContext(Model):
    goals: str = Field(min_length=3, max_length=700)
    preferences: str = Field(min_length=3, max_length=1000)
    allergies: list[str] = Field(max_length=30)
    budget_and_access: str = Field(min_length=3, max_length=1000)
    facilities_and_skills: str = Field(min_length=3, max_length=1000)
    routine_and_activity: str = Field(min_length=3, max_length=1000)
    restrictions: str = Field(min_length=3, max_length=1000)
    clinical_or_specialised_request: bool


class Meal(Model):
    occasion: str = Field(min_length=1, max_length=100)
    foods: list[str] = Field(min_length=1, max_length=12)
    substitution: str = Field(min_length=3, max_length=400)


class MealPlan(Model):
    introduction: str = Field(min_length=3, max_length=400)
    meals: list[Meal] = Field(min_length=1, max_length=8)
    shopping_list: list[str] = Field(max_length=50)
    preparation: list[str] = Field(max_length=12)
    fit_and_limitations: str = Field(min_length=3, max_length=1200)
    feedback_question: str = Field(min_length=3, max_length=300)


class WorkFact(Model):
    id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=3, max_length=1500)


class CareerContext(Model):
    facts: list[WorkFact] = Field(min_length=1, max_length=60)
    target_role: str = Field(min_length=3, max_length=300)
    job_description: str = Field(min_length=3, max_length=6000)

    @model_validator(mode="after")
    def unique(self):
        if len({f.id for f in self.facts}) != len(self.facts):
            raise ValueError("Career fact IDs must be distinct")
        return self


class CareerLine(Model):
    text: str = Field(min_length=3, max_length=700)
    fact_ids: list[str] = Field(min_length=1, max_length=10)


class CareerDraft(Model):
    title: str = Field(min_length=3, max_length=200)
    lines: list[CareerLine] = Field(min_length=1, max_length=50)
    missing_information: list[str] = Field(max_length=15)


class TrainingContext(Model):
    goal: str = Field(min_length=3, max_length=500)
    capability_and_equipment: str = Field(min_length=3, max_length=1200)
    doctor_clearance_confirmed: bool
    doctor_requested_physio: bool
    physio_review_completed: bool
    clinician_restrictions: str = Field(min_length=3, max_length=1200)


class TrainingSession(Model):
    day: str = Field(min_length=1, max_length=100)
    activity: str = Field(min_length=3, max_length=800)
    rest_and_adaptation: str = Field(min_length=3, max_length=600)


class TrainingDraft(Model):
    bodyweight_first_plan: list[TrainingSession] = Field(min_length=1, max_length=7)
    progression_and_limits: str = Field(min_length=3, max_length=1000)
    stopping_and_referral: str = Field(min_length=3, max_length=1000)
    review_question: str = Field(min_length=3, max_length=300)


class BusinessContext(Model):
    owner_facts: list[WorkFact] = Field(min_length=1, max_length=40)
    research_question: str = Field(min_length=5, max_length=2000)
    goals_and_constraints: str = Field(min_length=3, max_length=2000)


class BusinessPoint(Model):
    text: str = Field(min_length=3, max_length=1000)
    owner_fact_ids: list[str] = Field(max_length=10)
    research_conclusion_indexes: list[int] = Field(max_length=6)
    assumption: bool

    @model_validator(mode="after")
    def traceable_or_assumed(self):
        if not self.assumption and not self.owner_fact_ids and not self.research_conclusion_indexes:
            raise ValueError("A business point needs evidence or an explicit assumption label")
        return self


BUSINESS_SECTIONS = {
    "purpose_and_offer", "customers_and_competition", "pricing_and_marketing",
    "operations_and_people", "costs_cashflow_and_funding", "risks_and_obligations",
    "milestones_and_review", "delegating_automating_and_outsourcing",
}


class BusinessSection(Model):
    title: str = Field(min_length=3, max_length=100)
    points: list[BusinessPoint] = Field(min_length=1, max_length=8)


class BusinessDraft(Model):
    sections: list[BusinessSection] = Field(min_length=8, max_length=8)
    missing_information: list[str] = Field(max_length=20)

    @model_validator(mode="after")
    def coverage(self):
        if {s.title for s in self.sections} != BUSINESS_SECTIONS:
            raise ValueError("Business plan must cover all agreed core sections exactly once")
        return self


class Builders:
    def __init__(self, provider: Provider, *, caller_role: str):
        # An internal coordinator facade, not a second subscriber entry point.
        # The trusted application must authenticate this role before construction.
        if caller_role != "chief-of-staff":
            raise PermissionError("Draft builders must be dispatched through the Chief of Staff")
        self.provider = provider

    def meal_plan(self, context: MealContext, *, model_processing_approved: bool):
        if not model_processing_approved:
            raise PermissionError("Approve external processing of the specific food-plan information")
        context = MealContext.model_validate(context)
        if context.clinical_or_specialised_request:
            return {"state": "refer", "reason": "A suitable clinician or dietitian must handle this specialised request."}
        plan = MealPlan.model_validate(self.provider.generate("nutrition", "everyday_meal_plan", {
            "user_information": context.model_dump(mode="json"),
            "instructions": "Everyday food suggestions only. Respect allergies and restrictions; do not invent nutrient totals, health outcomes, treatment or supplement prescriptions. Say 'Based on what you have told us, this food plan could help.' Include substitutions, preparation and a feedback question.",
        }, MealPlan))
        return {"state": "draft_for_review", "review_required": True,
                "allergy_and_restriction_check_required": True,
                "plan": plan.model_dump(mode="json")}

    def career_document(self, kind: Literal["resume", "cover_letter"], context: CareerContext, *,
                        model_processing_approved: bool):
        if not model_processing_approved:
            raise PermissionError("Approve external processing of these career facts")
        if kind not in {"resume", "cover_letter"}:
            raise ValueError("Choose resume or cover_letter")
        context = CareerContext.model_validate(context)
        draft = CareerDraft.model_validate(self.provider.generate("career-business", kind, {
            "user_information": context.model_dump(mode="json"),
            "instructions": "Use only the supplied actual facts. Every line must reference its source fact IDs. Never invent a qualification, date, achievement or employer. Ask for missing information instead. Produce an editable draft.",
        }, CareerDraft))
        available = {f.id for f in context.facts}
        for line in draft.lines:
            if len(set(line.fact_ids)) != len(line.fact_ids) or not set(line.fact_ids) <= available:
                raise ValueError("Career document referenced absent or duplicate user facts")
        return {"state": "draft_for_review", "kind": kind, "review_required": True,
                "claim_entailment_requires_review": True, "document": draft.model_dump(mode="json")}

    def training_plan(self, context: TrainingContext, *, model_processing_approved: bool):
        if not model_processing_approved:
            raise PermissionError("Approve external processing of this training context")
        context = TrainingContext.model_validate(context)
        if not context.doctor_clearance_confirmed:
            return {"state": "refer", "reason": "Obtain the doctor's clearance and restrictions before a personalised training plan."}
        if context.doctor_requested_physio and not context.physio_review_completed:
            return {"state": "refer", "reason": "Complete the doctor's requested physiotherapy review first."}
        draft = TrainingDraft.model_validate(self.provider.generate("physical-development", "bodyweight_first_plan", {
            "user_information": context.model_dump(mode="json"),
            "instructions": "Bodyweight-first training draft within the stated clinician restrictions. No injury rehabilitation prescription, fasting, intensive breathing or heat/cold exposure programme. Include recovery, adaptation, stopping criteria and review.",
        }, TrainingDraft))
        return {"state": "draft_for_review", "review_required": True,
                "clinician_restriction_check_required": True, "plan": draft.model_dump(mode="json")}

    def business_plan(self, context: BusinessContext, team, public_sources, *,
                      model_processing_approved: bool, research_question_approved: bool):
        """Career requests general research via the coordinator, including Finance.

        Only the separately approved general question goes to necessary specialists.
        Owner facts are supplied later to the Career builder, never to the team.
        """
        if not model_processing_approved:
            raise PermissionError("Approve model processing of the business information")
        context = BusinessContext.model_validate(context)
        fact_ids = {f.id for f in context.owner_facts}
        if len(fact_ids) != len(context.owner_facts):
            raise ValueError("Business owner fact IDs must be distinct")
        research = team.discuss(context.research_question, public_sources,
                                approved_for_all_specialists=research_question_approved)
        if not research["synthesis"]:
            return {"state": "needs_research_review", "research": research}
        draft = BusinessDraft.model_validate(self.provider.generate("career-business", "business_plan", {
            "owner_information": context.model_dump(mode="json"),
            "coordinator_research": research["synthesis"],
            "required_sections": sorted(BUSINESS_SECTIONS),
            "instructions": "Separate owner facts, referenced research and explicit assumptions. Do not invent current economic statistics or arithmetic. Include cash-flow and break-even inputs still needing deterministic checks, legal/referral gaps and measurable review milestones.",
        }, BusinessDraft))
        conclusions = research["synthesis"]["conclusions"]
        for section in draft.sections:
            for point in section.points:
                if (not set(point.owner_fact_ids) <= fact_ids or
                    len(set(point.owner_fact_ids)) != len(point.owner_fact_ids) or
                    len(set(point.research_conclusion_indexes)) != len(point.research_conclusion_indexes) or
                    any(i < 0 or i >= len(conclusions) for i in point.research_conclusion_indexes)):
                    raise ValueError("Business plan cited absent or duplicate inputs")
        return {"state": "draft_for_review", "review_required": True,
                "financial_calculations_require_checking": True,
                "plan": draft.model_dump(mode="json"), "research": research}
