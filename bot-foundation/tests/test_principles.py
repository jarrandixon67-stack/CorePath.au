"""Prevent the older services and replacement foundation drifting in policy."""

import json
import sys
import unittest
from pathlib import Path

from corepath_bots.principles import principles, render_principles
from corepath_bots.registry import instructions, roles

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if not BACKEND.exists():
    BACKEND = ROOT / "CorePath.au" / "backend"
sys.path.insert(0, str(BACKEND))

from bot_standards import AGREED_PRINCIPLES  # noqa: E402
from coordinator.limits import MAX_SPECIALIST_CALLS, MAX_TEAM_BOTS  # noqa: E402
from coordinator.models import ResearchRequest  # noqa: E402
from persy.models import ResearchProposal  # noqa: E402
from specialists.registry import Domain  # noqa: E402
from pydantic import ValidationError  # noqa: E402


class AgreedPrincipleTests(unittest.TestCase):
    def test_old_and_new_services_receive_identical_agreed_principles(self):
        snapshot = json.loads((BACKEND / "bot_standards" / "agreed-principles.json").read_text())
        self.assertEqual(snapshot, principles())
        self.assertEqual(AGREED_PRINCIPLES, render_principles())
        for role in roles():
            self.assertIn(AGREED_PRINCIPLES, instructions(role))

    def test_policy_ids_are_unique_and_separate_authority_from_evidence(self):
        entries = principles()["principles"]
        self.assertEqual(len(entries), len({p["id"] for p in entries}))
        by_id = {p["id"]: p["instruction"] for p in entries}
        self.assertIn("Only the founder", by_id["twelve"])
        self.assertIn("preserves meaningful disagreement", by_id["collaboration"])
        self.assertIn("never proof", by_id["evidence"])

    def test_all_eleven_are_valid_across_the_old_request_boundaries(self):
        payload = {"question": "A full authorised research question.", "allowed_domains": list(Domain),
                   "max_specialist_calls": 11, "allow_collaboration": True}
        self.assertEqual(MAX_SPECIALIST_CALLS, 11)
        self.assertEqual(MAX_TEAM_BOTS, 12)
        for contract in (ResearchRequest, ResearchProposal):
            self.assertEqual(contract.model_validate(payload).max_specialist_calls, 11)
            with self.assertRaises(ValidationError):
                contract.model_validate({**payload, "max_specialist_calls": 12})
        self.assertEqual(ResearchRequest(question=payload["question"], allowed_domains=list(Domain)).max_specialist_calls, 11)


if __name__ == "__main__":
    unittest.main()
