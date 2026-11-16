import copy
import unittest

from model_conversation.archive import digest
from biotracebench_scoring.context_accounting import FORMAT, apply_context_accounting
from biotracebench_scoring.evaluation import metrics


class ContextAccountingTests(unittest.TestCase):
    def setUp(self):
        self.score = {
            'status': 'native_scoring_completed', 'unresolved_items': 0,
            'field': metrics(2, 3, 3), 'record': metrics(0, 2, 1),
            'logical': {}, 'physical': {}, 'known_field_counts': {}, 'mark_counts': {},
            'gold_field_correctness': {},
            'field_items': [
                {'id': 'required', 'owner_key': 'result:0:value', 'reference_row': 'r0', 'prediction_row': 'p0', 'gold': True, 'predicted': True, 'verdict': 'correct', 'correct': True},
                {'id': 'sample_n', 'owner_key': 'result:0:sample_n', 'reference_row': 'r0', 'prediction_row': 'p0', 'gold': True, 'predicted': True, 'verdict': 'correct', 'correct': True},
                {'id': 'missing', 'owner_key': 'result:0:missing', 'reference_row': 'r0', 'prediction_row': 'p0', 'gold': True, 'predicted': False, 'verdict': 'missing', 'correct': False},
            ],
            'record_items': [
                {'prediction_row': 'p0', 'reference_row': 'r0', 'verdict': 'matched', 'correct': False, 'schema_missing_fields': []},
                {'prediction_row': 'p1', 'reference_row': None, 'verdict': 'extra', 'correct': False, 'schema_missing_fields': []},
            ],
            'residual_extras': [{'cell': 'c1', 'owner_row': 'p1'}],
        }
        self.inv = {'rows': [{'id': 'p0', 'side': 'prediction'}, {'id': 'p1', 'side': 'prediction'}],
                    'cells': [{'id': 'c1', 'row': 'p1', 'role': 'scientific', 'nonempty': True}]}
        self.sources = [{'id': 's', 'text': 'The analysis included eleven people per arm.'}]
        self.decision = {'format': FORMAT, 'actor': 'Codex', 'base_score_identity': digest(self.score),
                         'reference_context_fields': [{'field_id': 'sample_n', 'prediction_class': 'context', 'reason': 'The count is already expressed in the analysis population.', 'evidence': [{'source_id': 's', 'quote': 'eleven people per arm'}]}],
                         'optional_prediction_records': [{'prediction_row': 'p1', 'accepted_cells': ['c1'], 'reason': 'This is an explicitly linked analysis context.', 'evidence': [{'source_id': 's', 'quote': 'eleven people per arm'}]}]}

    def test_valid_context_does_not_hide_a_missing_required_field(self):
        original = copy.deepcopy(self.score)
        result = apply_context_accounting(self.score, self.inv, self.sources, self.decision)
        self.assertEqual(self.score, original)
        self.assertEqual(result['field'], metrics(1, 1, 2))
        self.assertEqual(result['record'], metrics(0, 1, 1))
        self.assertEqual(result['residual_extras'], [])

    def test_source_review_can_clear_a_prior_missing_repeat_penalty(self):
        self.score['field_items'][1].update(verdict='incorrect', correct=False)
        self.score['field'] = metrics(1, 3, 3)
        self.decision['base_score_identity'] = digest(self.score)
        result = apply_context_accounting(self.score, self.inv, self.sources, self.decision)
        self.assertEqual(result['field'], metrics(1, 1, 2))
        self.assertEqual(result['field_items'][1]['original_verdict'], 'incorrect')
        self.assertEqual(result['field_items'][1]['verdict'], 'not_scored')

    def test_wrong_context_expression_remains_extra(self):
        self.score['field_items'][1].update(verdict='incorrect', correct=False)
        self.decision['reference_context_fields'][0]['prediction_class'] = 'incorrect'
        self.score['field'] = metrics(1, 3, 3)
        self.decision['base_score_identity'] = digest(self.score)
        result = apply_context_accounting(self.score, self.inv, self.sources, self.decision)
        self.assertEqual(result['field'], metrics(1, 2, 2))
        self.assertEqual(result['field_items'][1]['verdict'], 'extra')
        self.assertFalse(result['record_items'][0]['correct'])

    def test_requires_full_record_coverage_and_source_bound_score(self):
        self.decision['optional_prediction_records'][0]['accepted_cells'] = []
        with self.assertRaisesRegex(ValueError, 'cover every'):
            apply_context_accounting(self.score, self.inv, self.sources, self.decision)
        self.decision['optional_prediction_records'][0]['accepted_cells'] = ['c1']
        self.decision['reference_context_fields'][0]['evidence'][0]['quote'] = 'twelve people'
        with self.assertRaisesRegex(ValueError, 'actual source'):
            apply_context_accounting(self.score, self.inv, self.sources, self.decision)
        self.decision['base_score_identity'] = 'stale'
        with self.assertRaisesRegex(ValueError, 'exact base score'):
            apply_context_accounting(self.score, self.inv, self.sources, self.decision)


if __name__ == '__main__':
    unittest.main()
