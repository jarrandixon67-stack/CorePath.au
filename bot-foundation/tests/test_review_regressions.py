"""Regressions found by the second code review, beyond the original happy paths."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from corepath_bots.contracts import Contribution, Domain, PersyReply
from corepath_bots.demo import DemoProvider, demo_sources
from corepath_bots.life_profile import Consent, Evidence, LifeProfile, Message, Observation, ProfileProposal
from corepath_bots.provider import OpenAIProvider, ProviderError
from corepath_bots.registry import SPECIALIST_IDS, instructions, policy_hash
from corepath_bots.storage import Store
from corepath_bots.team import Team
from corepath_bots.twelve import KnowledgeReview, PublicFinding, Twelve
from corepath_bots.workflows import Builders


class OutputPreservationTests(unittest.TestCase):
    def test_coordinator_cannot_erase_specialist_warnings_or_referrals(self):
        class Warnings(DemoProvider):
            def generate(self, role_id, stage, context, contract):
                output = super().generate(role_id, stage, context, contract)
                if role_id == Domain.PHYSICAL:
                    output["gaps"] = ["Important fixture uncertainty retained from the specialist."]
                    output["questions"] = ["A material fixture question?"]
                    output["referral_reason"] = "A qualified fixture review is needed."
                if role_id in SPECIALIST_IDS:
                    output["claims"][0]["limitations"] = "A critical limitation in the supporting source."
                return output
        result = Team(Warnings()).discuss("Check warning preservation.", demo_sources(), approved_for_all_specialists=True, mode="full")
        for text in ("Important fixture uncertainty", "A material fixture question?",
                     "A qualified fixture review", "A critical limitation"):
            self.assertIn(text, result["persy_draft"])
        self.assertEqual(result["referral_needs"][0]["domain"], Domain.PHYSICAL)
        self.assertIn("https://example.invalid/corepath-demo", result["persy_draft"])

    def test_no_findings_does_not_claim_completed_research(self):
        class NoEvidence(DemoProvider):
            def generate(self, role_id, stage, context, contract):
                output = super().generate(role_id, stage, context, contract)
                if role_id in SPECIALIST_IDS:
                    output["claims"] = []
                if role_id == "chief-of-staff":
                    output["conclusions"] = []
                return output
        result = Team(NoEvidence()).discuss("Check missing evidence.", [], approved_for_all_specialists=True, mode="full")
        self.assertEqual(len(result["contributions"]), 11)
        self.assertEqual(result["state"], "needs_evidence")

    def test_copied_source_cannot_bypass_public_approval_validation(self):
        source = demo_sources()[0].model_copy(update={"public": False})
        with self.assertRaises(ValidationError):
            Team(DemoProvider()).discuss("Check copied approval flags.", [source], approved_for_all_specialists=True, mode="full")


class ProviderFailureTests(unittest.TestCase):
    def request(self, payload):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        opener = MagicMock()
        opener.open.return_value = response
        with patch.dict("os.environ", {"OPENAI_API_KEY": "synthetic-test-key", "COREPATH_MODEL": "synthetic-model"}), \
             patch("corepath_bots.provider.urllib.request.build_opener", return_value=opener):
            return OpenAIProvider(allow_model_processing=True).generate("persy", "test", {}, PersyReply)

    def test_nonobject_response_is_a_controlled_failure(self):
        for payload in ([], None, "unexpected text", 1):
            with self.subTest(payload=payload), self.assertRaises(ProviderError):
                self.request(payload)

    def test_malformed_nested_output_is_a_controlled_failure(self):
        for output in (None, ["bad item"], [{"type": "message", "content": ["bad part"]}],
                       [{"type": "message", "content": None}]):
            with self.subTest(output=output), self.assertRaises(ProviderError):
                self.request({"status": "completed", "output": output})

    def test_valid_response_still_validates_contract(self):
        data = {"opening": "A fixture greeting.", "conclusion_indexes": [], "closing_question": None}
        actual = self.request({"status": "completed", "output": [
            {"type": "reasoning"}, {"type": "message", "content": [{"type": "output_text", "text": json.dumps(data)}]}]})
        self.assertEqual(actual, data)


class StagePolicyTests(unittest.TestCase):
    def test_research_and_drafting_use_different_explicit_contracts(self):
        research = instructions("nutrition", "initial_assessment")
        draft = instructions("nutrition", "everyday_meal_plan")
        self.assertIn("Every factual claim needs an exact source ID", research)
        self.assertNotIn("Every factual claim needs an exact source ID", draft)
        self.assertIn("Chief-of-Staff-authorised drafting job", draft)
        self.assertIn("no Life Profile", draft)
        self.assertNotEqual(policy_hash("nutrition", "initial_assessment"),
                            policy_hash("nutrition", "everyday_meal_plan"))

    def test_unsupported_specialist_stage_is_not_a_permission(self):
        with self.assertRaises(ValueError):
            instructions("nutrition", "send_bank_records")

    def test_draft_builders_require_coordinator_dispatch(self):
        for role in ("persy", "nutrition", "12", "unknown"):
            with self.assertRaises(PermissionError):
                Builders(DemoProvider(), caller_role=role)


class ProfileReviewTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.profile = LifeProfile(self.store)
        self.consent = Consent(purpose="Personal support", analysis_enabled=True, model_processing=True,
                               sensitive_enabled=False, categories=["habits"])
        self.revision = self.profile.set_consent("owner", self.consent)
        self.messages = [Message(id="m1", conversation_id="c1", text="I enjoy gardening.",
                                 categories=["habits"], sensitive=False)]
        self.proposal = ProfileProposal(observations=[Observation(category="habits", statement="Enjoys gardening.",
            kind="user_statement", sensitive=False, evidence=[Evidence(message_id="m1", quote="I enjoy gardening")])], follow_up=None)

    def tearDown(self):
        self.store.close()

    def record(self, messages=None):
        return self.profile.record_proposal("owner", "Personal support", messages or self.messages,
            self.proposal, consent_revision=self.revision)["proposal_ids"][0]

    def test_sensitive_correction_cannot_reuse_nonsensitive_permission(self):
        item = self.record()
        with self.assertRaises(PermissionError):
            self.profile.review("owner", item, "accept", correction="A correction that may include private details.", share_persy=True)
        self.assertEqual(self.profile.context("persy", "owner", {"habits"}), [])

    def test_private_correction_is_marked_sensitive(self):
        item = self.record()
        self.profile.review("owner", item, "accept", correction="A correction kept private.")
        self.assertTrue(self.profile.inspect("owner")[0]["sensitive"])

    def test_duplicate_message_ids_cannot_forge_pattern_provenance(self):
        with self.assertRaises(ValueError):
            self.record(self.messages * 2)

    def test_input_requires_category_permission_before_provider_receives_it(self):
        provider = DemoProvider()
        self.profile.provider = provider
        other = self.messages[0].model_copy(update={"categories": ["relationships"]})
        with self.assertRaises(PermissionError):
            self.profile.analyse("owner", "Personal support", [other])
        self.assertEqual(provider.calls, [])

    def test_sensitive_input_cannot_be_sent_then_discarded_afterwards(self):
        provider = DemoProvider()
        self.profile.provider = provider
        sensitive = self.messages[0].model_copy(update={"sensitive": True})
        with self.assertRaises(PermissionError):
            self.profile.analyse("owner", "Personal support", [sensitive])
        self.assertEqual(provider.calls, [])

    def test_direct_recording_cannot_bypass_model_consent(self):
        self.revision = self.profile.set_consent("owner", self.consent.model_copy(update={"model_processing": False}))
        with self.assertRaises(PermissionError):
            self.record()

    def test_erase_and_recreate_cannot_reuse_an_old_consent_revision(self):
        old_revision = self.revision
        self.profile.erase_owner("owner")
        new_revision = self.profile.set_consent("owner", self.consent)
        self.assertGreater(new_revision, old_revision)
        with self.assertRaises(PermissionError):
            self.record()

    def test_evidence_keeps_conversation_provenance(self):
        self.record()
        evidence = json.loads(self.profile.inspect("owner")[0]["evidence"])
        self.assertEqual(evidence[0]["conversation_id"], "c1")

    def test_unreviewed_input_classification_is_not_guessed(self):
        with self.assertRaises(ValidationError):
            Message(id="raw", conversation_id="c1", text="An unclassified conversation.")

    def test_permission_read_is_inside_a_write_lock(self):
        trace = []
        self.store.db.set_trace_callback(trace.append)
        self.record()
        begin = next(i for i, q in enumerate(trace) if q.startswith("BEGIN IMMEDIATE"))
        check = next(i for i, q in enumerate(trace) if "SELECT * FROM consent" in q)
        insert = next(i for i, q in enumerate(trace) if q.startswith("INSERT INTO observations"))
        self.assertLess(begin, check)
        self.assertLess(check, insert)

    def test_failed_proposal_rolls_back_all_records(self):
        self.proposal.observations.append(self.proposal.observations[0].model_copy(deep=True))
        self.proposal.observations[1].evidence[0].quote = "An invented quotation"
        with self.assertRaises(ValueError):
            self.record()
        self.assertEqual(self.profile.inspect("owner"), [])
        self.assertFalse(self.store.db.in_transaction)


class TwelveReviewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = str(Path(self.directory.name) / "knowledge.sqlite")
        self.store = Store(self.path)
        self.twelve = Twelve(self.store, DemoProvider(), founder_id="founder")
        claim = Contribution.model_validate(DemoProvider().generate("nutrition", "initial", {}, Contribution)).claims[0]
        self.finding = PublicFinding(id="f1", domain=Domain.NUTRITION, claim=claim, sources=demo_sources())
        KnowledgeReview(self.store).accept(self.finding, reviewer="human", reviewed_as_nonpersonal=True, independent_review_complete=True)

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def test_old_report_flags_later_evidence_retraction(self):
        self.twelve.enable("founder")
        self.twelve.run("founder")
        self.assertEqual(self.twelve.reports("founder")[0]["evidence_state"], "current")
        KnowledgeReview(self.store).retract("f1")
        self.assertEqual(self.twelve.reports("founder")[0]["evidence_state"], "needs_review")

    def test_duplicate_source_ids_in_reviewed_knowledge_are_rejected(self):
        with self.assertRaises(ValidationError):
            PublicFinding(id="ambiguous", domain=Domain.NUTRITION, claim=self.finding.claim, sources=demo_sources() * 2)

    def test_shutdown_from_another_connection_during_call_discards_output(self):
        path = self.path
        class ExternalShutdown(DemoProvider):
            def generate(self, *args, **kwargs):
                other = Store(path)
                try:
                    Twelve(other, DemoProvider(), founder_id="founder").shutdown("founder")
                finally:
                    other.close()
                return {"ideas": [], "issues": []}
        self.twelve.provider = ExternalShutdown()
        self.twelve.enable("founder")
        with self.assertRaises(PermissionError):
            self.twelve.run("founder")
        self.assertEqual(self.twelve.reports("founder"), [])

    def test_final_status_and_evidence_checks_are_locked_before_insert(self):
        self.twelve.enable("founder")
        trace = []
        self.store.db.set_trace_callback(trace.append)
        self.twelve.run("founder")
        insert = next(i for i, q in enumerate(trace) if q.startswith("INSERT INTO twelve_reports"))
        begin = max(i for i, q in enumerate(trace[:insert]) if q.startswith("BEGIN IMMEDIATE"))
        status = max(i for i, q in enumerate(trace[:insert]) if "SELECT enabled,generation" in q)
        sources = max(i for i, q in enumerate(trace[:insert]) if "SELECT id,payload FROM findings" in q)
        self.assertLess(begin, status)
        self.assertLess(begin, sources)


if __name__ == "__main__":
    unittest.main()
