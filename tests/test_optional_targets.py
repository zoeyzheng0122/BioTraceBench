"""Optional control answers are neutral; wrong values and identities still cost."""
from copy import deepcopy
import unittest
from biotracebench_scoring.task_grading_contract import inventory, mark_all
from biotracebench_analysis.replay.scoring import projected

def packet(mode='zero', rename=False):
    fields = {'sample': ['sample_id', 'sample_name'], 'condition': ['condition_id', 'sample_id', 'factor_value']}
    dictionary = {t: {'identifier': ff[0], 'references': {'sample_id': 'sample'} if t == 'condition' else {}, 'fields': [{'key': f} for f in ff]} for t, ff in fields.items()}
    policy = {'reference_contract': 'biotracebench-fixed-reference-1', 'field_roles': {t + '.' + f: 'identifier' if f == ff[0] else 'scientific' for t, ff in fields.items() for f in ff}}
    gold = {'sample': [{'sample_id': 'S1', 'sample_name': 'control'}, {'sample_id': 'S2', 'sample_name': 'treated'}], 'condition': [{'condition_id': 'C0', 'sample_id': 'S1', 'factor_value': 0}]}
    pred = deepcopy(gold)
    if mode == 'omit':
        pred['condition'] = []
    if mode == 'wrong_value':
        pred['condition'][0]['factor_value'] = 1
    if mode == 'wrong_target':
        pred['condition'][0]['sample_id'] = 'S2'
    if mode == 'duplicate':
        pred['condition'].append({**pred['condition'][0], 'condition_id': 'Cextra'})
    if rename:
        for r in pred['sample']:
            r['sample_id'] = {'S1': 'arbitrary-control', 'S2': 'arbitrary-treated'}[r['sample_id']]
        for r in pred['condition']:
            r['sample_id'] = {'S1': 'arbitrary-control', 'S2': 'arbitrary-treated'}[r['sample_id']]
            r['condition_id'] = 'id-' + r['condition_id']
        pred['sample'].reverse()
    inv = inventory(pred, gold, dictionary, policy)
    rr = {(r['side'], r['table'], r['row_index']): r for r in inv['rows']}
    cc = {(c['row'], c['field']): c for c in inv['cells']}
    records, marks = ([], [])
    for table in fields:
        for i in range(max(len(gold[table]), len(pred[table]))):
            pr = rr.get(('prediction', table, i))
            gi = 1 - i if rename and table == 'sample' else i
            gr = rr.get(('reference', table, gi))
            rec = {'prediction_row': pr['id'] if pr else None, 'reference_row': gr['id'] if gr else None, 'verdict': 'matched' if pr and gr else 'missing' if gr else 'extra', 'reason': 'Explicit synthetic scientific identity.'}
            records.append(rec)
            for f in fields[table]:
                pc = cc.get((pr['id'], f)) if pr else None
                gc = cc.get((gr['id'], f)) if gr else None
                role = (gc or pc)['role']
                bad = table == 'condition' and (mode == 'wrong_value' and f == 'factor_value' or (mode == 'wrong_target' and f == 'sample_id'))
                verdict = 'not_scored' if role != 'scientific' else 'incorrect' if bad else 'correct' if pc and gc else 'missing' if gc else 'extra'
                marks.append({'prediction_cell': pc['id'] if pc else None, 'reference_cell': gc['id'] if gc else None, 'category': role, 'verdict': verdict, 'reason': 'Explicit synthetic field adjudication.'})
    result = {'inventory': inv, 'marking': {'records': records, 'cells': marks, 'reference_issues': []}}
    assert not mark_all(inv, result['marking'])['unresolved_items']
    return result
MASK = [{'case': 'B004', 'table': 'condition', 'row_index': 0, 'field_exclusions': ['*'], 'main_record_scoring': 'excluded', 'answer_policy': 'optional_neutral'}]

def score(p):
    return projected(p['inventory'], p['marking'], 'B004', MASK)

class OptionalTargetTests(unittest.TestCase):

    def test_unresolved_optional_value_blocks_direct_scoring(self):
        review = packet()
        cells = {cell['id']: cell for cell in review['inventory']['cells']}
        optional_value = next(mark for mark in review['marking']['cells']
                              if cells[mark['reference_cell']]['field'] == 'factor_value')
        optional_value['verdict'] = 'uncertain'
        with self.assertRaisesRegex(ValueError, 'applicable scientific uncertainty'):
            score(review)

    def test_zero_and_omission_are_equal_without_added_credit(self):
        self.assertEqual(score(packet()), score(packet('omit')))
        self.assertEqual(score(packet())['field']['tp'], 2)
        self.assertEqual(score(packet())['record']['gold'], 2)

    def test_wrong_value_and_binding_retain_one_field_and_record_penalty(self):
        for mode in ['wrong_value', 'wrong_target']:
            with self.subTest(mode=mode):
                m = score(packet(mode))
                good = score(packet())
                self.assertEqual(m['field']['tp'], good['field']['tp'])
                self.assertEqual(m['field']['predicted'], good['field']['predicted'] + 1)
                self.assertEqual(m['record']['predicted'], good['record']['predicted'] + 1)

    def test_second_zero_row_is_still_extra(self):
        m = score(packet('duplicate'))
        good = score(packet())
        self.assertEqual(m['field']['predicted'], good['field']['predicted'] + 2)
        self.assertEqual(m['record']['predicted'], good['record']['predicted'] + 1)

    def test_consistent_ids_and_row_order_do_not_change_the_policy(self):
        for mode in ['zero', 'omit', 'wrong_value', 'wrong_target', 'duplicate']:
            with self.subTest(mode=mode):
                self.assertEqual(score(packet(mode)), score(packet(mode, True)))
