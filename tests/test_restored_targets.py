"""Restored targets remain subject to explicit scientific verdicts and omissions."""
from pathlib import Path
from copy import deepcopy
import json, tempfile, unittest
from biotracebench_analysis.replay.io import write, csvwrite, read
from biotracebench_analysis.replay.scoring import projected
from biotracebench_scoring.task_grading_contract import inventory, mark_all

def fixture(omit=False, wrong_time=False):
    dictionary = {'condition': {'identifier': 'condition_id', 'references': {}, 'fields': [{'key': f} for f in ['condition_id', 'factor_value', 'factor_unit', 'time']]}}
    policy = {'reference_contract': 'biotracebench-fixed-reference-1', 'field_roles': {'condition.' + f: 'identifier' if f == 'condition_id' else 'scientific' for f in ['condition_id', 'factor_value', 'factor_unit', 'time']}}
    gold = {'condition': [{'condition_id': 'C1', 'factor_value': 100, 'factor_unit': 'micrograms/mL', 'time': '48h'}]}
    pred = {'condition': []} if omit else deepcopy(gold)
    if wrong_time:
        pred['condition'][0]['time'] = '24h'
    inv = inventory(pred, gold, dictionary, policy)
    rr = {r['side']: r for r in inv['rows']}
    cc = {(c['side'], c['field']): c for c in inv['cells']}
    marks = []
    for f in ['condition_id', 'factor_value', 'factor_unit', 'time']:
        p = cc.get(('prediction', f))
        g = cc['reference', f]
        role = g['role']
        verdict = 'not_scored' if role != 'scientific' else 'missing' if not p else 'incorrect' if f == 'time' and wrong_time else 'correct'
        marks.append({'prediction_cell': p['id'] if p else None, 'reference_cell': g['id'], 'category': role, 'verdict': verdict, 'reason': 'Explicit synthetic source judgment.'})
    marking = {'records': [{'prediction_row': rr.get('prediction', {}).get('id'), 'reference_row': rr['reference']['id'], 'verdict': 'missing' if omit else 'matched', 'reason': 'Explicit synthetic scientific identity.'}], 'cells': marks, 'reference_issues': []}
    assert not mark_all(inv, marking)['unresolved_items']
    return (gold, {'inventory': inv, 'marking': marking})
OLD = [{'case': 'B000', 'table': 'condition', 'row_index': 0, 'field_exclusions': ['factor_value', 'factor_unit'], 'main_record_scoring': 'excluded'}]
NEW = [{**OLD[0], 'field_exclusions': [], 'main_record_scoring': 'included'}]

class RestoredTargetTests(unittest.TestCase):

    def test_missing_restored_answer_adds_targets_without_true_positives(self):
        _, p = fixture(omit=True)
        a = projected(p['inventory'], p['marking'], 'B000', OLD)
        b = projected(p['inventory'], p['marking'], 'B000', NEW)
        self.assertEqual(b['field']['gold'], a['field']['gold'] + 2)
        self.assertEqual(b['field']['tp'], 0)
        self.assertEqual(b['record']['tp'], 0)
        self.assertEqual(b['record']['gold'], 1)
        self.assertEqual(b['record']['predicted'], 0)

    def test_independent_error_still_blocks_restored_complete_record(self):
        _, p = fixture(wrong_time=True)
        b = projected(p['inventory'], p['marking'], 'B000', NEW)
        self.assertEqual(b['field']['tp'], 2)
        self.assertEqual(b['record']['tp'], 0)
        self.assertEqual(b['record']['gold'], 1)
