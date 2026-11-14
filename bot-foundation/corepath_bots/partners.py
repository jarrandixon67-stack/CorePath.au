"""Deterministic proposal evaluation. No mail, signing or financial transactions."""

from decimal import Decimal

from pydantic import Field

from .contracts import Model


class PartnerCandidate(Model):
    name: str = Field(min_length=1, max_length=250)
    category: str = Field(min_length=1, max_length=100)
    customer_benefit: str = Field(min_length=3, max_length=1000)
    evidence_urls: list[str] = Field(min_length=1, max_length=20)
    suitability_reviewed: bool
    commission_compatible: bool
    concerns: list[str] = Field(max_length=20)


class Terms(Model):
    commission_basis_points: int = Field(default=1000, ge=0, le=10000)
    corepath_spend: Decimal = Field(default=Decimal("0"), ge=0, allow_inf_nan=False)
    exclusivity: bool = False
    guarantees: bool = False
    data_sharing: bool = False
    binding_contract: bool = False
    proposed_benefits: list[str] = Field(default_factory=list, max_length=20)


class NegotiationAuthority(Model):
    approved_template_id: str | None = Field(default=None, max_length=100)
    allowed_benefits: list[str] = Field(default_factory=list, max_length=50)
    # Agreed initial mandate: financial changes require the founder.
    commission_basis_points: int = Field(default=1000, ge=1000, le=1000)


def evaluate(candidate: PartnerCandidate, terms: Terms, authority: NegotiationAuthority) -> dict:
    candidate = PartnerCandidate.model_validate(candidate)
    terms = Terms.model_validate(terms)
    authority = NegotiationAuthority.model_validate(authority)
    reasons = []
    if not candidate.suitability_reviewed:
        reasons.append("Complete the suitability and evidence review")
    if terms.commission_basis_points and not candidate.commission_compatible:
        reasons.append("Commission compatibility needs review")
    if not authority.approved_template_id:
        reasons.append("Founder-approved offer template is not configured")
    if terms.commission_basis_points != authority.commission_basis_points:
        reasons.append("Commission change requires the founder")
    if terms.corepath_spend:
        reasons.append("Spending requires the founder")
    for key in ("exclusivity", "guarantees", "data_sharing", "binding_contract"):
        if getattr(terms, key):
            reasons.append(f"{key.replace('_', ' ').capitalize()} requires the founder")
    if not set(terms.proposed_benefits) <= set(authority.allowed_benefits):
        reasons.append("Customer benefit is outside approved negotiating limits")
    return {"partner": candidate.name, "customer_benefit": candidate.customer_benefit,
            "terms": terms.model_dump(mode="json"), "evidence": candidate.evidence_urls,
            "concerns": candidate.concerns,
            "state": "needs_founder_or_review" if reasons else "within_negotiating_limits",
            "reasons": reasons, "outreach_executed": False, "commitment_made": False,
            "recommendation": "Resolve the listed reviews before proceeding." if reasons else
            "Prepare a nonbinding discussion using the approved template; no signing authority is granted."}
