"""Whole-field decisions, optional evidence and explicit human review; no network."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from biotracebench.common import read, write, digest
from biotracebench_scoring.evaluation import score
from biotracebench_scoring import scoring_judge as judge
from model_api import Backend
from test_biotracebench_alignment import CLINICAL, ROOT, dictionary
import test_biotracebench_scoring_judge as fixtures


class WholeFieldTests(unittest.TestCase):
    def setUp(self):
        self.policy = read(ROOT/'configs/tasks/biotracebench-scoring-v2.json')
        self.policy['identity_task_rules'] = {}  # No real task identities in this synthetic study.
        self.policy['frozen'] = True
        self.gold = copy.deepcopy(CLINICAL)
        self.gold['result'][0]['supplementary_statistics'] = 'Arm A n=80; Arm B n=75; P<0.05'

    def evaluate(self, value):
        prediction = copy.deepcopy(self.gold)
        prediction['result'][0]['supplementary_statistics'] = value
        return prediction, score(prediction, self.gold, dictionary(self.gold), self.policy)

    def test_same_whole_field_needs_no_judge_or_citation(self):
        raw = self.gold['result'][0]['supplementary_statistics']
        prediction, result = self.evaluate(raw.replace('<', '＜') + '  ')
        self.assertEqual(result['field']['f1'], 1)
        self.assertFalse(result['adjudication_queue'])
        self.assertEqual(prediction['result'][0]['supplementary_statistics'], raw.replace('<', '＜') + '  ')
        items = result['scoring_items']['result']['prediction'][0]['items']
        self.assertIn('supplementary_statistics', items)
        self.assertFalse(any(k.startswith('supplementary_statistics.') for k in items))

    def test_reorder_omission_swapped_roles_and_comparator_need_whole_field_decision(self):
        for value in ['Arm B n=75; Arm A n=80; P<0.05', 'Arm A n=80',
                      'Arm A n=75; Arm B n=80; P<0.05', 'Arm A n=80; Arm B n=75; P=0.05']:
            with self.subTest(value=value):
                prediction, result = self.evaluate(value)
                queue = [q for q in result['adjudication_queue'] if q['kind']=='text_equivalence']
                self.assertEqual(len(queue), 1)
                q = queue[0]
                self.assertEqual(q['comparison_unit'], 'whole_field')
                self.assertEqual(result['field']['gold'] - result['field']['tp'], 1)
                self.assertEqual(result['field']['predicted'], result['field']['gold'])
                equal = value.startswith('Arm B')
                decisions = {'contexts': {result['context_id']: {'equivalences': {
                    q['id']: {'equal': equal, 'basis': 'Synthetic human whole-field review'}}}}}
                final = score(prediction, self.gold, dictionary(self.gold), self.policy, decisions)
                self.assertEqual(final['gold_field_correctness']['result:0:supplementary_statistics'], equal)
                self.assertEqual(final['field']['gold'] - final['field']['tp'], 0 if equal else 1)

    def test_equal_statistics_with_different_unit_context_not_automatically_equal(self):
        prediction = copy.deepcopy(self.gold)
        prediction['result'][0]['result_unit'] = 'different unit'
        result = score(prediction, self.gold, dictionary(self.gold), self.policy)
        self.assertTrue(any(q.get('field')=='supplementary_statistics' for q in result['adjudication_queue']))

    def test_matching_answers_prepare_zero_judge_requests_without_evidence(self):
        _, result = self.evaluate(self.gold['result'][0]['supplementary_statistics'])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write(root/'scores.json', [{'case_id':'C001','conditions':{'SSR':result}}])
            write(root/'context.json', {})
            write(root/'budget.json', {})
            prepared = judge.prepare(root/'scores.json',root/'context.json',fixtures.PROFILE,root/'budget.json',root/'plan')
            self.assertEqual(prepared['eligible_items'],0)
            self.assertEqual(prepared['paid_calls'],0)

    def test_semantic_judge_allows_no_source_and_unresolved_human_review(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root = Path(temp)
            helper = fixtures.JudgeTests()
            helper.plan(root)
            contexts = read(root/'evidence.json')
            for support in contexts.values():
                support['sources'] = []
            write(root/'context.json', contexts)
            judge.prepare(root/'scores.json',root/'context.json',fixtures.PROFILE,root/'budget.json',root/'plan2')
            packets = read(root/'plan2/review-packets.json')
            self.assertNotIn('ssr', json.dumps(packets))
            self.assertNotIn('context_id', json.dumps(packets))
            def sender(*args):
                value={'verdict':'uncertain','rationale':'Source-defined abbreviation requires confirmation.','evidence_ids':[]}
                response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}],
                          'usage':{'prompt_tokens':100,'completion_tokens':20}}
                return 200,{},json.dumps(response).encode()
            judge.execute(root/'plan2',root/'run',backend=Backend(fixtures.PROFILE,sender=sender))
            template = read(root/'run/review-template.json')
            template[0].update(reviewer='synthetic',basis='Cannot determine abbreviation without source.',reviewed_at='2026-10-28')
            write(root/'review.json',template)
            result=judge.apply_reviews(root/'plan2',root/'run',root/'review.json',root/'pending')
            self.assertEqual(result['remaining'],1)
            self.assertEqual(result['decided'],0)
            self.assertEqual(read(root/'pending/adjudications.json'),{'contexts':{}})


if __name__=='__main__':
    unittest.main()
