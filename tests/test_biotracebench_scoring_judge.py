"""Synthetic-only intake, boundary and Qwen judge regression tests."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from biotracebench.common import read, write, seal, digest
from biotracebench_scoring.evaluation import score
from biotracebench_scoring.scoring_input import load_submission
from biotracebench_scoring import scoring_judge as judge
from model_api import Backend
from test_biotracebench_scoring_items import GOLD, DICT, POLICY

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT/'configs/models/profiles/qwen3.8-max-judge.json'

class JudgeTests(unittest.TestCase):
    def test_unknown_fields_not_counted_by_key_count(self):
        pred = copy.deepcopy(GOLD)
        pred['result'][0]['extra'] = 'unknown content'
        pred['unrecognized'] = [{'a': 1, 'b': 2}]
        value = score(pred, GOLD, DICT, POLICY)
        self.assertEqual(value['field']['predicted'], 7)
        self.assertEqual(value['record']['predicted'], 1)
        self.assertEqual(value['status'], 'provisional')
        self.assertEqual(sum(q['kind']=='content_classification' for q in value['adjudication_queue']),2)

    def test_conflicting_requires_content_review_not_only_label(self):
        gold = copy.deepcopy(GOLD)
        gold['result'][0]['result_value'] = 'Source A: 0; Source B: 1'
        first = score(gold, gold, DICT, POLICY)
        states = {first['scoring_items']['result'][side][0]['items']['result_value']['field_id']:
                  {'state':'conflicting','basis':'Both alternatives checked in synthetic source'} for side in ('prediction','reference')}
        decision = {'contexts': {first['context_id']: {'field_states': states}}}
        second = score(gold, gold, DICT, POLICY, decision)
        self.assertEqual(second['field']['tp'],6)
        q = next(q for q in second['adjudication_queue'] if q['kind']=='state_equivalence')
        decision['contexts'][first['context_id']]['equivalences'] = {q['id']:{'equal':True,'basis':'Same alternatives and source attribution'}}
        result = score(gold, gold, DICT, POLICY, decision)
        self.assertEqual(result['field']['f1'],1)
        self.assertEqual(result['status'],'final_under_frozen_dictionary')

    def test_waiting_not_failed_and_raw_partial_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(ValueError,'Scoring deferred'):
                load_submission(root,'SYN','i0')
            write(root/'status.json',{'tasks':{'SYN':{'i0':'failed_validation'}}})
            self.assertIsNone(load_submission(root,'SYN','i0')[0])
            final = root/'SYN/i0/final'
            write(final/'database.json',None)
            (final/'raw-answer.txt').write_text(json.dumps({'database':GOLD,'review':{}}))
            seal(final)
            result,intake = load_submission(root,'SYN','i0')
            self.assertEqual(result,GOLD)
            self.assertEqual(intake['availability'],'partial_from_exact_json')
            (final/'database.json').write_text('{}')
            with self.assertRaises(Exception): load_submission(root,'SYN','i0')

    def plan(self, root, budget=None):
        gold=copy.deepcopy(GOLD); gold['result'][0]['result_value']='not estimable'
        pred=copy.deepcopy(gold); pred['result'][0]['result_value']='NE'
        result=score(pred,gold,DICT,POLICY)
        q=next(q for q in result['adjudication_queue'] if q['kind']=='text_equivalence')
        write(root/'scores.json',[{'case_id':'SYN','conditions':{'ssr':result}}])
        write(root/'evidence.json',{result['context_id']+':'+q['id']:{'task_definition':'Extract the synthetic endpoint.',
              'field_rule':'NE means not estimable in this source.',
              'sources':[{'id':'e1','source':'synthetic.txt','locator':'line 1','text':'NE: not estimable.'}]}})
        write(root/'budget.json',budget or {'max_requests':1,'per_request_cny':1,'total_cny':1,
              'max_input_cny_per_million':1,'max_output_cny_per_million':1,
              'price_source':'synthetic tariff, not live','price_verified_at':'2026-10-26'})
        judge.prepare(root/'scores.json',root/'evidence.json',PROFILE,root/'budget.json',root/'plan')
        return pred,gold,result

    def transport(self, calls, bad=False, missing_usage=False):
        def sender(endpoint,body,headers,timeout):
            calls.append(json.loads(body))
            content={'verdict':'equivalent','rationale':'Same source-defined meaning.','evidence_ids':['fake' if bad else 'e1']}
            payload={'model':'qwen3.8-max-0902','choices':[{'finish_reason':'stop','message':{'content':json.dumps(content)}}]}
            if not missing_usage:payload['usage']={'prompt_tokens':100,'completion_tokens':20}
            return 200,{},json.dumps(payload).encode()
        return Backend(PROFILE,sender=sender)

    def test_full_roundtrip_human_review_offline_no_second_call(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp); pred,gold,original=self.plan(root);calls=[]
            backend=self.transport(calls)
            result=judge.execute(root/'plan',root/'run',backend=backend)
            self.assertEqual(result['status'],'awaiting_human_review')
            self.assertNotIn('ssr',json.dumps(calls))
            self.assertNotIn('context_id',json.dumps(calls))
            proposal=read(root/'run/proposals.json')[0]
            # No automatic score change before explicit review.
            self.assertEqual(score(pred,gold,DICT,POLICY)['status'],'provisional')
            with patch.dict('os.environ',{},clear=True):
                judge.execute(root/'plan',root/'run',offline=True,backend=Backend(PROFILE,sender=lambda *a: self.fail('network')))
            self.assertEqual(len(calls),1)
            write(root/'reviews.json',[{'id':proposal['id'],'proposal_identity':digest(proposal),'equal':True,
                'reviewer':'synthetic-reviewer','basis':'Independently checked synthetic definition.','reviewed_at':'2026-10-26'}])
            judge.apply_reviews(root/'plan',root/'run',root/'reviews.json',root/'reviewed')
            final=score(pred,gold,DICT,POLICY,read(root/'reviewed/adjudications.json'))
            self.assertEqual(final['field']['f1'],1)
            self.assertEqual(final['status'],'final_under_frozen_dictionary')
            self.assertIsNone(read(root/'run/costs.json')['requests'][0]['exact_cny'])
            for path in (root/'run').rglob('*'):
                if path.is_file():self.assertNotIn(b'synthetic-secret',path.read_bytes())

    def test_budget_rejects_before_call(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.plan(root,{'max_requests':1,'per_request_cny':0.0001,'total_cny':1,
                'max_input_cny_per_million':1,'max_output_cny_per_million':1,'price_source':'synthetic','price_verified_at':'2026-10-26'})
            calls=[]
            with self.assertRaisesRegex(ValueError,'budget'):judge.execute(root/'plan',root/'run',backend=self.transport(calls))
            self.assertFalse(calls)

    def test_bad_reference_and_missing_usage_stop(self):
        from unittest.mock import patch
        for bad,missing in [(True,False),(False,True)]:
            with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
                root=Path(temp);self.plan(root);calls=[]
                with self.assertRaises(ValueError):judge.execute(root/'plan',root/'run',backend=self.transport(calls,bad,missing))
                self.assertEqual(len(calls),1)
                self.assertFalse((root/'run/proposals.json').exists())

    def test_unknown_consumption_no_resend(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);self.plan(root)
            def timeout(*args):raise TimeoutError()
            with self.assertRaises(Exception):judge.execute(root/'plan',root/'run',backend=Backend(PROFILE,sender=timeout))
            calls=[]
            with self.assertRaisesRegex(ValueError,'unknown'):judge.execute(root/'plan',root/'run',backend=self.transport(calls))
            self.assertFalse(calls)

if __name__=='__main__':unittest.main()
