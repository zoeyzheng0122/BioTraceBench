"""Shared precision reaches Qwen intact; the program never revises its judgment."""
import copy
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import test_biotracebench_task_grading as f
from biotracebench_scoring import task_grading as grading
from biotracebench_scoring.grading_precision import CONTRACT, POLICY, NUMERIC_POLICY
from biotracebench_scoring.task_grading_contract import PROMPT
from model_api import Backend
from model_conversation.archive import digest, read, write, sha, verify


class PrecisionTests(unittest.TestCase):
    fixture = f.WorkflowTests.fixture

    def test_same_precision_policy_for_every_task_and_condition(self):
        policy = read(f.ROOT/'configs/tasks/biotracebench-scoring-v2.json')
        original = copy.deepcopy(policy)
        for case in ('B001','B010','B041','C001','C050'):
            selected = grading._grading_policy(policy,case,f.DICT)
            self.assertEqual(selected['precision_policy'],POLICY)
            self.assertEqual(selected['precision_contract'],CONTRACT)
            self.assertEqual(selected['numeric_policy'],NUMERIC_POLICY)
            self.assertNotIn('precision_rules',selected)
        self.assertEqual(original,policy)
        self.assertFalse(policy['frozen'])
        self.assertIn('ROUND_HALF_UP',PROMPT)
        self.assertIn('whether prediction or gold is more precise',PROMPT)
        self.assertIn('Counts (including count-valued results)',PROMPT)
        self.assertIn('denominators and identifiers remain exact',PROMPT)
        self.assertIn('existing cell reason',PROMPT)
        self.assertNotIn('source-bound predeclared continuous rounding only',PROMPT)

    def test_old_malformed_or_competing_rules_are_blocked_before_any_request(self):
        changed = copy.deepcopy(POLICY)
        changed['rounding']='ROUND_HALF_EVEN'
        types = copy.deepcopy(POLICY)
        types['citation_quality_gate']=0
        for extra in ({'precision_contract':'biotracebench-source-precision-1'},
                      {'precision_rules':[]}, {'precision_rules':'malformed'},
                      {'precision_rules':[{'study_id':'another-study'}]},
                      {'precision_policy':changed}, {'precision_policy':types},
                      {'precision_policy':None}, {'numeric_policy':'Exact only; round by source only'},
                      {'field_rules':{'sample.value':{'decimal_places':2}}}):
            with self.subTest(extra=extra),tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                self.fixture(root)
                policy={**f.POLICY,**extra}
                write(root/'policy.json',policy)
                before=(root/'policy.json').read_bytes()
                result=grading.prepare(root/'submission',root/'gold',root/'policy.json',f.PROFILE,
                    root/'budget.json',root/'blocked-plan',provisional=True)
                self.assertEqual(result['model_calls'],0)
                self.assertEqual(result['prepared_outputs'],0)
                plan=read(root/'blocked-plan/plan.json')
                self.assertEqual(plan['entries'][0]['status'],'blocked_input_or_capacity')
                self.assertFalse(plan['packets'])
                self.assertEqual((root/'policy.json').read_bytes(),before)

    def test_rounding_marks_keep_original_values_reasons_and_shared_identity(self):
        for predicted,gold,verdict,reason in (
                ('12.346','12.35','correct','12.346 rounds to 12.35 at two decimal places, ROUND_HALF_UP; all whole-cell assertions agree.'),
                ('12.35','12.346','correct','12.346 in gold rounds to 12.35 at two decimal places, ROUND_HALF_UP; all whole-cell assertions agree.'),
                ('12.3','12.34','correct','12.34 in gold rounds to 12.3 at one decimal place, ROUND_HALF_UP; all whole-cell assertions agree.'),
                ('-1.225','-1.23','correct','-1.225 rounds to -1.23 at two decimal places; ties away from zero; whole cell agrees.'),
                ('12.344','12.35','incorrect','12.344 rounds to 12.34 at two decimal places, not 12.35; submitted whole cell is incorrect.')):
            with self.subTest(predicted=predicted,gold=gold),tempfile.TemporaryDirectory() as temp, \
                    patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
                root=Path(temp)
                prediction=copy.deepcopy(f.GOLD)
                prediction['sample'][0]['value']=Decimal(predicted)
                self.fixture(root,('i0','gsr','ssr'),prediction=prediction)
                reference=copy.deepcopy(f.GOLD)
                reference['sample'][0]['value']=Decimal(gold)
                write(root/'gold/basic/SYN/SYN.json',reference)
                grading.prepare(root/'submission',root/'gold',root/'policy.json',f.PROFILE,
                    root/'budget.json',root/'precision-plan',provisional=True)
                plan=read(root/'precision-plan/plan.json')
                identities={e['score_binding']['precision_policy_identity'] for e in plan['entries']}
                self.assertEqual(identities,{digest(POLICY)})
                inputs=[root/'gold/basic/SYN/SYN.json',
                    *[root/'submission/SYN'/s/'final/database.json' for s in ('i0','gsr','ssr')]]
                originals={str(p):p.read_bytes() for p in inputs}
                sent=[]

                def sender(endpoint,body,headers,timeout):
                    wire=json.loads(body)
                    payload=json.loads(wire['messages'][1]['content'][0]['text'])['payload']
                    policy=json.loads(payload['scoring_policy_json'])
                    self.assertEqual(policy['precision_policy'],POLICY)
                    self.assertEqual(policy['numeric_policy'],NUMERIC_POLICY)
                    values={c['side']:c['value_json'] for c in payload['inventory']['cells'] if c['field']=='value'}
                    self.assertEqual(values,{'prediction':predicted,'reference':gold})
                    reply=f.reply_for(payload['inventory'],overrides={'value':verdict})
                    ids={c['id'] for c in payload['inventory']['cells'] if c['field']=='value'}
                    next(c for c in reply['cells'] if c['prediction_cell'] in ids)['reason']=reason
                    sent.append(wire)
                    return 200,{},json.dumps({'model':'qwen3.8-max-0902','id':'synthetic-precision',
                        'choices':[{'finish_reason':'stop','message':{'content':json.dumps(reply)}}],
                        'usage':{'prompt_tokens':100,'completion_tokens':20}}).encode()

                backend=Backend(f.PROFILE,sender=sender)
                state=grading.execute(root/'precision-plan',root/'run',backend=backend)
                self.assertEqual(state['graded_outputs'],3)
                for entry in state['outputs']:
                    folder=root/'run/tasks'/entry['id']
                    result=read(folder/'marking.json')['result']
                    self.assertEqual(result['precision_policy'],POLICY)
                    self.assertEqual(result['precision_policy_identity'],digest(POLICY))
                    self.assertEqual(result['field']['f1'],1 if verdict=='correct' else .5)
                    cell=next(c for c in result['cells'] if c['prediction']['field']=='value')
                    self.assertEqual(cell['prediction']['value_json'],predicted)
                    self.assertEqual(cell['reference']['value_json'],gold)
                    self.assertEqual(cell['reason'],reason)
                    self.assertIn(reason,(folder/'cells.csv').read_text(encoding='utf-8-sig'))
                    self.assertIn(reason,(folder/'review.html').read_text())
                self.assertEqual(originals,{str(p):p.read_bytes() for p in inputs})
                before={str(p):sha(p) for p in (root/'run').rglob('*') if p.is_file()}
                with patch.dict('os.environ',{},clear=True):
                    again=grading.execute(root/'precision-plan',root/'run',offline=True,backend=backend)
                self.assertEqual(again,state)
                self.assertEqual(before,{str(p):sha(p) for p in (root/'run').rglob('*') if p.is_file()})
                self.assertEqual(len(sent),3)
                verify(root/'run')

    def test_whole_cell_errors_and_qwen_decisions_are_not_rejudged_by_arithmetic(self):
        predicted=copy.deepcopy(f.GOLD)
        predicted['sample'][0]['value']='mean 12.346; CI 10.20–15.50'
        gold=copy.deepcopy(f.GOLD)
        gold['sample'][0]['value']='mean 12.35; CI 10.20–14.50'
        inv=f.inventory(predicted,gold,f.DICT,f.POLICY)
        reason='Mean can round to 12.35, but the CI upper bound is wrong; whole cell incorrect.'
        reply=f.reply_for(inv,overrides={'value':'incorrect'})
        ids={c['id'] for c in inv['cells'] if c['field']=='value'}
        mark=next(c for c in reply['cells'] if c['prediction_cell'] in ids)
        mark['reason']=reason
        result=f.mark_all(inv,reply)
        self.assertEqual(result['field']['f1'],.5)
        self.assertEqual(result['mark_counts']['incorrect'],1)
        self.assertEqual(result['mark_counts']['missing'],0)
        # A bad scientific Qwen judgment remains visible for external human review.
        # The program checks marking coverage/presence, not arithmetic correctness.
        mark.update(verdict='correct',reason='Synthetic Qwen judgment retained verbatim.')
        self.assertEqual(f.mark_all(inv,reply)['field']['f1'],1)


if __name__=='__main__':
    unittest.main()
