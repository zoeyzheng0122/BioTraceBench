"""Synthetic identity contract and blinded human review regressions."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import test_biotracebench_alignment as fixtures
from test_biotracebench_alignment import BASIC, CLINICAL
from biotracebench_scoring.identity_alignment import scoped_policy
from biotracebench_scoring.identity_review import prepare, apply
from model_conversation.archive import write, read


class IdentityContractTests(unittest.TestCase):
    setUp = fixtures.AlignmentTests.setUp
    evaluate = fixtures.AlignmentTests.evaluate

    def test_strong_experiment_identity_survives_wrong_link(self):
        reference = copy.deepcopy(BASIC)
        reference['assay_run'][0]['experiment_run_accession'] = 'Synthetic:E1 (experiment)'
        prediction = copy.deepcopy(reference)
        prediction['assay_run'][0]['sample_ids'] = ['UNKNOWN']
        result = self.evaluate(prediction, reference)
        self.assertEqual(result['pairs']['assay_run'], [{'prediction': 0, 'gold': 0}])
        self.assertFalse(result['gold_field_correctness']['assay_run:0:sample_ids'])
        self.assertTrue(result['gold_field_correctness']['assay_run:0:platform'])

    def test_parent_attribute_error_does_not_invalidate_child(self):
        prediction = copy.deepcopy(CLINICAL)
        prediction['population'][0]['population_size'] = 999
        result = self.evaluate(prediction, CLINICAL)
        self.assertEqual(result['pairs']['result'], [{'prediction': 0, 'gold': 0}])
        self.assertFalse(result['gold_field_correctness']['population:0:population_size'])
        self.assertTrue(result['gold_field_correctness']['result:0:result_value'])

    def test_exact_duplicate_retained_and_child_alias_resolved(self):
        prediction = copy.deepcopy(BASIC)
        prediction['sample'].append({**prediction['sample'][0], 'sample_id': 'S2'})
        prediction['condition'][0]['sample_id'] = 'S2'
        result = self.evaluate(prediction)
        self.assertEqual(len(result['pairs']['sample']), 1)
        self.assertEqual(result['record']['predicted'], 4)
        self.assertEqual(result['record']['tp'], 3)
        self.assertTrue(result['gold_field_correctness']['condition:0:sample_id'])
        self.assertIn('duplicate_prediction', [a['status'] for a in result['alignment_audit']['sample']])

    def test_nonidentical_competitors_never_selected_by_accuracy(self):
        prediction = copy.deepcopy(BASIC)
        prediction['sample'].append({**prediction['sample'][0], 'sample_id': 'S2', 'species': 'wrong'})
        result = self.evaluate(prediction)
        self.assertEqual(result['pairs']['sample'], [])

    def test_shared_experiment_id_is_not_unique(self):
        reference = copy.deepcopy(BASIC)
        reference['assay_run'].append({**reference['assay_run'][0], 'assay_id': 'A2', 'platform': 'Other'})
        self.assertEqual(self.evaluate(BASIC, reference)['pairs']['assay_run'], [])

    def test_task_native_label_is_frozen_and_not_guessed(self):
        reference = copy.deepcopy(BASIC)
        reference['assay_run'][0]['experiment_run_accession'] = None
        reference['assay_run'][0]['method'] = 'Run-17; acquisition method'
        self.assertEqual(self.evaluate(reference, reference)['pairs']['assay_run'], [])
        policy = copy.deepcopy(self.policy)
        policy['identity_task_rules'] = {'B001': {
            'basis': 'Synthetic source names each acquisition Run-N.',
            'identity_native_labels': {'assay_run': {'method': {
                'pattern': r'\b(?P<identity>Run-\d+)\b', 'basis': 'Synthetic acquisition labels'}}},
            'identity_strong_groups': {'assay_run': [['method']]}}}
        with self.assertRaises(ValueError):
            scoped_policy(policy, None)
        effective = scoped_policy(policy, {'case_id': 'B001'})
        effective['identity_task_rules'] = {}
        prediction = copy.deepcopy(reference)
        prediction['assay_run'][0]['sample_ids'] = ['UNKNOWN']
        self.assertEqual(self.evaluate(prediction, reference, effective)['pairs']['assay_run'],
                         [{'prediction': 0, 'gold': 0}])

    def test_identity_review_is_blinded_sealed_and_replayable(self):
        prediction = copy.deepcopy(CLINICAL)
        prediction['result'][0]['comparison'] = 'P2 minus P1'
        result = self.evaluate(prediction, CLINICAL)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root/'scores.json', [{'case_id': 'C001', 'conditions': {'SSR': result, 'GSR': result}}])
            prepare(root/'scores.json', root/'plan')
            self.assertEqual(len(read(root/'plan/review-packets.json')['packets']), 1)
            packet = read(root/'plan/review-packets.json')['packets'][0]
            self.assertNotIn('SSR', json.dumps(packet))
            self.assertNotIn('result_value', json.dumps(packet))
            review = {'id': packet['id'], 'verdict': 'match', 'candidate': packet['candidates'][0]['id'],
                      'basis': 'Source confirms object; submitted direction is incorrect.',
                      'evidence': [{'source': 'synthetic.txt', 'locator': 'Table 1 row 1'}]}
            write(root/'reviews.json', [review])
            apply(root/'plan', root/'reviews.json', root/'resolved')
            scored = self.evaluate(prediction, CLINICAL, decisions=read(root/'resolved/adjudications.json'))
            self.assertEqual(scored['pairs']['result'], [{'prediction': 0, 'gold': 0}])
            self.assertFalse(scored['gold_field_correctness']['result:0:comparison'])
            write(root/'reviews.json', [review, review])
            with self.assertRaises(ValueError):
                apply(root/'plan', root/'reviews.json', root/'duplicate')
            write(root/'plan/private-routes.json', {})
            with self.assertRaises((ValueError, RuntimeError)):
                apply(root/'plan', root/'reviews.json', root/'tampered')

    def test_human_evidence_required_and_unresolved_does_not_force_pair(self):
        prediction = copy.deepcopy(CLINICAL)
        prediction['result'][0]['comparison'] = 'P2 minus P1'
        result = self.evaluate(prediction, CLINICAL)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root/'scores.json', [{'case_id': 'C001', 'conditions': {'SSR': result}}])
            prepare(root/'scores.json', root/'plan')
            entry = read(root/'plan/review-template.json')[0]
            write(root/'reviews.json', [entry])
            with self.assertRaisesRegex(ValueError, 'source/locator'):
                apply(root/'plan', root/'reviews.json', root/'invalid')
            entry.update(basis='Source remains ambiguous', evidence=[{'source': 'synthetic.txt', 'locator': 'Table 1'}])
            write(root/'reviews.json', [entry])
            apply(root/'plan', root/'reviews.json', root/'pending')
            self.assertEqual(read(root/'pending/adjudications.json'), {'contexts': {}})
            entry['verdict'] = 'nonmatch'
            write(root/'reviews.json', [entry])
            apply(root/'plan', root/'reviews.json', root/'nonmatch')
            resolved = self.evaluate(prediction, CLINICAL, decisions=read(root/'nonmatch/adjudications.json'))
            self.assertEqual(resolved['pairs']['result'], [])
            self.assertEqual(resolved['alignment_audit']['result'][0]['status'], 'human_nonmatch')


if __name__ == '__main__':
    unittest.main()
