import copy
import unittest

from model_conversation.archive import digest
from biotracebench_scoring.evaluation import metrics
from biotracebench_scoring.partial_context_accounting import FORMAT, apply_partial_context_accounting


class PartialContextAccountingTests(unittest.TestCase):
    def setUp(self):
        self.score = {'status': 'native_scoring_completed', 'unresolved_items': 0,
                      'field': metrics(2, 5, 3), 'record': metrics(1, 2, 2),
                      'logical': {'field': metrics(2, 5, 3), 'record': metrics(1, 2, 2)},
                      'known_field_counts': {}, 'mark_counts': {'correct': 2, 'extra': 3},
                      'record_items': [{'prediction_row': 'p1', 'reference_row': None, 'verdict': 'extra', 'correct': False}],
                      'residual_extras': [{'cell': 'good1', 'owner_row': 'p1'}, {'cell': 'good2', 'owner_row': 'p1'}, {'cell': 'wrong', 'owner_row': 'p1'}]}
        self.inventory = {'rows': [{'id': 'p1', 'side': 'prediction'}],
                          'cells': [{'id': x, 'row': 'p1', 'role': 'scientific', 'nonempty': True}
                                    for x in ('good1', 'good2', 'wrong')]}
        self.sources = [{'id': 's', 'text': 'The two analysis arms had 142 and 146 participants.'}]
        self.decision = {'format': FORMAT, 'actor': 'Codex', 'base_score_identity': digest(self.score),
                         'partial_context_records': [{'prediction_row': 'p1', 'valid_context_cells': ['good1', 'good2'],
                                                     'incorrect_cells': ['wrong'], 'reason': 'The combined count is not directly reported.',
                                                     'evidence': [{'source_id': 's', 'quote': '142 and 146 participants'}]}]}

    def test_valid_cells_are_not_extra_but_wrong_cell_and_record_remain(self):
        old = copy.deepcopy(self.score)
        new = apply_partial_context_accounting(self.score, self.inventory, self.sources, self.decision)
        self.assertEqual(self.score, old)
        self.assertEqual(new['field'], metrics(2, 3, 3))
        self.assertEqual(new['record'], old['record'])
        self.assertEqual([x['cell'] for x in new['residual_extras']], ['wrong'])
        self.assertEqual(new['record_items'][0]['verdict'], 'extra')

    def test_rejects_incomplete_and_unverifiable_classifications(self):
        self.decision['partial_context_records'][0]['valid_context_cells'] = ['good1']
        with self.assertRaisesRegex(ValueError, 'every nonempty'):
            apply_partial_context_accounting(self.score, self.inventory, self.sources, self.decision)
        self.decision['partial_context_records'][0]['valid_context_cells'] = ['good1', 'good2']
        self.decision['partial_context_records'][0]['evidence'][0]['quote'] = 'directly reported 288'
        with self.assertRaisesRegex(ValueError, 'actual source'):
            apply_partial_context_accounting(self.score, self.inventory, self.sources, self.decision)

    def test_wrong_cell_already_used_elsewhere_requires_new_review(self):
        self.score['residual_extras'] = [x for x in self.score['residual_extras'] if x['cell'] != 'wrong']
        self.decision['base_score_identity'] = digest(self.score)
        with self.assertRaisesRegex(ValueError, 'independently counted residual'):
            apply_partial_context_accounting(self.score, self.inventory, self.sources, self.decision)


if __name__ == '__main__':
    unittest.main()
