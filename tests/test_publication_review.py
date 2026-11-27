"""New-output protocol tests use synthetic sources and explicit identity evidence."""
from copy import deepcopy
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from biotracebench_analysis.replay.io import write, read, digest
from biotracebench_analysis.replay.score_output import prepare, finalize, CONTRACT
from biotracebench_analysis.replay.review_contract import ANNOTATIONS
from biotracebench_analysis.replay.demo import supplied_judgment

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
        write(self.art/'manifest.json', {'format':'biotracebench-submission-1', 'paths':{
            'published':'evaluation', 'materials':'benchmark', 'annotations':ANNOTATIONS,
        }})
        self.published = self.art/'evaluation'
        self.materials = self.art/'benchmark'
        config = Path(__file__).parents[1]/'src/biotracebench/review_configs/scoring/clinical.json'
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

    def prepare(self, name=None, judgment_factory=supplied_judgment):
        if name:self.plan=self.root/name
        with redirect_stdout(io.StringIO()):
            prepare(SimpleNamespace(artifact_root=self.art,case=self.case,database=self.submission,out=self.plan))
        self.packet=read(self.plan/'packet.json')
        self.reply=synthetic_evidence(self.packet,judgment_factory(self.packet['inventory']))
        if 'state_assessments' in self.packet['response_schema']['required']:
            self.reply['state_assessments'] = []

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

    def _restore_authority_label(self, label):
        from model_conversation.archive import digest as content_digest, read_exact
        packet = deepcopy(self.packet)
        packet['policy']['precision_policy']['decision_authority'] = label
        packet['study_bindings']['scoring rules'] = content_digest([
            packet['policy'], packet['field_dictionary']])
        write(self.plan/'packet.json', packet)
        binding = read(self.plan/'binding.json')
        binding['packet_sha256'] = content_digest(read_exact(self.plan/'packet.json'))
        write(self.plan/'binding.json', binding)

    def test_bound_packet_before_authority_rename_remains_readable(self):
        self._restore_authority_label('qwen_whole_cell_judgment')
        result = self.finish()
        self.assertEqual(result['metrics']['field']['f1'], 1)
        self.assertEqual(result['metrics']['record']['f1'], 1)

    def test_authority_compatibility_does_not_accept_other_policy_changes(self):
        self._restore_authority_label('unrecognized_judgment_authority')
        with self.assertRaisesRegex(ValueError, 'scoring rules identity changed'):
            self.finish()

    def test_final_score_envelope_and_paper_counts(self):
        result = self.finish()
        self.assertEqual(set(result), {
            'contract', 'case', 'actor', 'packet_sha256', 'judgment_sha256',
            'metrics', 'reference_issues', 'excluded_review_items', 'validation',
        })
        self.assertEqual(result['contract'], CONTRACT)
        self.assertEqual(result['case'], self.case)
        self.assertEqual(set(result['metrics']), {'field', 'record'})
        for level, count in [('field', 2), ('record', 1)]:
            self.assertEqual(result['metrics'][level], {
                'tp': count, 'predicted': count, 'gold': count,
                'precision': 1.0, 'recall': 1.0, 'f1': 1.0,
            })
            for key in ('tp', 'predicted', 'gold'):
                self.assertIs(type(result['metrics'][level][key]), int)

    def test_finalize_applies_zero_reference_convention_after_exclusions(self):
        write(self.published/'source-dispositions.json', [{
            'case': self.case, 'table': 'population', 'row_index': 0,
            'field_exclusions': ['*'], 'main_record_scoring': 'excluded',
        }])
        self.prepare('no-eligible-targets')
        result = self.finish()
        for metrics in result['metrics'].values():
            self.assertEqual(metrics, {
                'tp': 0, 'predicted': 0, 'gold': 0,
                'precision': None, 'recall': None, 'f1': None,
            })

    def test_finalize_empty_prediction_has_zero_applicable_scores(self):
        def missing_judgment(inv):
            return {
                'records': [{'prediction_row': None, 'reference_row': row['id'],
                             'verdict': 'missing', 'reason': 'Synthetic prediction is empty.'}
                            for row in inv['rows']],
                'cells': [{'prediction_cell': None, 'reference_cell': cell['id'],
                           'category': cell['role'],
                           'verdict': 'missing' if cell['role'] == 'scientific' and cell['nonempty']
                                      else 'not_scored',
                           'reason': 'Synthetic prediction is empty.'}
                          for cell in inv['cells']],
                'reference_issues': [],
            }

        write(self.submission, {})
        self.prepare('empty-prediction', judgment_factory=missing_judgment)
        result = self.finish()
        for level, gold in [('field', 2), ('record', 1)]:
            self.assertEqual(result['metrics'][level], {
                'tp': 0, 'predicted': 0, 'gold': gold,
                'precision': 0.0, 'recall': 0.0, 'f1': 0.0,
            })

    def test_finalize_rejects_missing_and_duplicate_cell_judgments(self):
        for defect in ('missing', 'duplicate'):
            with self.subTest(defect=defect):
                reply = deepcopy(self.reply)
                if defect == 'missing':
                    reply['cells'].pop()
                else:
                    reply['cells'].append(deepcopy(reply['cells'][0]))
                with self.assertRaises(ValueError):
                    self.finish(reply)
                self.assertFalse((self.root/'result').exists())

    def test_installed_and_source_commands_agree(self):
        repo = Path(__file__).resolve().parents[1]
        commands = {
            'installed': [str(Path(sys.executable).with_name('biotracebench-score'))],
            'review': [str(Path(sys.executable).with_name('biotracebench-review'))],
            'source': [sys.executable, '-B', str(repo/'scripts/score_output.py')],
            'module': [sys.executable, '-B', '-m', 'biotracebench_analysis.replay.score_output'],
            'compatibility': [sys.executable, '-B', '-m', 'biotracebench_analysis.publication.score_output'],
        }
        env = {key: value for key, value in os.environ.items() if key != 'PYTHONPATH'}
        judgment = self.root/'judgment.json'
        write(judgment, self.reply)
        scores = []
        for name, command in commands.items():
            with self.subTest(entrypoint=name):
                plan, output = self.root/(name+'-plan'), self.root/(name+'-score')
                subprocess.run(command + ['prepare', '--artifact-root', str(self.art),
                    '--case', self.case, '--database', str(self.submission), '--out', str(plan)],
                    check=True, capture_output=True, text=True, env=env, cwd=self.root)
                self.assertEqual(read(plan/'packet.json')['inventory'], self.packet['inventory'])
                subprocess.run(command + ['finalize', '--artifact-root', str(self.art),
                    '--plan', str(plan), '--judgment', str(judgment), '--actor', 'Synthetic reviewer',
                    '--out', str(output)], check=True, capture_output=True, text=True,
                    env=env, cwd=self.root)
                scores.append(read(output/'score.json')['metrics'])
        self.assertTrue(all(score == scores[0] for score in scores))
        self.assertEqual(scores[0]['field']['f1'], 1)
        self.assertEqual(scores[0]['record']['f1'], 1)

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
        self.reply['state_assessments'] = [{'reference_cell': state['reference_cell'],
                                            'state': 'unspecified', 'locator': None}]
        result=self.finish();self.assertEqual(result['metrics']['field']['gold'],2)
        self.assertEqual(result['metrics']['record']['f1'],1)

    def test_conflicting_double_empty_state_only_affects_record_credit(self):
        self.annotate('not_reported')
        write(self.submission, {'database': self.reference, 'annotations': {'R1': 'Timeframe not applicable'}})
        self.prepare('explicit-conflict')
        state=next(x for x in self.packet['information_states'] if x['state']=='not_reported')
        self.reply['state_assessments'] = [{'reference_cell': state['reference_cell'],
                                            'state': 'not_applicable', 'locator': '/annotations/R1'}]
        scores=self.finish()['metrics']
        self.assertEqual(scores['field']['f1'],1)
        self.assertEqual(scores['record']['f1'],0)

    def test_explicit_required_and_matching_no_credit_to_blank_field(self):
        self.annotate('not_applicable')
        path=self.art/ANNOTATIONS
        annotations=read(path)
        annotations['cases'][self.case]['fields'][0]['requires_explicit']=True
        write(path, annotations)
        write(self.submission, {'database': self.reference, 'annotations': {'R1': 'Timeframe not applicable'}})
        self.prepare('explicit-required')
        state=next(x for x in self.packet['information_states'] if x['state']=='not_applicable')
        with self.assertRaisesRegex(ValueError, 'applicable double-empty'):
            self.finish()
        self.reply['state_assessments'] = [{'reference_cell': state['reference_cell'],
                                            'state': 'unspecified', 'locator': None}]
        self.assertEqual(self.finish()['metrics']['record']['f1'],0)
        (self.root/'result').rename(self.root/'unspecified-result')
        self.reply['state_assessments'][0].update(state='not_applicable', locator='/annotations/R1')
        scores=self.finish()['metrics']
        self.assertEqual(scores['record']['f1'],1)
        self.assertEqual(scores['field']['gold'],2)


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

    def test_unresolved_optional_value_blocks_finalization(self):
        write(self.published/'source-dispositions.json', [{
            'case': self.case, 'table': 'population', 'row_index': 0,
            'field_exclusions': ['*'], 'main_record_scoring': 'excluded',
            'answer_policy': 'optional_neutral',
        }])
        self.prepare('optional')
        cells = {cell['id']: cell for cell in self.packet['inventory']['cells']}
        optional_value = next(mark for mark in self.reply['cells']
                              if cells[mark['reference_cell']]['field'] == 'population_size')
        optional_value['verdict'] = 'uncertain'
        with self.assertRaisesRegex(ValueError, 'applicable scientific uncertainty'):
            self.finish()
        self.assertFalse((self.root/'result').exists())

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

    def use_previous_packet(self, protocol):
        packet_path = self.plan/'packet.json'
        packet = read(packet_path)
        packet['contract'] = protocol
        del packet['study_bindings']
        packet.update(
            reference_sha256=digest(self.ref),
            eligibility_sha256=digest(self.published/'source-dispositions.json'),
            task_sha256=digest(self.materials/'tasks/clinical/C000/task.json'),
            source_manifest_sha256=digest(self.materials/'metadata/manifests/clinical/C000.json'),
            annotations_sha256=digest(self.art/ANNOTATIONS) if (self.art/ANNOTATIONS).exists() else None,
        )
        write(packet_path, packet)
        write(self.plan/'binding.json', {'contract':protocol, 'case':self.case,
                                         'packet_sha256':digest(packet_path)})

    def test_historical_packet_requires_explicit_replay(self):
        from biotracebench_analysis.replay.score_output import LEGACY_CONTRACT
        self.use_previous_packet(LEGACY_CONTRACT)
        reply = deepcopy(self.reply)
        reply.pop('identity_evidence')
        with self.assertRaisesRegex(ValueError, 'explicit --legacy-plan'):
            self.finish(reply)
        result = self.finish(reply, legacy=True)
        self.assertEqual(result['metrics']['field']['f1'], 1)
        self.assertEqual(result['validation']['identity_evidence'], 'historical replay')

    def test_previous_state_packet_preserves_record_scoring(self):
        from biotracebench_analysis.replay.score_output import STATE_CONTRACT
        self.annotate('not_reported')
        self.prepare('annotated')
        state = next(x for x in self.packet['information_states'] if x['state'] == 'not_reported')
        self.reply['state_assessments'] = [{'reference_cell':state['reference_cell'],
                                            'state':'unspecified','locator':None}]
        self.use_previous_packet(STATE_CONTRACT)
        self.assertEqual(self.finish()['metrics']['record']['f1'], 1)

    def test_json_formatting_and_changes_to_other_studies_are_independent(self):
        self.annotate('not_reported')
        self.prepare('annotated')
        state = next(x for x in self.packet['information_states'] if x['state'] == 'not_reported')
        self.reply['state_assessments'] = [{'reference_cell':state['reference_cell'],
                                            'state':'unspecified','locator':None}]
        for path in [self.ref, self.plan/'packet.json',
                     self.materials/'tasks/clinical/C000/task.json',
                     self.materials/'metadata/manifests/clinical/C000.json']:
            path.write_text(json.dumps(read(path), sort_keys=True))
        write(self.published/'source-dispositions.json', [{'case':'C999','change':'unrelated'}])
        annotations = read(self.art/ANNOTATIONS)
        annotations['cases']['C999'] = {'fields':[]}
        write(self.art/ANNOTATIONS, annotations)
        self.assertEqual(self.finish()['metrics']['field']['f1'], 1)

    def test_preparing_with_a_reformatted_annotated_reference(self):
        from model_conversation.archive import digest as content_digest
        self.annotate('not_reported')
        write(self.published/'reference-content-digests.json', {
            self.case: {'file_sha256':digest(self.ref), 'content_sha256':content_digest(self.reference)},
        })
        self.ref.write_text(json.dumps(self.reference, sort_keys=True))
        self.prepare('reformatted')
        self.assertIn('not_reported', {item['state'] for item in self.packet['information_states']})

    def test_changed_reference_identifies_study_and_next_step(self):
        self.reference['population'][0]['population_size'] += 1
        write(self.ref, self.reference)
        with self.assertRaisesRegex(ValueError, 'C000: reference identity changed.*Prepare'):
            self.finish()


if __name__ == '__main__':
    unittest.main()
