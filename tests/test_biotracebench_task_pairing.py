"""Task-specific identity from invented labels; never read actual study data."""
import copy
import unittest
from unittest.mock import patch

from biotracebench.common import read
from biotracebench_scoring.evaluation import score
from biotracebench_scoring.identity_alignment import scoped_policy, rules
from biotracebench_scoring.rule_audit import reference_observations
from test_biotracebench_alignment import BASIC, ROOT, dictionary


class TaskPairingTests(unittest.TestCase):
    def setUp(self):
        self.policy = read(ROOT/'configs/tasks/biotracebench-scoring-v2.json')
        self.policy['identity_task_rules'] = read(ROOT/'tests/fixtures/synthetic_identity_rules.json')
        self.assertFalse(self.policy['frozen'])
        self.policy['frozen'] = True  # In-memory synthetic policy only.
        self.network = patch('socket.socket', side_effect=AssertionError('No network'))
        self.network.start()
        self.addCleanup(self.network.stop)

    def reference(self, case):
        data = copy.deepcopy(BASIC)
        labels = (['1st MS experiment, naïve 8H2', '1st MS experiment, primed 8H2',
                   '1st MS experiment, naïve 9J4', '2nd MS experiment, naïve 8H2']
                  if case == 'B901' else
                  ['20990101_Exercise_1st_F91.raw', '20990101_Exercise_1st_F92.raw',
                   '20990101_Exercise_2nd_F91.raw', '20990101_Unloading_1st_F91.raw'])
        data['assay_run'] = [
            {**data['assay_run'][0], 'assay_id':'A'+str(i),
             'experiment_run_accession':'Synthetic:shared (project)',
             'method':label+'. Synthetic procedure.'} for i,label in enumerate(labels)]
        return data

    def evaluate(self, prediction, reference, case, policy=None):
        return score(prediction, reference, dictionary(reference), policy or self.policy,
                     context={'case_id':case})

    def test_every_native_identity_is_unique_and_independent_of_order_and_ids(self):
        for case in ('B901','B903'):
            with self.subTest(case=case):
                gold=self.reference(case);p=copy.deepcopy(gold)
                p['assay_run'].reverse()
                p['sample'][0]['sample_id']='other-sample'
                p['condition'][0].update(condition_id='other-condition',sample_id='other-sample')
                for i,row in enumerate(p['assay_run']):
                    row.update(assay_id='new-'+str(i),sample_ids=['other-sample'])
                original=copy.deepcopy((p,gold,self.policy))
                result=self.evaluate(p,gold,case)
                self.assertEqual(result['pairs']['assay_run'],
                                 [{'prediction':i,'gold':3-i} for i in range(4)])
                self.assertEqual(result['field']['f1'],1)
                self.assertEqual(result['record']['f1'],1)
                self.assertEqual((p,gold,self.policy),original)

    def test_b901_complete_components_allow_explicit_format_variations(self):
        gold=self.reference('B901');p=copy.deepcopy(gold)
        p['assay_run'][0]['method']='Clone 8h2; naive; MS experiment #01. Other synthetic wording.'
        result=self.evaluate(p,gold,'B901')
        self.assertIn({'prediction':0,'gold':0},result['pairs']['assay_run'])
        self.assertFalse(result['gold_field_correctness']['assay_run:0:method'])
        self.assertTrue(any(q['kind']=='text_equivalence' and q['field']=='method'
                            for q in result['adjudication_queue']))
        evidence=result['alignment_audit']['assay_run'][0]['evidence']['native_labels']['prediction']['method']
        self.assertEqual(evidence[0],'native_components')
        self.assertEqual(dict(evidence[1]),{'clone':'8H2','culture_state':'naive','experiment_round':'1'})

    def test_b901_missing_or_conflicting_components_are_not_guessed(self):
        for method in ('1st MS experiment; naive', 'naive clone 8H2',
                       '1st MS experiment; clone 8H2',
                       '1st MS experiment, naive 8H2 and primed 8H2',
                       '1st MS experiment, naive 8H2 and 9J4',
                       '1st MS experiment and 2nd MS experiment, naive 8H2'):
            with self.subTest(method=method):
                gold=self.reference('B901');p=copy.deepcopy(gold)
                p['assay_run'][0]['method']=method
                result=self.evaluate(p,gold,'B901')
                self.assertFalse(any(pair['prediction']==0 for pair in result['pairs']['assay_run']))
                self.assertTrue(any(q['kind']=='record_identity' and q['table']=='assay_run'
                                    for q in result['adjudication_queue']))

    def test_b903_complete_filename_is_required(self):
        for method in ('F91', 'File ID F91', 'Exercise 1st F91',
                       '20990101_Exercise_1st_F91.raw.backup',
                       '20990101_Exercise_1st_F91.raw; 20990101_Exercise_1st_F92.raw'):
            with self.subTest(method=method):
                gold=self.reference('B903');p=copy.deepcopy(gold)
                p['assay_run'][0]['method']=method
                result=self.evaluate(p,gold,'B903')
                self.assertFalse(any(pair['prediction']==0 for pair in result['pairs']['assay_run']))
                self.assertTrue(any(q['kind']=='record_identity' and q['table']=='assay_run'
                                    for q in result['adjudication_queue']))

    def test_pairing_does_not_hide_wrong_link_platform_or_whole_method(self):
        for case in ('B901','B903'):
            with self.subTest(case=case):
                gold=self.reference(case);p=copy.deepcopy(gold)
                p['assay_run'][0].update(sample_ids=['UNKNOWN'],platform='Wrong synthetic instrument')
                p['assay_run'][0]['method']+=' Contradictory synthetic procedure.'
                result=self.evaluate(p,gold,case)
                self.assertEqual(len(result['pairs']['assay_run']),4)
                for field in ('sample_ids','platform','method'):
                    self.assertFalse(result['gold_field_correctness']['assay_run:0:'+field])
                self.assertEqual(result['field']['gold']-result['field']['tp'],3)
                self.assertEqual(result['record']['gold']-result['record']['tp'],1)
                self.assertFalse(any(k.startswith('method.') for k in
                    result['scoring_items']['assay_run']['prediction'][0]['items']))

    def test_exact_duplicates_remain_surplus_without_displacing_a_record(self):
        for case in ('B901','B903'):
            gold=self.reference(case);p=copy.deepcopy(gold)
            p['assay_run'].append({**p['assay_run'][0],'assay_id':'duplicate'})
            result=self.evaluate(p,gold,case)
            self.assertEqual(len(result['pairs']['assay_run']),4)
            self.assertEqual(result['record']['predicted']-result['record']['tp'],1)
            self.assertTrue(any(a['status']=='duplicate_prediction' for a in result['alignment_audit']['assay_run']))

    def test_nonidentical_competitors_are_not_selected_by_more_correct_content(self):
        for case in ('B901','B903'):
            gold=self.reference(case);p=copy.deepcopy(gold)
            p['assay_run'].append({**p['assay_run'][0],'assay_id':'competitor','platform':'Wrong'})
            result=self.evaluate(p,gold,case)
            self.assertFalse(any(pair['gold']==0 for pair in result['pairs']['assay_run']))
            self.assertTrue(any(q['kind']=='record_identity' for q in result['adjudication_queue']))

    def test_rules_are_case_scoped_and_cannot_bypass_object_accession_conflicts(self):
        for case in ('B901','B903'):
            gold=self.reference(case)
            self.assertEqual(self.evaluate(gold,gold,'B001')['pairs']['assay_run'],[])
            p=copy.deepcopy(gold)
            gold['assay_run'][0]['experiment_run_accession']='Synthetic:run-A (run)'
            p['assay_run'][0]['experiment_run_accession']='Synthetic:run-B (run)'
            result=self.evaluate(p,gold,case)
            self.assertNotIn({'prediction':0,'gold':0},result['pairs']['assay_run'])

    def test_unknown_or_invalid_component_rules_fail_before_comparison(self):
        for change in ('unknown_contract','missing_patterns','missing_capture','bad_normalization','bad_alias'):
            with self.subTest(change=change):
                policy=copy.deepcopy(self.policy)
                rule=policy['identity_task_rules']['B901']['identity_native_labels']['assay_run']['method']
                if change=='unknown_contract':rule['contract']='unknown'
                elif change=='missing_patterns':rule['components']['clone']['patterns']=[]
                elif change=='missing_capture':rule['components']['clone']['patterns']=[r'clone\d+']
                elif change=='bad_normalization':rule['components']['clone']['normalization']='guess'
                else:rule['components']['clone']['aliases']={'wrong lower case':'8H2'}
                g=self.reference('B901')
                with self.assertRaises(ValueError):self.evaluate(g,g,'B901',policy)

    def test_native_components_cannot_be_bound_to_outcomes_or_reference_links(self):
        for field in ('sample_ids','assay_id'):
            policy=scoped_policy(self.policy,{'case_id':'B901'})
            native=policy['identity_native_labels']['assay_run'].pop('method')
            policy['identity_native_labels']['assay_run'][field]=native
            spec=dictionary(self.reference('B901'))['assay_run']
            with self.assertRaises(ValueError):rules('assay_run',spec,policy)

    def test_repeated_consistent_components_do_not_hide_conflicting_labels(self):
        gold=self.reference('B901');p=copy.deepcopy(gold)
        p['assay_run'][0]['method']='1st MS experiment, naive 8H2; MS experiment #1, clone 8h2.'
        self.assertIn({'prediction':0,'gold':0},self.evaluate(p,gold,'B901')['pairs']['assay_run'])
        p['assay_run'][0]['method']+=' MS experiment #2.'
        self.assertFalse(any(pair['prediction']==0 for pair in self.evaluate(p,gold,'B901')['pairs']['assay_run']))

    def test_rule_inventory_reports_unique_labels_without_scientific_approval(self):
        gold=self.reference('B901')
        schema={'type':'object','properties':{t:{'type':'array','items':{'type':'object'}} for t in gold}}
        observations=reference_observations(gold,dictionary(gold),schema,
                                            scoped_policy(self.policy,{'case_id':'B901'}))
        identities=observations['identity_candidates']['assay_run']
        self.assertFalse(identities['scientific_identity_approved'])
        self.assertFalse(identities['native_labels']['method']['incomplete_rows'])
        self.assertFalse(identities['native_labels']['method']['colliding_rows'])
        self.assertEqual(len(identities['native_labels']['method']['identities']),4)


if __name__=='__main__':unittest.main()
