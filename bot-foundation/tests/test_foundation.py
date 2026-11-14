import json
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pydantic import ValidationError

from corepath_bots.contracts import Contribution, Domain, Source
from corepath_bots.demo import DemoProvider, demo_sources
from corepath_bots.life_profile import (Consent, LifeProfile, Location, LocationDirectory,
                                       LocationFact, Message, Observation, ProfileProposal, Evidence)
from corepath_bots.partners import (NegotiationAuthority, PartnerCandidate, Terms, evaluate)
from corepath_bots.provider import ProviderError
from corepath_bots.registry import SPECIALIST_IDS, instructions, policy_hash, roles
from corepath_bots.reminders import ReminderPreference, daily_invitation
from corepath_bots.storage import Store
from corepath_bots.team import InvalidEvidence, Limits, Team, validate_contribution
from corepath_bots.tools import bmi, budget, compare_decisions, number, smart_goal
from corepath_bots.twelve import KnowledgeReview, PublicFinding, Twelve
from corepath_bots.workflows import (Builders, CareerContext, WorkFact, MealContext,
                                     TrainingContext, BusinessContext, BUSINESS_SECTIONS)


class TeamTests(unittest.TestCase):
    def test_full_team_reviews_then_coordinates_and_presents(self):
        provider = DemoProvider()
        report = Team(provider).discuss("How can we demonstrate the workflow?", demo_sources(),
                                        approved_for_all_specialists=True)
        self.assertEqual(report["state"], "completed")
        self.assertEqual(report["calls_attempted"], 24)
        self.assertEqual(len(report["contributions"]), 11)
        self.assertEqual(len(report["synthesis"]["feedback"]), 11)
        self.assertTrue(report["review_required"])
        self.assertIn("not specialist expertise", report["persy_draft"])
        review_calls = [c for c in provider.calls if c[1] == "peer_review"]
        self.assertEqual(len(review_calls), 11)
        for role_id, stage, context in review_calls:
            peers = context["peer_briefs_routed_by_chief_of_staff"]
            self.assertEqual(set(peers), set(SPECIALIST_IDS) - {role_id})
            self.assertTrue(all("Synthetic workflow" in c["summary"] for c in peers.values()))

    def test_question_needs_explicit_whole_team_authorisation(self):
        provider = DemoProvider()
        with self.assertRaises(PermissionError):
            Team(provider).discuss("A private question", [], approved_for_all_specialists=False)
        self.assertFalse(provider.calls)

    def test_nothing_relevant_is_valid(self):
        contribution = Contribution(relevant=False, summary="Nothing relevant to add.",
                                    claims=[], questions=[], gaps=[], peer_requests=[], referral_reason=None)
        validate_contribution(Domain.PERSONAL, contribution, [])

    def test_missing_source_or_wrong_quote_rejected(self):
        proposal = DemoProvider().generate(Domain.PERSONAL.value, "initial", {}, Contribution)
        contribution = Contribution.model_validate(proposal)
        with self.assertRaises(InvalidEvidence):
            validate_contribution(Domain.PERSONAL, contribution, [])
        contribution.claims[0].citations[0].quote = "This text does not occur in the source"
        with self.assertRaises(InvalidEvidence):
            validate_contribution(Domain.PERSONAL, contribution, demo_sources())

    def test_source_cannot_cross_domain_scope(self):
        source = demo_sources()[0].model_copy(update={"domains": [Domain.NUTRITION]})
        contribution = Contribution.model_validate(DemoProvider().generate(Domain.PERSONAL.value, "initial", {}, Contribution))
        with self.assertRaises(InvalidEvidence):
            validate_contribution(Domain.PERSONAL, contribution, [source])

    def test_duplicate_source_ids_rejected_before_calls(self):
        provider = DemoProvider()
        with self.assertRaises(ValueError):
            Team(provider).discuss("Demonstrate duplicates", demo_sources() * 2,
                                    approved_for_all_specialists=True)
        self.assertFalse(provider.calls)

    def test_invalid_initial_output_yields_explicit_partial_report(self):
        class Broken(DemoProvider):
            def generate(self, role_id, stage, context, contract):
                if role_id == Domain.PHYSICAL:
                    raise ProviderError("Unavailable")
                return super().generate(role_id, stage, context, contract)
        report = Team(Broken()).discuss("Demonstrate a partial team", demo_sources(),
                                        approved_for_all_specialists=True)
        self.assertEqual(report["state"], "partial")
        self.assertNotIn(Domain.PHYSICAL, report["contributions"])
        self.assertTrue(any("initial_unavailable" in issue for issue in report["issues"]))
        self.assertLessEqual(report["calls_attempted"], 24)

    def test_invalid_review_retains_valid_initial_finding(self):
        class Broken(DemoProvider):
            def generate(self, role_id, stage, context, contract):
                result = super().generate(role_id, stage, context, contract)
                if stage == "peer_review" and role_id == Domain.NUTRITION:
                    result["claims"][0]["citations"][0]["quote"] = "An invented quotation"
                return result
        report = Team(Broken()).discuss("Demonstrate review failures", demo_sources(), approved_for_all_specialists=True)
        self.assertEqual(report["state"], "partial")
        self.assertEqual(report["contributions"][Domain.NUTRITION], report["initial_contributions"][Domain.NUTRITION])

    def test_synthesis_cannot_cite_absent_claim(self):
        class Broken(DemoProvider):
            def generate(self, role_id, stage, context, contract):
                result = super().generate(role_id, stage, context, contract)
                if role_id == "chief-of-staff":
                    result["conclusions"][0]["references"][0]["index"] = 2
                return result
        report = Team(Broken()).discuss("Demonstrate evidence validation", demo_sources(), approved_for_all_specialists=True)
        self.assertIsNone(report["synthesis"])
        self.assertIsNone(report["persy_draft"])
        self.assertEqual(report["state"], "partial")

    def test_confidence_cannot_exceed_supporting_claim(self):
        class Inflated(DemoProvider):
            def generate(self, role_id, stage, context, contract):
                result = super().generate(role_id, stage, context, contract)
                if role_id == "chief-of-staff":
                    result["conclusions"][0]["confidence"] = "high"
                return result
        report = Team(Inflated()).discuss("Demonstrate confidence bounds", demo_sources(), approved_for_all_specialists=True)
        self.assertEqual(report["synthesis"]["conclusions"][0]["confidence"], "low")

    def test_persy_cannot_drop_conclusions(self):
        class Drops(DemoProvider):
            def generate(self, role_id, stage, context, contract):
                result = super().generate(role_id, stage, context, contract)
                if role_id == "persy":
                    result["conclusion_indexes"] = []
                return result
        report = Team(Drops()).discuss("Demonstrate presentation checks", demo_sources(), approved_for_all_specialists=True)
        self.assertIsNone(report["persy_draft"])
        self.assertEqual(report["state"], "partial")

    def test_budget_remains_bounded(self):
        report = Team(DemoProvider(), Limits(max_calls=13)).discuss(
            "Demonstrate a smaller call budget", demo_sources(), approved_for_all_specialists=True)
        self.assertEqual(report["calls_attempted"], 13)
        self.assertEqual(len(report["contributions"]), 11)
        self.assertEqual(report["state"], "partial")

    def test_empty_evidence_does_not_fabricate_findings(self):
        report = Team(DemoProvider()).discuss("No supplied evidence is available", [], approved_for_all_specialists=True)
        self.assertFalse(report["contributions"])
        self.assertEqual(report["state"], "partial")

    def test_roles_match_enum_and_all_have_versioned_hashes(self):
        self.assertEqual(set(SPECIALIST_IDS), {d.value for d in Domain})
        self.assertEqual(len(roles()), 16)
        for role_id in roles():
            self.assertEqual(len(policy_hash(role_id)), 64)
            self.assertIn("COREPATH".lower(), instructions(role_id).lower())
        self.assertIn("bodyweight", instructions(Domain.PHYSICAL))
        self.assertIn("Wim Hof", instructions(Domain.MENTAL))
        self.assertIn("worldwide", instructions("life-profile"))


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.profile = LifeProfile(self.store)
        self.consent = Consent(purpose="Personal support", analysis_enabled=True,
                               model_processing=True, sensitive_enabled=True,
                               categories=["identity", "habits", "emotions"])
        self.revision = self.profile.set_consent("alice", self.consent)
        self.messages = [Message(id="m1", conversation_id="c1", text="I enjoy gardening every weekend.")]
        self.proposal = ProfileProposal(observations=[Observation(
            category="habits", statement="Enjoys gardening at weekends.", kind="user_statement",
            sensitive=False, evidence=[Evidence(message_id="m1", quote="I enjoy gardening")])], follow_up=None)

    def tearDown(self):
        self.store.close()

    def record(self):
        return self.profile.record_proposal("alice", "Personal support", self.messages,
            self.proposal, consent_revision=self.revision)["proposal_ids"][0]

    def test_proposal_requires_review_and_explicit_sharing(self):
        item = self.record()
        self.assertEqual(self.profile.context("persy", "alice", {"habits"}), [])
        self.profile.review("alice", item, "accept")
        self.assertEqual(self.profile.context("persy", "alice", {"habits"}), [])
        self.profile.review("alice", item, "accept", share_persy=True)
        self.assertEqual(len(self.profile.context("persy", "alice", {"habits"})), 1)
        self.assertEqual(self.profile.context("chief-of-staff", "alice", {"habits"}), [])

    def test_specialist_and_twelve_cannot_request_profile(self):
        for actor in ("12", "nutrition", "partner"):
            with self.assertRaises(PermissionError):
                self.profile.context(actor, "alice", {"habits"})

    def test_other_owner_cannot_review_or_delete_observation(self):
        item = self.record()
        self.profile.set_consent("bob", self.consent)
        with self.assertRaises(KeyError):
            self.profile.review("bob", item, "accept", share_persy=True)
        self.assertEqual(self.profile.delete("bob", item), 0)
        self.assertEqual(len(self.profile.inspect("alice")), 1)

    def test_changed_consent_rejects_stale_proposal_and_resets_sharing(self):
        item = self.record()
        self.profile.review("alice", item, "accept", share_persy=True)
        self.profile.set_consent("alice", self.consent)
        self.assertEqual(self.profile.context("persy", "alice", {"habits"}), [])
        with self.assertRaises(PermissionError):
            self.record()

    def test_withdrawal_blocks_context_and_new_proposals(self):
        self.record()
        self.profile.set_consent("alice", self.consent.model_copy(update={"analysis_enabled": False}))
        with self.assertRaises(PermissionError):
            self.profile.context("persy", "alice", {"habits"})
        self.assertEqual(len(self.profile.inspect("alice")), 1)

    def test_unmatched_evidence_does_not_save(self):
        self.proposal.observations[0].evidence[0].quote = "An invented quote"
        with self.assertRaises(ValueError):
            self.record()
        self.assertFalse(self.profile.inspect("alice"))

    def test_pattern_requires_separate_conversations(self):
        self.proposal.observations[0].kind = "observed_pattern"
        with self.assertRaises(ValueError):
            self.record()
        self.messages.append(Message(id="m2", conversation_id="c2", text="I enjoy gardening again."))
        self.proposal.observations[0].evidence.append(Evidence(message_id="m2", quote="I enjoy gardening"))
        self.assertTrue(self.record())

    def test_sensitive_without_consent_is_discarded(self):
        self.revision = self.profile.set_consent("alice", self.consent.model_copy(update={"sensitive_enabled": False}))
        self.proposal.observations[0].sensitive = True
        result = self.profile.record_proposal("alice", "Personal support", self.messages, self.proposal, consent_revision=self.revision)
        self.assertEqual(result["proposal_ids"], [])

    def test_owner_correction_and_erase(self):
        item = self.record()
        self.profile.review("alice", item, "accept", correction="Gardens when time permits.", share_persy=True)
        self.assertEqual(self.profile.context("persy", "alice", {"habits"})[0]["kind"], "owner_corrected")
        self.profile.erase_owner("alice")
        self.assertFalse(self.profile.inspect("alice"))

    def test_context_is_bounded_above_fifty_records(self):
        for _ in range(51):
            self.profile.review("alice", self.record(), "accept", share_persy=True)
        self.assertEqual(len(self.profile.context("persy", "alice", {"habits"}, limit=50)), 50)
        with self.assertRaises(ValueError):
            self.profile.context("persy", "alice", {"habits"}, limit=51)

    def test_public_location_is_separate_and_has_freshness(self):
        directory = LocationDirectory(self.store)
        at = datetime.now(UTC)
        location = Location(id="demo-town", name="Demonstration Town", country_code="AU",
                            region="Fixture only", kind="town", timezone="Australia/Sydney",
                            latitude=0, longitude=0, gaps=["Synthetic test; not a real town profile"],
                            facts=[LocationFact(topic="demonstration", statement="A synthetic location record.",
                                    source_url="https://example.invalid", attribution="Test fixture only",
                                    checked_at=at-timedelta(days=3), review_after=at-timedelta(days=1))])
        with self.assertRaises(PermissionError):
            directory.put(location, reviewed_public_record=False)
        directory.put(location, reviewed_public_record=True)
        self.assertTrue(directory.search("demonstration")[0]["facts"][0]["needs_refresh"])
        self.assertFalse(self.profile.inspect("alice"))


class TwelveTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.twelve = Twelve(self.store, DemoProvider(), founder_id="founder-id")
        claim = Contribution.model_validate(DemoProvider().generate("nutrition", "initial", {}, Contribution)).claims[0]
        self.finding = PublicFinding(id="finding-1", domain=Domain.NUTRITION, claim=claim, sources=demo_sources())
        KnowledgeReview(self.store).accept(self.finding, reviewer="human", reviewed_as_nonpersonal=True,
                                           independent_review_complete=True)

    def tearDown(self):
        self.store.close()

    def test_founder_only_assignments_and_permissions(self):
        with self.assertRaises(PermissionError):
            self.twelve.enable("chief-of-staff")
        self.twelve.enable("founder-id")
        with self.assertRaises(PermissionError):
            self.twelve.run("chief-of-staff")
        self.assertTrue(self.twelve.status("chief-of-staff")["enabled"])

    def test_disabled_by_default_and_shutdown_blocks_work(self):
        with self.assertRaises(PermissionError):
            self.twelve.run("founder-id")
        self.twelve.enable("founder-id")
        result = self.twelve.run("founder-id")
        self.assertEqual(result["audience"], "founder_only")
        with self.assertRaises(PermissionError):
            self.twelve.reports("chief-of-staff")
        self.twelve.shutdown("founder-id")
        with self.assertRaises(PermissionError):
            self.twelve.run("founder-id")

    def test_shutdown_during_model_call_discards_result(self):
        twelve = self.twelve
        class KillDuringCall(DemoProvider):
            def generate(self, *args, **kwargs):
                twelve.shutdown("founder-id")
                return {"ideas": [], "issues": []}
        self.twelve.provider = KillDuringCall()
        self.twelve.enable("founder-id")
        with self.assertRaises(PermissionError):
            self.twelve.run("founder-id")
        self.assertEqual(self.twelve.reports("founder-id"), [])

    def test_erase_disables_and_deletes_local_reports(self):
        self.twelve.enable("founder-id")
        self.twelve.run("founder-id")
        self.twelve.erase_local_records("founder-id")
        self.assertEqual(self.twelve.reports("founder-id"), [])
        self.assertFalse(self.twelve.status("chief-of-staff")["enabled"])

    def test_unreviewed_knowledge_cannot_be_accepted(self):
        with self.assertRaises(PermissionError):
            KnowledgeReview(self.store).accept(self.finding, reviewer="human", reviewed_as_nonpersonal=False,
                                               independent_review_complete=True)

    def test_evidence_changed_during_call_discards_report(self):
        store = self.store
        class ChangeDuringCall(DemoProvider):
            def generate(self, *args, **kwargs):
                with store.db as db:
                    db.execute("UPDATE findings SET payload=? WHERE id=?", ("{}", "finding-1"))
                return {"ideas": [], "issues": []}
        self.twelve.provider = ChangeDuringCall()
        self.twelve.enable("founder-id")
        with self.assertRaises(InvalidEvidence):
            self.twelve.run("founder-id")
        self.assertEqual(self.twelve.reports("founder-id"), [])


class ToolAndPartnerTests(unittest.TestCase):
    def test_budget_converts_frequencies_with_decimal_math(self):
        result = budget([{"amount": "1000", "frequency": "fortnightly"}],
                        [{"amount": "100", "frequency": "weekly"}, {"amount": "200", "frequency": "monthly"}])
        self.assertEqual(result["annual_income"], "26000.00")
        self.assertEqual(result["annual_expenses"], "7600.00")
        self.assertEqual(result["monthly_average_surplus"], "1533.33")

    def test_invalid_numeric_and_negative_inputs_rejected(self):
        for value in ("NaN", "Infinity", True, "not a number"):
            with self.assertRaises(ValueError):
                number(value)
        with self.assertRaises(ValueError):
            budget([], [{"amount": -10, "frequency": "weekly"}])

    def test_bmi_units_and_child_scope(self):
        self.assertEqual(bmi(80, 180, adult=True)["bmi"], "24.7")
        with self.assertRaises(ValueError):
            bmi(80, 1.8, adult=True)
        with self.assertRaises(ValueError):
            bmi(40, 150, adult=False)

    def test_weighted_decision_is_explicit_and_not_a_command(self):
        result = compare_decisions({"fit": 2, "affordability": 1},
                                   {"A": {"fit": 9, "affordability": 3}, "B": {"fit": 6, "affordability": 9}})
        self.assertEqual(result["scores"], {"A": "7.00", "B": "7.00"})
        self.assertIn("not a decision", result["limits"])

    def test_smart_goal_needs_real_fields(self):
        with self.assertRaises(ValueError):
            smart_goal(specific="", measure="a", feasible_step="a", relevance="a", deadline="a", review_date="a", accountability="a")

    def test_partner_terms_respect_founder_limits(self):
        candidate = PartnerCandidate(name="Demonstration Provider", category="activity",
                                     customer_benefit="A suitable local activity.", evidence_urls=["https://example.invalid"],
                                     suitability_reviewed=True, commission_compatible=True, concerns=[])
        authority = NegotiationAuthority(approved_template_id="reviewed-template", allowed_benefits=["introductory visit"])
        result = evaluate(candidate, Terms(proposed_benefits=["introductory visit"]), authority)
        self.assertEqual(result["state"], "within_negotiating_limits")
        self.assertFalse(result["outreach_executed"])
        for terms in (Terms(commission_basis_points=900), Terms(corepath_spend=Decimal("1")),
                      Terms(exclusivity=True), Terms(binding_contract=True), Terms(data_sharing=True),
                      Terms(proposed_benefits=["unapproved discount"])):
            self.assertEqual(evaluate(candidate, terms, authority)["state"], "needs_founder_or_review")

    def test_reminder_opt_in_quiet_hours_and_duplicate_suppression(self):
        preference = ReminderPreference(enabled=True, hour=17)
        at = datetime(2026, 11, 14, 6, tzinfo=UTC)  # 17:00 Sydney in November
        draft = daily_invitation(preference, at)
        self.assertFalse(draft["delivery_executed"])
        self.assertIsNone(daily_invitation(preference, at, last_local_date="2026-11-14"))
        self.assertIsNone(daily_invitation(ReminderPreference(enabled=False), at))
        self.assertIsNone(daily_invitation(ReminderPreference(enabled=True, hour=23), datetime(2026,11,14,12,tzinfo=UTC)))


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.provider = DemoProvider()
        self.builders = Builders(self.provider)
        self.meal = MealContext(goals="Everyday meals", preferences="Simple foods", allergies=[],
                                budget_and_access="Modest budget", facilities_and_skills="A home kitchen",
                                routine_and_activity="Variable work routine", restrictions="None reported",
                                clinical_or_specialised_request=False)
        self.training = TrainingContext(goal="Build everyday strength", capability_and_equipment="Beginner at home",
                            doctor_clearance_confirmed=False, doctor_requested_physio=False,
                            physio_review_completed=False, clinician_restrictions="Not yet reviewed")
        self.career = CareerContext(facts=[WorkFact(id="fact-1", text="Maintained a home garden.")],
                                    target_role="Gardening assistant", job_description="Help maintain gardens.")

    def test_specialised_food_request_refers_without_model_call(self):
        self.meal.clinical_or_specialised_request = True
        result = self.builders.meal_plan(self.meal, model_processing_approved=True)
        self.assertEqual(result["state"], "refer")
        self.assertFalse(self.provider.calls)

    def test_builders_require_explicit_model_processing(self):
        for operation in (
            lambda: self.builders.meal_plan(self.meal, model_processing_approved=False),
            lambda: self.builders.training_plan(self.training, model_processing_approved=False),
            lambda: self.builders.career_document("resume", self.career, model_processing_approved=False),
        ):
            with self.assertRaises(PermissionError):
                operation()
        self.assertFalse(self.provider.calls)

    def test_training_requires_doctor_then_requested_physio(self):
        self.assertEqual(self.builders.training_plan(self.training, model_processing_approved=True)["state"], "refer")
        self.training.doctor_clearance_confirmed = True
        self.training.doctor_requested_physio = True
        self.assertEqual(self.builders.training_plan(self.training, model_processing_approved=True)["state"], "refer")
        self.assertFalse(self.provider.calls)

    def test_career_builder_rejects_invented_fact_references(self):
        class CareerProvider(DemoProvider):
            def generate(self, role_id, stage, context, contract):
                return {"title": "Resume draft", "lines": [{"text": "Invented qualification", "fact_ids": ["not-supplied"]}],
                        "missing_information": []}
        with self.assertRaises(ValueError):
            Builders(CareerProvider()).career_document("resume", self.career, model_processing_approved=True)

    def test_resume_and_cover_letter_are_editable_referenced_drafts(self):
        class CareerProvider(DemoProvider):
            def generate(self, role_id, stage, context, contract):
                return {"title": stage, "lines": [{"text": "Experience maintaining a home garden.", "fact_ids": ["fact-1"]}],
                        "missing_information": ["Confirm dates and contact details."]}
        for kind in ("resume", "cover_letter"):
            result = Builders(CareerProvider()).career_document(kind, self.career, model_processing_approved=True)
            self.assertEqual(result["state"], "draft_for_review")
            self.assertTrue(result["claim_entailment_requires_review"])

    def test_business_research_goes_through_full_team_without_owner_facts(self):
        class BusinessProvider(DemoProvider):
            def generate(self, role_id, stage, context, contract):
                if stage == "business_plan":
                    return {"sections": [{"title": title, "points": [{"text": "A proposed planning assumption.",
                            "owner_fact_ids": [], "research_conclusion_indexes": [], "assumption": True}]}
                            for title in BUSINESS_SECTIONS], "missing_information": ["Validate market demand."]}
                return super().generate(role_id, stage, context, contract)
        provider = BusinessProvider()
        owner_text = "Private owner fact withheld from team."
        context = BusinessContext(owner_facts=[WorkFact(id="private-fact", text=owner_text)],
                                  research_question="Demonstrate general market research workflow.",
                                  goals_and_constraints="Build a small service business.")
        result = Builders(provider).business_plan(context, Team(provider), demo_sources(),
                    model_processing_approved=True, research_question_approved=True)
        self.assertEqual(result["state"], "draft_for_review")
        specialist_calls = [c for c in provider.calls if c[0] in SPECIALIST_IDS]
        self.assertEqual(len(specialist_calls), 22)
        self.assertTrue(all(owner_text not in json.dumps(c[2]) for c in specialist_calls))

    def test_business_research_requires_approved_question(self):
        context = BusinessContext(owner_facts=[WorkFact(id="f1", text="A private business fact.")],
                                  research_question="General market research question.", goals_and_constraints="Build carefully.")
        with self.assertRaises(PermissionError):
            self.builders.business_plan(context, Team(self.provider), demo_sources(),
                         model_processing_approved=True, research_question_approved=False)
        self.assertFalse(self.provider.calls)


if __name__ == "__main__":
    unittest.main()
