"""Fixed-reference field counting with synthetic records and offline review."""
import copy
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from model_conversation.archive import read, write, seal, verify
from biotracebench_scoring.evaluation import score
from biotracebench_scoring import completion
from biotracebench_scoring.workflow import score_run
from test_biotracebench_alignment import CLINICAL, ROOT, dictionary
import test_biotracebench_rule_audit as audit_fixtures
from biotracebench_scoring.rule_audit import audit

CONTRACT = 'biotracebench-fixed-reference-1'
DICTIONARY = {'sample': {'identifier': 'id', 'fields': [
    {'key':'id'}, {'key':'label'}, {'key':'value'}, {'key':'optional'}]}}
POLICY = {'version':'biotracebench-score-2', 'item_policy':'biotracebench-scoring-items-1',
          'frozen':True, 'identity_contract':'biotracebench-identity-2',
          'identity_groups':{'sample':[['label']]}, 'reference_contract':CONTRACT,
          'compound_fields':[], 'field_rules':{}, 'field_roles':{}}
GOLD = {'sample':[{'id':'S1','label':'Object A','value':60,'optional':None}]}


class FixedReferenceTests(unittest.TestCase):
    def evaluate(self, prediction=None, gold=None, policy=None, decisions=None):
        with patch('socket.socket',side_effect=AssertionError('No network')):
            return score(prediction if prediction is not None else GOLD,
                         gold if gold is not None else GOLD, DICTIONARY, policy or POLICY, decisions)

    def assert_counts(self, result, tp, predicted, reference):
        self.assertEqual((result['field']['tp'], result['field']['predicted'], result['field']['gold']),
                         (tp,predicted,reference))

    def test_both_blank_not_counted_or_queued_and_record_can_match(self):
        before=copy.deepcopy(GOLD)
        result=self.evaluate()
        self.assert_counts(result,2,2,2)
        self.assertEqual(result['record']['tp'],1)
        self.assertFalse(result['adjudication_queue'])
        self.assertNotIn('sample:0:optional',result['gold_field_correctness'])
        self.assertEqual(result['reference_contract'],CONTRACT)
        self.assertEqual(result['boundary_revision'],'scoring-boundaries-3')
        self.assertEqual(GOLD,before)

    def test_extra_at_reference_null_is_one_fp_without_fn(self):
        prediction=copy.deepcopy(GOLD);prediction['sample'][0]['optional']=30
        result=self.evaluate(prediction)
        self.assert_counts(result,2,3,2)
        self.assertEqual(result['field']['precision'],2/3)
        self.assertEqual(result['field']['recall'],1)
        self.assertEqual(result['field']['f1'],4/5)
        self.assertEqual(result['record']['tp'],0)
        self.assertFalse(result['adjudication_queue'])

    def test_omitted_reference_value_is_fn_not_a_state_question(self):
        for missing in (False,True):
            p=copy.deepcopy(GOLD)
            if missing:del p['sample'][0]['value']
            else:p['sample'][0]['value']=None
            result=self.evaluate(p)
            self.assert_counts(result,1,1,2)
            self.assertEqual(result['record']['tp'],0)
            self.assertFalse(result['adjudication_queue'])

    def test_one_incorrect_submission_preserves_paper_match_denominators(self):
        p=copy.deepcopy(GOLD);p['sample'][0]['value']=61
        result=self.evaluate(p)
        self.assert_counts(result,1,2,2)
        for metric in ('precision','recall','f1'):
            self.assertEqual(result['field'][metric],0.5)
        self.assertEqual(result['record']['tp'],0)

    def test_explicit_reference_state_omission_remains_fn(self):
        for value in ('NR','NE','not_reported'):
            g=copy.deepcopy(GOLD);g['sample'][0]['value']=value
            p=copy.deepcopy(g);p['sample'][0]['value']=None
            result=self.evaluate(p,g)
            self.assert_counts(result,1,1,2)
            self.assertFalse(result['adjudication_queue'])

    def test_semantic_adjudication_cannot_turn_a_reference_blank_into_credit(self):
        p=copy.deepcopy(GOLD);p['sample'][0]['optional']='extra content'
        result=self.evaluate(p)
        decisions={'contexts':{result['context_id']:{'equivalences':{
            'invented-blank-match':{'equal':True,'basis':'Attempted blank match'}}}}}
        with self.assertRaisesRegex(ValueError,'Stale or inapplicable text'):
            self.evaluate(p,decisions=decisions)

    def test_zero_false_nr_ne_and_explicit_states_remain_content(self):
        for value in (0,False,'NR','NE','not_reported','conflicting','not estimable'):
            with self.subTest(value=value):
                g=copy.deepcopy(GOLD);g['sample'][0]['value']=value
                result=self.evaluate(g,g)
                self.assert_counts(result,2,2,2)
                self.assertEqual(result['record']['tp'],1)
        g=copy.deepcopy(GOLD);g['sample'][0]['value']='NR'
        p=copy.deepcopy(g);p['sample'][0]['value']='NE'
        self.assertFalse(self.evaluate(p,g)['gold_field_correctness']['sample:0:value'])

    def test_whitespace_is_blank_without_hiding_structured_submissions(self):
        for value in ('','  \t\n'):
            g=copy.deepcopy(GOLD);g['sample'][0]['optional']=value
            p=copy.deepcopy(g);p['sample'][0]['optional']=None
            self.assert_counts(self.evaluate(p,g),2,2,2)
        for value in ({},[],0,False,'null','NR'):
            p=copy.deepcopy(GOLD);p['sample'][0]['optional']=value
            self.assert_counts(self.evaluate(p),2,3,2)

    def test_blank_extra_prediction_field_is_not_a_false_positive(self):
        p=copy.deepcopy(GOLD);del p['sample'][0]['optional']
        self.assert_counts(self.evaluate(p),2,2,2)

    def test_record_and_field_counts_share_pairing_with_nulls_and_duplicates(self):
        g=copy.deepcopy(GOLD)
        g['sample'].append({'id':'S2','label':'Object B','value':None,'optional':None})
        p=copy.deepcopy(g);p['sample'].reverse()
        for i,r in enumerate(p['sample']):r['id']='renamed-'+str(i)
        result=self.evaluate(p,g)
        self.assert_counts(result,3,3,3)
        self.assertEqual(result['record']['tp'],2)
        p['sample'].append({**p['sample'][0],'id':'extra-duplicate'})
        duplicated=self.evaluate(p,g)
        self.assert_counts(duplicated,3,4,3)
        self.assertEqual((duplicated['record']['tp'],duplicated['record']['predicted']), (2,3))

    def test_null_cannot_be_promoted_to_a_scored_state_by_adjudication(self):
        result=self.evaluate()
        item=result['scoring_items']['sample']['reference'][0]['items']['optional']
        decisions={'contexts':{result['context_id']:{'field_states':{
            item['field_id']:{'state':'not_reported','basis':'Attempt to turn a null into credit'}}}}}
        with self.assertRaisesRegex(ValueError,'fixed-reference|Fixed-reference'):
            self.evaluate(decisions=decisions)

    def test_contract_is_versioned_and_legacy_null_policy_remains_available(self):
        old=copy.deepcopy(POLICY);old.pop('reference_contract')
        result=self.evaluate(policy=old)
        self.assert_counts(result,2,3,3)
        self.assertTrue(any(q['kind']=='field_state' for q in result['adjudication_queue']))
        self.assertEqual(result['boundary_revision'],'scoring-boundaries-2')
        bad=copy.deepcopy(POLICY);bad['reference_contract']='unknown-version'
        with self.assertRaisesRegex(ValueError,'reference contract'):
            self.evaluate(policy=bad)

    def test_current_contract_cannot_reenable_compound_subitem_credit(self):
        bad=copy.deepcopy(POLICY);bad['compound_fields']=['sample.value']
        with self.assertRaisesRegex(ValueError,'whole.field'):
            self.evaluate(policy=bad)

    def test_missing_reference_key_remains_a_reference_diagnostic(self):
        g=copy.deepcopy(GOLD);del g['sample'][0]['optional']
        result=self.evaluate(GOLD,g)
        self.assert_counts(result,2,2,2)
        self.assertTrue(any(q['kind']=='field_state' and q['side']=='reference' for q in result['adjudication_queue']))

    def test_unit_changes_cannot_supply_an_empty_reference_unit(self):
        g=copy.deepcopy(CLINICAL);g['result'][0].update(result_value=1,result_unit=None)
        p=copy.deepcopy(g);p['result'][0].update(result_value=1000,result_unit='μg')
        policy=read(ROOT/'configs/tasks/biotracebench-scoring-v2.json')
        policy['frozen']=True;policy['identity_task_rules']={}
        result=score(p,g,dictionary(g),policy)
        self.assertFalse(result['gold_field_correctness']['result:0:result_value'])
        self.assertNotIn('result:0:result_unit',result['gold_field_correctness'])
        self.assertFalse(result['adjudication_queue'])
        self.assertEqual(p['result'][0]['result_value'],1000)

    def test_missing_model_unit_is_a_clear_omission(self):
        g=copy.deepcopy(CLINICAL);g['result'][0].update(result_value=1,result_unit='mg')
        p=copy.deepcopy(g);p['result'][0]['result_unit']=None
        policy=read(ROOT/'configs/tasks/biotracebench-scoring-v2.json')
        policy['frozen']=True;policy['identity_task_rules']={}
        result=score(p,g,dictionary(g),policy)
        self.assertFalse(result['gold_field_correctness']['result:0:result_unit'])
        self.assertTrue(result['gold_field_correctness']['result:0:result_value'])
        self.assertEqual(result['field']['gold']-result['field']['tp'],1)
        self.assertEqual(result['field']['predicted'],result['field']['tp'])
        self.assertFalse(result['adjudication_queue'])

    def test_extra_unit_does_not_change_equal_raw_values_or_infer_a_gold_unit(self):
        g=copy.deepcopy(CLINICAL);g['result'][0].update(result_value=1,result_unit=None)
        p=copy.deepcopy(g);p['result'][0]['result_unit']='μg'
        policy=read(ROOT/'configs/tasks/biotracebench-scoring-v2.json')
        policy['frozen']=True;policy['identity_task_rules']={}
        result=score(p,g,dictionary(g),policy)
        self.assertTrue(result['gold_field_correctness']['result:0:result_value'])
        self.assertEqual(result['field']['gold'],result['field']['tp'])
        self.assertEqual(result['field']['predicted']-result['field']['tp'],1)
        self.assertFalse(result['adjudication_queue'])

    def test_blank_optional_analysis_does_not_block_approved_conversion(self):
        g=copy.deepcopy(CLINICAL)
        g['result'][0].update(result_value=1,result_unit='mg',statistical_method=None)
        p=copy.deepcopy(g);p['result'][0].update(result_value=1000,result_unit='μg')
        policy=read(ROOT/'configs/tasks/biotracebench-scoring-v2.json')
        policy['frozen']=True;policy['identity_task_rules']={}
        result=score(p,g,dictionary(g),policy)
        self.assertEqual(result['field']['f1'],1)
        self.assertFalse(result['adjudication_queue'])

    def test_extra_whole_statistics_at_reference_blank_is_only_one_fp(self):
        g=copy.deepcopy(CLINICAL)
        g['result'][0].update(result_value=1,result_unit='mg',supplementary_statistics=None)
        p=copy.deepcopy(g)
        p['result'][0].update(result_value=1000,result_unit='μg',
                              supplementary_statistics='95% CI [500, 1500]; P<0.05; n=30')
        policy=read(ROOT/'configs/tasks/biotracebench-scoring-v2.json')
        policy['frozen']=True;policy['identity_task_rules']={}
        result=score(p,g,dictionary(g),policy)
        self.assertEqual(result['field']['gold'],result['field']['tp'])
        self.assertEqual(result['field']['predicted']-result['field']['tp'],1)
        self.assertFalse(result['adjudication_queue'])

    def test_compatible_units_still_match_when_reference_value_is_empty(self):
        g=copy.deepcopy(CLINICAL);g['result'][0].update(result_value=None,result_unit='mg')
        p=copy.deepcopy(g);p['result'][0].update(result_value=1000,result_unit='μg')
        policy=read(ROOT/'configs/tasks/biotracebench-scoring-v2.json')
        policy['frozen']=True;policy['identity_task_rules']={}
        result=score(p,g,dictionary(g),policy)
        self.assertNotIn('result:0:result_value',result['gold_field_correctness'])
        self.assertTrue(result['gold_field_correctness']['result:0:result_unit'])
        self.assertFalse(result['adjudication_queue'])
        self.assertEqual(result['field']['predicted']-result['field']['tp'],1)

    def test_unfrozen_policy_remains_diagnostic_only(self):
        policy=copy.deepcopy(POLICY);policy['frozen']=False
        with self.assertRaises(ValueError):self.evaluate(policy=policy)
        result=score(GOLD,GOLD,DICTIONARY,policy,allow_unfrozen=True)
        self.assertEqual(result['status'],'provisional')
        self.assert_counts(result,2,2,2)

    def test_read_only_audit_keeps_null_inventory_without_requesting_state_sidecars(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            dataset,policy,paper,_,_=audit_fixtures.RuleAuditTests().fixture(root)
            value=read(policy);value['reference_contract']=CONTRACT;write(policy,value)
            result=audit(dataset,policy,paper,root/'audit',1)
            self.assertEqual(result['summary']['null_fields'],1)
            questions=read(root/'audit/confirmation-queue.json')
            r01=next(q for q in questions if q['id']=='R01')
            self.assertFalse(r01['requires_user_decision_now'])
            self.assertEqual(r01['status'],'determined_by_fixed_reference_contract')
            self.assertFalse(result['summary']['scientific_audit_completed'])
            verify(root/'audit')

    def test_offline_human_round_can_complete_without_a_null_judge_batch(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);prepared=root/'prepared'
            write(prepared/'dictionary.json',DICTIONARY)
            write(prepared/'materials.json',{'domain':'basic','study_id':'synthetic'})
            material=seal(prepared);run=root/'run'
            stages=['i0','gsr','ssr']
            write(run/'manifest.json',{'protocol':'biotracebench-run-2','stages':stages,
                  'tasks':[{'case_id':'SYN','prepared':str(prepared),'material_identity':material}]})
            for stage in stages:
                write(run/'SYN'/stage/'final/database.json',GOLD)
                seal(run/'SYN'/stage/'final')
            write(root/'gold/basic/SYN/SYN.json',GOLD);write(root/'policy.json',POLICY)
            with patch('socket.socket',side_effect=AssertionError('No network')):
                score_run(Namespace(run=str(run),gold_root=str(root/'gold'),policy=str(root/'policy.json'),
                          out=str(root/'scores'),adjudications=None,with_analysis=False))
                completion.prepare(root/'scores',root/'check')
                reviews=read(root/'check/review-template.json')
                self.assertTrue(all(not r['semantic_reviews'] for r in reviews))
                for r in reviews:r.update(approve=True,reviewer='synthetic-human',reviewed_at='2026-10-28',basis='Checked fixed-reference counts.')
                write(root/'reviews.json',reviews)
                result=completion.finalize(root/'check',root/'reviews.json',root/'done')
            self.assertEqual(result['status'],'completed')
            scores=read(root/'done/study-scores.json')[0]['conditions']
            self.assertTrue(all(s['field']['gold']==2 and s['field']['f1']==1 for s in scores.values()))
            self.assertEqual(read(root/'done/completion-audit.json')['model_calls'],0)


if __name__=='__main__':unittest.main()
