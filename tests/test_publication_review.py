"""New-output protocol tests use synthetic sources and explicit identity evidence."""
from copy import deepcopy
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
import io
import json
import tempfile
import unittest
from biotracebench_analysis.publication.io import write, read, digest
from biotracebench_analysis.publication.score_output import prepare, finalize, CONTRACT
from biotracebench_analysis.publication.review_contract import ANNOTATIONS
from biotracebench_analysis.publication.demo import supplied_judgment

def synthetic_evidence(packet, reply):
    """Certify the known exact synthetic population labels, never real study answers."""
    reply = deepcopy(reply)
    inv = packet['inventory']
    evidence = []
    for record in reply['records']:
        proof = []
        for side, key in [('prediction','prediction_row'),('reference','reference_row')]:
            row = record[key]
            if row is None:
                continue
            if record['verdict'] != 'matched':
                proof.append({'source':side,'locator':'row:'+row})
            else:
                cell = next(c for c in inv['cells'] if c['row']==row and c['field']=='population_name')
                proof.append({'source':side,'locator':cell['id']})
        evidence.append({k:record[k] for k in ['prediction_row','reference_row']} |
                        {'basis':'The synthetic fixture declares the same population label.', 'evidence':proof})
    reply['identity_evidence'] = evidence
    return reply

class SourceBoundReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.art = self.root/'materials'
        self.case = 'C000'
        self.published = self.art/'04_Reproducibility/02_Published_Evaluation'
        self.materials = self.art/'03_Benchmark_Data/01_Task_Materials'
        config = Path(__file__).parents[1]/'configs/scoring/clinical.json'
        self.reference = {'population':[{**{f['key']:None for f in read(config)['population']['fields']},
                                        'population_id':'R1','population_name':'Synthetic arm','population_size':3}]}
        self.ref = self.published/'projection/references/C000.json'
        write(self.ref,self.reference)
        write(self.published/'source-dispositions.json',[])
        write(self.materials/'tasks/clinical/C000/task.json',{'scope':'One synthetic arm; source evidence is supplied.'})
        self.source = self.materials/'materials/clinical/C000/source.txt'
        self.source.parent.mkdir(parents=True)
        self.source.write_text('Synthetic arm has three members. No timeframe is reported.\n')
        write(self.materials/'metadata/manifests/clinical/C000.json',{'files':[{'path':'source.txt','sha256':digest(self.source)}]})
        self.submission = self.root/'database.json'
        write(self.submission,self.reference)
        self.plan = self.root/'plan'
        self.prepare()

    def tearDown(self):
        self.tmp.cleanup()

    def prepare(self, name=None):
        if name:self.plan=self.root/name
        with redirect_stdout(io.StringIO()):
            prepare(SimpleNamespace(artifact_root=self.art,case=self.case,database=self.submission,out=self.plan))
        self.packet=read(self.plan/'packet.json')
        self.reply=synthetic_evidence(self.packet,supplied_judgment(self.packet['inventory']))

    def finish(self, reply=None, legacy=False):
        judgment=self.root/'judgment.json';write(judgment,self.reply if reply is None else reply)
        with redirect_stdout(io.StringIO()):
            finalize(SimpleNamespace(artifact_root=self.art,plan=self.plan,judgment=judgment,
                                     actor='Synthetic reviewer',out=self.root/'result',legacy_plan=legacy))
        return read(self.root/'result/score.json')

    def annotate(self, state, field='population_time_frame', basis='The supplied source states the reporting status.'):
        write(self.art/ANNOTATIONS,{'cases':{self.case:{'reference_sha256':digest(self.ref),
              'fields':[{'table':'population','row_index':0,'field':field,'state':state,'basis':basis,
                         'evidence':[{'source':'source.txt','locator':'line 1'}]}]}}})

    def test_source_bound_review_preserves_exact_scores(self):
        result=self.finish();self.assertEqual(result['metrics']['field']['f1'],1)
        self.assertEqual(result['metrics']['record']['f1'],1)
        self.assertEqual(result['validation']['identity_evidence'],'passed')

    def test_null_remains_unspecified_without_source_annotation(self):
        cell=next(x for x in self.packet['information_states'] if not x['nonempty'])
        self.assertEqual(cell['state'],'unspecified_null')

    def test_wrapper_annotations_survive_without_changing_inventory_or_scores(self):
        write(self.submission,{'database':self.reference,'annotations':[
            {'table':'population','row_id':'R1','field':'population_time_frame',
             'state':'not_reported','note':'No timeframe in the synthetic source.'}]})
        before=deepcopy(self.packet['inventory']);self.prepare('wrapped')
        self.assertEqual(json.loads(self.packet['submitted_json'])['annotations'][0]['state'],'not_reported')
        self.assertEqual(self.packet['inventory'],before)
        self.assertEqual(self.finish()['metrics']['field']['gold'],2)

    def test_full_json_preserves_decimal_lexemes(self):
        self.submission.write_text(json.dumps({'database':self.reference,'annotations':{'precision':2.0}}).replace('2.0','2.00'))
        self.prepare('precision')
        self.assertIn('2.00',self.packet['submitted_json'])

    def test_source_not_reported_annotation_is_preserved_without_credit(self):
        self.annotate('not_reported');self.prepare('annotated')
        state=next(x for x in self.packet['information_states'] if x['state']=='not_reported')
        self.assertFalse(state['nonempty'])
        result=self.finish();self.assertEqual(result['metrics']['field']['gold'],2)

    def test_reported_annotation_cannot_fill_empty_reference(self):
        self.annotate('reported')
        with self.assertRaisesRegex(ValueError,'Empty reference'):
            self.prepare('invalid-state')

    def test_source_annotation_with_unknown_source_fails(self):
        self.annotate('not_reported');p=self.art/ANNOTATIONS;d=read(p)
        d['cases'][self.case]['fields'][0]['evidence'][0]['source']='not-supplied.txt';write(p,d)
        with self.assertRaisesRegex(ValueError,'not declared'):self.prepare('invalid-source')

    def test_old_state_annotation_reference_cannot_transfer(self):
        self.annotate('not_reported');p=self.art/ANNOTATIONS;d=read(p);d['cases'][self.case]['reference_sha256']='0'*64;write(p,d)
        with self.assertRaisesRegex(ValueError,'different reference'):self.prepare('wrong-reference')

    def test_evidence_is_mandatory_on_new_entrypoint(self):
        self.reply.pop('identity_evidence')
        with self.assertRaisesRegex(ValueError,'envelope'):self.finish()

    def test_primary_ids_cannot_establish_identity(self):
        for e in self.reply['identity_evidence'][0]['evidence']:
            e['locator']=next(c['id'] for c in self.packet['inventory']['cells'] if c['side']==e['source'] and c['field']=='population_id')
        with self.assertRaisesRegex(ValueError,'Local IDs'):self.finish()

    def test_equal_result_numbers_cannot_establish_identity(self):
        for e in self.reply['identity_evidence'][0]['evidence']:
            e['locator']=next(c['id'] for c in self.packet['inventory']['cells'] if c['side']==e['source'] and c['field']=='population_size')
        with self.assertRaisesRegex(ValueError,'outcome values'):self.finish()

    def test_evidence_cannot_point_to_another_object(self):
        e=self.reply['identity_evidence'][0]['evidence'][0]
        e['locator']=next(c['id'] for c in self.packet['inventory']['cells'] if c['side']=='reference' and c['field']=='population_name')
        with self.assertRaisesRegex(ValueError,'outside its declared object'):self.finish()

    def test_undeclared_source_is_rejected(self):
        self.reply['identity_evidence'][0]['evidence'].append({'source':'invented.txt','locator':'Table 1'})
        with self.assertRaisesRegex(ValueError,'not declared'):self.finish()

    def test_duplicate_identity_receipt_fails(self):
        self.reply['identity_evidence'].append(deepcopy(self.reply['identity_evidence'][0]))
        with self.assertRaisesRegex(ValueError,'exactly once'):self.finish()

    def test_source_change_after_prepare_fails(self):
        self.source.write_text('Different study source.\n')
        with self.assertRaisesRegex(ValueError,'source identity differs'):self.finish()

    def test_state_change_after_prepare_fails(self):
        self.annotate('not_reported')
        with self.assertRaisesRegex(ValueError,'annotation identity changed'):self.finish()

    def test_active_uncertainty_blocks_finalization(self):
        next(c for c in self.reply['cells'] if c['verdict']=='correct')['verdict']='uncertain'
        with self.assertRaisesRegex(ValueError,'applicable scientific uncertainty'):self.finish()

    def test_excluded_uncertainty_survives_without_blocking_scores(self):
        write(self.published/'source-dispositions.json',[{'case':self.case,'table':'population','row_index':0,
               'field_exclusions':['population_size'],'main_record_scoring':'excluded','reason':'Synthetic count unsupported.'}])
        self.prepare('excluded')
        mark=next(c for c in self.reply['cells'] if self.packet['inventory']['cells'][int(c['reference_cell'][1:])]['field']=='population_size')
        mark['verdict']='uncertain'
        result=self.finish();self.assertEqual(result['metrics']['field']['gold'],1)
        self.assertEqual(result['metrics']['field']['f1'],1)
        self.assertEqual(len(result['excluded_review_items']),1)
        self.assertIsNone(result['metrics']['record']['f1'])
        self.assertEqual(read(self.root/'result/judgment.json')['cells'],self.reply['cells'])

    def test_supported_field_in_excluded_record_still_blocks(self):
        write(self.published/'source-dispositions.json',[{'case':self.case,'table':'population','row_index':0,
               'field_exclusions':['population_size'],'main_record_scoring':'excluded','reason':'Only count unsupported.'}])
        self.prepare('supported')
        next(c for c in self.reply['cells'] if c['verdict']=='correct' and c['reference_cell'] in {
            x['id'] for x in self.packet['inventory']['cells'] if x['field']=='population_name'})['verdict']='uncertain'
        with self.assertRaisesRegex(ValueError,'applicable scientific uncertainty'):self.finish()

    def test_excluded_identity_evidence_dependency_still_blocks(self):
        write(self.published/'source-dispositions.json',[{'case':self.case,'table':'population','row_index':0,
               'field_exclusions':['population_name'],'main_record_scoring':'excluded','reason':'Identity unresolved.'}])
        self.prepare('dependency')
        # The supported count depends on the name used to establish this population's identity.
        ids={x['id'] for x in self.packet['inventory']['cells'] if x['field']=='population_name'}
        for c in self.reply['cells']:
            if c['reference_cell'] in ids:c['verdict']='uncertain'
        with self.assertRaisesRegex(ValueError,'applicable scientific uncertainty'):self.finish()

    def test_active_reference_defect_requires_resolution(self):
        c=next(x for x in self.packet['inventory']['cells'] if x['side']=='reference' and x['field']=='population_name')
        self.reply['reference_issues']=[{'reference_cell':c['id'],'reason':'Synthetic unresolved source conflict.'}]
        with self.assertRaisesRegex(ValueError,'applicable scientific uncertainty'):self.finish()

    def test_explicit_source_state_blocks_only_when_applicable(self):
        self.annotate('unresolved', field='population_size');self.prepare('source-pending')
        with self.assertRaisesRegex(ValueError,'applicable scientific uncertainty'):self.finish()
        write(self.published/'source-dispositions.json',[{'case':self.case,'table':'population','row_index':0,
               'field_exclusions':['population_size'],'main_record_scoring':'excluded','reason':'Count unsupported.'}])
        self.prepare('source-excluded');result=self.finish()
        self.assertEqual(result['metrics']['field']['f1'],1)
        self.assertEqual(result['excluded_review_items'][0]['kind'],'source_state')

    def test_eligibility_state_cannot_cite_an_applicable_field(self):
        self.annotate('unresolved', field='population_size');p=self.art/ANNOTATIONS;d=read(p)
        d['cases'][self.case]['fields'][0]['evidence']=[{'source':'eligibility','locator':'C000/population/0/population_size'}];write(p,d)
        with self.assertRaisesRegex(ValueError,'does not match its exclusion'):self.prepare('false-exclusion')

    def test_historical_packet_requires_explicit_replay(self):
        from biotracebench_analysis.publication.score_output import LEGACY_CONTRACT
        packet=read(self.plan/'packet.json');packet['contract']=LEGACY_CONTRACT;write(self.plan/'packet.json',packet)
        binding=read(self.plan/'binding.json');binding['packet_sha256']=digest(self.plan/'packet.json');write(self.plan/'binding.json',binding)
        reply=deepcopy(self.reply);reply.pop('identity_evidence')
        with self.assertRaisesRegex(ValueError,'explicit --legacy-plan'):self.finish(reply)
        result=self.finish(reply,legacy=True)
        self.assertEqual(result['metrics']['field']['f1'],1)
        self.assertEqual(result['validation']['identity_evidence'],'historical replay')

if __name__=='__main__':
    unittest.main()
