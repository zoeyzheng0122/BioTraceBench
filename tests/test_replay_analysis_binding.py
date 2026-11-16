import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from test_archive_replay import fixture
from biotracebench_scoring.archive_replay import replay
from biotracebench_analysis.replay_validation import validate_replay
from biotracebench_analysis.paper_reproduction import summarize
from test_archive_replay import POLICY

class ReplayAnalysisBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.m,_,_=fixture(self.root)
        self.m['models'].append('second-model')
        self.m['positions'].append({**self.m['positions'][0],'model':'second-model'})
        (self.root/'manifest.json').write_text(json.dumps(self.m))
        self.r=replay(self.root/'manifest.json')
    def tearDown(self):self.tmp.cleanup()
    def artifact(self,name):return json.loads((self.root/name).read_bytes())
    def test_missing_complete_model_is_rejected(self):
        self.r['scores']=self.r['scores'][:1]
        with self.assertRaisesRegex(ValueError,'grid'):validate_replay(self.r,self.m,self.artifact)
    def test_metrics_cannot_differ_from_counts(self):
        self.r['scores'][0]['field_f1']=.6
        with self.assertRaisesRegex(ValueError,'count'):validate_replay(self.r,self.m,self.artifact)
    def test_consistently_changed_counts_and_metrics_are_rejected(self):
        for q in ['field_tp','field_precision','field_recall','field_f1','record_tp','record_precision','record_recall','record_f1']:
            self.r['scores'][0][q]=0
        with self.assertRaisesRegex(ValueError,'count'):validate_replay(self.r,self.m,self.artifact)
    def test_domain_and_zero_classification_are_bound(self):
        for name,value in [('domain','clinical'),('zero_cause','downstream_not_started')]:
            r=copy.deepcopy(self.r);r['scores'][0][name]=value
            with self.assertRaises(ValueError):validate_replay(r,self.m,self.artifact)
    def test_candidate_requires_the_actual_bound_overlay(self):
        r=copy.deepcopy(self.r);r['candidate']=True;r['corrections_sha256']='a'*64
        with self.assertRaisesRegex(ValueError,'overlay'):validate_replay(r,self.m,self.artifact)
    def test_valid_baseline_passes_independent_count_check(self):
        validate_replay(self.r,self.m,self.artifact)
    def test_valid_candidate_recounts_from_bound_cell_changes(self):
        marks=self.artifact('j.json')['marking']['cells'];cell=next(m for m in marks if m['category']=='scientific')
        overlay={'baseline_manifest_sha256':self.r['baseline_manifest_sha256'],'changes':[dict(
            position=['m','B001','i0'],judgment_sha256=self.m['files']['j.json'],
            prediction_cell=cell['prediction_cell'],reference_cell=cell['reference_cell'],
            old_verdict='correct',new_verdict='incorrect',reason='Documented candidate.',
            evidence=[{'path':'reference.json','sha256':self.m['files']['reference.json']}])]}
        path=self.root/'overlay.json';path.write_text(json.dumps(overlay));h=hashlib.sha256(path.read_bytes()).hexdigest()
        r=replay(self.root/'manifest.json',path)
        validate_replay(r,self.m,self.artifact,overlay,h)
        self.assertEqual(r['corrections_sha256'],h)
        r['scores'][0]['record_tp']=1
        with self.assertRaisesRegex(ValueError,'count'):validate_replay(r,self.m,self.artifact,overlay,h)

    def two_domain_grid(self, all_zero=False):
        basic=self.m['cases'][0]
        self.m['cases'].append({**basic,'case':'C001','domain':'clinical'})
        self.m['conditions']=['i0','gsr','ssr']
        self.m['positions']=[dict(model=model,case=case,condition=stage,domain=domain,
            **({'zero_cause':'initial_refusal'} if all_zero or case=='B001' else {'zero_cause':None,'judgment':'j.json'}))
            for model in self.m['models'] for case,domain in [('B001','basic'),('C001','clinical')]
            for stage in self.m['conditions']]
        (self.root/'manifest.json').write_text(json.dumps(self.m))
        return replay(self.root/'manifest.json')

    def test_study_with_only_zero_positions_uses_bound_reference_counts(self):
        r=self.two_domain_grid()
        validate_replay(r,self.m,self.artifact)
        for row in r['scores']:
            self.assertEqual((row['field_gold'],row['record_gold']),(2,1))
            if row['case']=='B001':self.assertEqual(row['field_f1'],0)

    def test_all_zero_domains_still_produce_zero_paper_summaries(self):
        r=self.two_domain_grid(all_zero=True)
        validate_replay(r,self.m,self.artifact)
        result=summarize(r['scores'],dict(domain_weights={'basic':.5,'clinical':.5},seed=1,
            resamples=3,quantile_method='linear',interval=[.025,.975]))
        for group in result['summary']:
            self.assertEqual(group['field_f1'],dict(mean=0,low=0,high=0))

    def test_partial_zero_positions_still_use_the_same_reference_counts(self):
        self.m['positions'][0].pop('judgment');self.m['positions'][0]['zero_cause']='initial_refusal'
        (self.root/'manifest.json').write_text(json.dumps(self.m))
        r=replay(self.root/'manifest.json');validate_replay(r,self.m,self.artifact)
        self.assertEqual(r['scores'][0]['field_gold'],2)

    def test_all_zero_rows_cannot_supply_their_own_reference_denominator(self):
        r=self.two_domain_grid(all_zero=True)
        for row in r['scores']:row['field_gold']=999
        with self.assertRaisesRegex(ValueError,'count'):validate_replay(r,self.m,self.artifact)

    def test_reference_presence_roles_and_zero_false_content(self):
        from biotracebench_analysis.replay_validation import reference_counts
        reference={'sample':[{'id':'r','name':None,'time':'  ','zero':0,'false':False,'state':'NR',
                              'empty_list':[],'empty_object':{},'note':'source'}]}
        spec={'sample':{'identifier':'id','fields':[{'key':key} for key in reference['sample'][0]],'references':{}}}
        policy={**POLICY,'field_roles':{'sample.note':'provenance'}}
        self.assertEqual(reference_counts(reference,spec,policy),(5,1))

    def test_agreeing_judgment_denominators_must_still_match_bound_reference(self):
        bundle=self.artifact('j.json')
        time_cells={c['id'] for c in bundle['inventory']['cells'] if c['field']=='time'}
        for c in bundle['inventory']['cells']:
            if c['id'] in time_cells:c['nonempty']=False
        for mark in bundle['marking']['cells']:
            if mark['prediction_cell'] in time_cells:mark['verdict']='not_scored'
        r=copy.deepcopy(self.r)
        for row in r['scores']:
            row.update(field_tp=1,field_predicted=1,field_gold=1)
        with self.assertRaisesRegex(ValueError,'reference counts'):
            validate_replay(r,self.m,lambda name:bundle if name=='j.json' else self.artifact(name))

if __name__=='__main__':unittest.main()
