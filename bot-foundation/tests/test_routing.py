import unittest
from pydantic import ValidationError
from corepath_bots.contracts import Domain
from corepath_bots.demo import DemoProvider, demo_sources
from corepath_bots.provider import ProviderError
from corepath_bots.team import Team, Limits


class Routed(DemoProvider):
    def __init__(self, domains):
        super().__init__()
        self.domains = domains

    def generate(self, role, stage, context, contract):
        if stage == 'select_necessary_specialists':
            self.calls.append((role, stage, context))
            return {'domains': self.domains, 'rationale': 'These fields are relevant in this synthetic case.'}
        return super().generate(role, stage, context, contract)


class RoutingTests(unittest.TestCase):
    def discuss(self, provider, **kwargs):
        return Team(provider).discuss('Demonstrate relevant domain selection.', demo_sources(),
                                      approved_for_all_specialists=True, **kwargs)

    def test_default_auto_does_not_fill_eleven_or_run_automatic_review(self):
        p = Routed([Domain.NUTRITION])
        result = self.discuss(p)
        self.assertEqual(result['state'], 'completed')
        self.assertEqual(result['calls_attempted'], 4)
        self.assertEqual(result['assessed_domains'], [Domain.NUTRITION])
        self.assertFalse(result['full_team_assessed'])
        self.assertFalse(any(c[1] == 'peer_review' for c in p.calls))
        self.assertEqual(len(result['synthesis']['feedback']), 1)
        self.assertEqual(len(p.calls[0][2]['available_specialists']), 11)

    def test_customer_ceiling_allows_one_two_ten_or_eleven_when_necessary(self):
        for n in (1, 2, 10, 11):
            with self.subTest(n=n):
                p = Routed(list(Domain)[:n])
                result = self.discuss(p, max_specialists=n)
                self.assertEqual(result['state'], 'completed')
                self.assertEqual(len(result['contributions']), n)
                self.assertEqual(result['calls_attempted'], n + 3)
                self.assertEqual(result['full_team_assessed'], n == 11)

    def test_ceiling_does_not_force_unnecessary_specialists(self):
        result = self.discuss(Routed([Domain.PRACTICAL]), max_specialists=10)
        self.assertEqual(len(result['contributions']), 1)

    def test_necessary_cross_field_coverage_exceeding_budget_stops_before_dispatch(self):
        p = Routed([Domain.PHYSICAL, Domain.NUTRITION])
        result = self.discuss(p, max_specialists=1)
        self.assertEqual(result['state'], 'needs_selection_change')
        self.assertEqual(len(p.calls), 1)
        self.assertEqual(result['assessed_domains'], [])
        self.assertEqual(len(result['recommended_domains']), 2)
        self.assertIsNone(result['persy_draft'])

    def test_explicit_full_team_retains_all_eleven_and_optional_review(self):
        result = self.discuss(DemoProvider(), mode='full')
        self.assertEqual(result['calls_attempted'], 24)
        self.assertTrue(result['full_team_assessed'])
        result = self.discuss(DemoProvider(), mode='full', review_round=False)
        self.assertEqual(result['calls_attempted'], 13)

    def test_invalid_or_duplicate_routing_never_falls_back_to_full_team(self):
        for domains in ([], ['invented'], [Domain.PERSONAL, Domain.PERSONAL]):
            p = Routed(domains)
            with self.assertRaises(ValidationError):
                self.discuss(p)
            self.assertEqual(len(p.calls), 1)

    def test_ceiling_and_mode_are_validated_before_paid_routing(self):
        for kwargs in ({'max_specialists':0}, {'max_specialists':12}, {'max_specialists':True},
                       {'mode':'unknown'}, {'mode':'full','max_specialists':2}):
            p = DemoProvider()
            with self.assertRaises(ValueError):
                self.discuss(p, **kwargs)
            self.assertFalse(p.calls)

    def test_remaining_call_budget_prevents_dispatch(self):
        p = Routed([Domain.PERSONAL, Domain.FINANCIAL])
        result = Team(p, Limits(max_calls=4)).discuss('Demonstrate a bounded question.', demo_sources(),
                       approved_for_all_specialists=True)
        self.assertEqual(result['state'], 'needs_selection_change')
        self.assertEqual(len(p.calls), 1)

    def test_unavailable_selected_specialist_is_partial(self):
        class Broken(Routed):
            def generate(self, role, stage, context, contract):
                if role == Domain.NUTRITION:
                    raise ProviderError('Unavailable')
                return super().generate(role, stage, context, contract)
        result = self.discuss(Broken([Domain.PERSONAL, Domain.NUTRITION]))
        self.assertEqual(result['state'], 'partial')
        self.assertFalse(result['full_team_assessed'])

    def test_feedback_cannot_invent_unconsulted_or_duplicate_specialists(self):
        class InvalidFeedback(Routed):
            def generate(self, role, stage, context, contract):
                result = super().generate(role, stage, context, contract)
                if stage == 'evaluate_and_give_feedback':
                    result['feedback'] *= 2
                return result
        result = self.discuss(InvalidFeedback([Domain.NUTRITION]))
        self.assertEqual(result['state'], 'partial')
        self.assertIsNone(result['persy_draft'])

    def test_peer_request_outside_selected_team_is_visible_not_silently_ignored(self):
        class Peer(Routed):
            def generate(self, role, stage, context, contract):
                result = super().generate(role, stage, context, contract)
                if role == Domain.NUTRITION:
                    result['peer_requests'] = [Domain.PHYSICAL]
                return result
        result = self.discuss(Peer([Domain.NUTRITION]))
        self.assertEqual(result['state'], 'partial')
        self.assertTrue(any('additional_specialist_review_needed' in i for i in result['issues']))
