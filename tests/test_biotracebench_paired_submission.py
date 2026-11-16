"""Synthetic paired submission and stale-input guards; no live network or gold."""
import copy
import json
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import test_biotracebench_conditions as fixtures
from test_biotracebench import ANSWER, source_fixture
from biotracebench import dataset_identity, submission, prompts
from biotracebench.common import Stop, read, write, sha, seal
from biotracebench.materials import prepare, Reader
from biotracebench.runner import freeze, increase_limits
from biotracebench.export import run_report


class PairedSubmissionTests(unittest.TestCase):
    setUp = fixtures.ConditionTests.setUp
    tearDown = fixtures.ConditionTests.tearDown
    manifest = fixtures.ConditionTests.manifest
    execute = fixtures.ConditionTests.execute
    response = fixtures.ConditionTests.response
    send = fixtures.ConditionTests.send

    def test_surplus_closing_brace_preserves_database_and_format_diagnostics(self):
        self.manifest(strict=True)
        def send(*args):
            if 'estimate' in args[0]:
                return self.provider(*args)
            self.wire.append(json.loads(args[1]))
            return self.response(json.dumps({'database': ANSWER, 'annotations': []}) + '}')
        self.execute(send)
        final = self.out/'B001/i0/final'
        self.assertEqual(read(final/'database.json'), ANSWER)
        assessment = read(final/'output-assessment.json')
        self.assertTrue(assessment['database_schema_valid'])
        self.assertFalse(assessment['json_parseable'])
        self.assertFalse(assessment['delivery_contract_valid'])
        self.assertEqual(assessment['database_structure_errors'][0]['error'], 'invalid_final_json')

    def annotated(self, source='m0001', record='s1'):
        return {'table': 'sample', 'record_id': record, 'record_key': None, 'field': 'sample_name', 'kind': 'evidence',
                'source': source, 'locator': 'characters 0:40', 'text': 'Source names the preparation.'}

    def sender(self, annotations):
        def send(*args):
            if 'estimate' in args[0]:
                return self.provider(*args)
            self.wire.append(json.loads(args[1]))
            return self.response(json.dumps({'database': ANSWER, 'annotations': annotations}, ensure_ascii=False))
        return send

    def test_all_conditions_share_contract_and_bound_two_file_exports(self):
        frozen = self.manifest(strict=True)
        self.assertEqual(frozen['submission_protocol'], submission.PROTOCOL)
        self.assertEqual(frozen['execution_protocol'], prompts.EXECUTION_PROTOCOL)
        self.assertIsNone(self.execute(self.sender([self.annotated()]))['failure'])
        schemas = [x['response_format']['json_schema']['schema'] for x in self.wire]
        self.assertEqual(schemas[0], schemas[1]); self.assertEqual(schemas[1], schemas[2])
        for stage in ('i0', 'gsr', 'ssr'):
            final = self.out/'B001'/stage/'final'
            annotation = read(final/'annotations.json')
            self.assertEqual(annotation['database_sha256'], sha(final/'database.json'))
            self.assertEqual(annotation['raw_answer_sha256'], sha(final/'raw-answer.txt'))
            self.assertEqual(annotation['material_identity'], frozen['tasks'][0]['material_identity'])
            self.assertEqual(annotation['diagnostics'], [])
            self.assertEqual(annotation['annotations'], [self.annotated()])
            assessment = read(final/'output-assessment.json')
            self.assertTrue(assessment['delivery_contract_valid'])
            self.assertEqual(assessment['delivery_contract_errors'], [])
            self.assertEqual(read(final/'database.json'), ANSWER)
            self.assertFalse((final/'review.json').exists())
            self.assertFalse((final/'graph.json').exists())
        self.assertEqual(self.provider.completions, 3)
        self.assertEqual(self.wire[1]['messages'][:-1], self.wire[2]['messages'][:-1])
        self.assertNotIn('review={', prompts.SSR)
        self.assertIsNone(self.execute(offline=True)['failure'])
        self.assertEqual(self.provider.completions, 3)
        run_report(self.out, self.root/'export')
        for stage in ('i0', 'gsr', 'ssr'):
            final = self.out/'B001'/stage/'final'
            exported = self.root/'export/B001'/stage
            self.assertEqual(read(exported/'annotations.json'), read(final/'annotations.json'))
            self.assertEqual(sha(exported/'database.json'), read(exported/'annotations.json')['database_sha256'])

    def test_visible_schema_is_the_complete_transport_for_all_conditions(self):
        self.manifest(strict=True)
        self.execute(self.sender([]))
        reader = Reader(self.root/'prepared')
        business = read(reader.folder/'schema.json')
        for request in self.wire:
            parts = request['messages'][1]['content']
            self.assertEqual(parts[0]['text'], 'Task instructions:\n'+(reader.folder/'instruction.md').read_text())
            header, remainder = parts[1]['text'].split('\n', 1)
            self.assertEqual(header, 'Complete transport schema (the entire response):')
            visible, _ = json.JSONDecoder().raw_decode(remainder)
            self.assertEqual(visible, submission.schema(business))
            self.assertEqual(visible, request['response_format']['json_schema']['schema'])
            self.assertEqual(visible['properties']['database'], business)
            self.assertIn('apply to the database member only', remainder)
        self.assertIn('Every JSON object must have unique keys', prompts.INITIAL)
        self.assertIn('Each source is exactly one supplied material ID', prompts.INITIAL)

    def test_unknown_evidence_retained_without_invalidating_database_or_extra_calls(self):
        self.manifest()
        result = self.execute(self.sender([self.annotated(source='invented', record='absent')]))
        self.assertIsNone(result['failure'])
        self.assertEqual(set(result['tasks']['B001'].values()), {'completed'})
        self.assertEqual(self.provider.completions, 3)
        final = self.out/'B001/ssr/final'
        issues = read(final/'annotations.json')['diagnostics']
        self.assertEqual({x['error'] for x in issues}, {'unknown_material', 'unresolved_record_binding'})
        self.assertEqual(read(final/'database.json'), ANSWER)
        self.assertEqual(read(final/'output-assessment.json')['scientific_correctness'], 'not_evaluated')
        self.assertTrue(read(final/'output-assessment.json')['delivery_contract_valid'])

    def test_capacity_deferral_resumes_current_conditions_and_annotation_protocol(self):
        self.manifest(strict=True)
        self.frozen.unlink()
        draft = read(self.root / 'draft.json')
        draft['capacity_policy'] = 'defer_and_continue'
        draft['model']['max_request_bytes'] = 20
        write(self.root / 'draft.json', draft)
        freeze(self.root / 'draft.json', self.frozen)
        result = self.execute(sender=lambda *args: self.fail('No request fits the original byte limit'))
        self.assertIsNone(result['failure'])
        self.assertEqual(result['tasks']['B001']['i0'], 'paused_capacity')
        increase_limits(self.frozen, self.out, {'max_request_bytes': 2000000})
        result = self.execute(self.sender([self.annotated()]))
        self.assertIsNone(result['failure'])
        self.assertEqual(result['tasks']['B001'], dict.fromkeys(('i0', 'gsr', 'ssr'), 'completed'))
        self.assertEqual(self.provider.completions, 3)
        for stage in ('i0', 'gsr', 'ssr'):
            record = read(self.out / 'B001' / stage / 'final/annotations.json')
            self.assertEqual(record['protocol'], submission.PROTOCOL)
            self.assertEqual(record['diagnostics'], [])

    def test_direct_database_without_annotations_preserved_and_not_repaired(self):
        self.manifest()
        def send(*args):
            if 'estimate' in args[0]: return self.provider(*args)
            return self.response(json.dumps(ANSWER))
        self.assertIsNone(self.execute(send)['failure'])
        final = self.out/'B001/ssr/final'
        record = read(final/'annotations.json')
        self.assertFalse(record['received']); self.assertIsNone(record['annotations'])
        self.assertEqual(read(final/'database.json'), ANSWER)
        self.assertEqual(self.provider.completions, 3)
        assessment = read(final/'output-assessment.json')
        self.assertTrue(assessment['database_schema_valid'])
        self.assertFalse(assessment['delivery_contract_valid'])
        self.assertTrue(assessment['delivery_contract_errors'])
        self.assertEqual((final/'raw-answer.txt').read_text(), json.dumps(ANSWER))

    def test_missing_annotations_member_preserves_database_and_reports_transport_error(self):
        self.manifest()
        payload = json.dumps({'database': ANSWER})
        def send(*args):
            if 'estimate' in args[0]: return self.provider(*args)
            return self.response(payload)
        self.assertIsNone(self.execute(send)['failure'])
        final = self.out/'B001/i0/final'
        assessment = read(final/'output-assessment.json')
        self.assertTrue(assessment['database_schema_valid'])
        self.assertFalse(assessment['delivery_contract_valid'])
        self.assertFalse(assessment['annotations_received'])
        self.assertEqual(read(final/'database.json'), ANSWER)
        self.assertIsNone(read(final/'annotations.json')['annotations'])
        self.assertEqual((final/'raw-answer.txt').read_text(), payload)

    def test_multiple_valid_source_ids_are_diagnosed_without_repair(self):
        reader = Reader(self.root/'prepared')
        ids = sorted(reader.entries)
        self.assertGreaterEqual(len(ids), 2)
        for separator in ('; ', ', '):
            annotation = self.annotated(source=separator.join(ids))
            original = copy.deepcopy(annotation)
            report = submission.annotation_record([annotation], ANSWER, read(reader.folder/'dictionary.json'), reader,
                case='B001', stage='i0', raw_hash='synthetic', database_hash='synthetic', transport='paired')
            self.assertEqual(report['diagnostics'], [{'annotation': 0, 'error': 'unknown_material',
                'reason': 'multiple_material_ids_in_single_source', 'material_ids': ids}])
            self.assertEqual(report['annotations'], [original])
            self.assertEqual(annotation, original)
        annotation = self.annotated(source=ids[0]+'; invented')
        report = submission.annotation_record([annotation], ANSWER, read(reader.folder/'dictionary.json'), reader,
            case='B001', stage='i0', raw_hash='synthetic', database_hash='synthetic', transport='paired')
        self.assertEqual(report['diagnostics'], [{'annotation': 0, 'error': 'unknown_material'}])

    def test_annotations_tampering_blocks_offline_recovery(self):
        self.manifest(); self.execute(self.sender([]))
        write(self.out/'B001/ssr/final/annotations.json', {'changed': True})
        self.assertIsNotNone(self.execute(offline=True)['failure'])
        self.assertEqual(self.provider.completions, 3)

    def test_preparation_identity_effective_inputs_and_source_changes(self):
        reader = Reader(self.root/'prepared')
        origin = dataset_identity.verify_prepared(reader, live_sources=True)
        actual = read(reader.folder/'effective-inputs.json')
        self.assertEqual(actual['dataset_identity'], origin['dataset']['identity'])
        self.assertEqual(actual['format_counts'], {'.txt': 1, '.xml': 1})
        self.assertEqual(actual['excluded'], [{'path': 'article.pdf', 'reason': 'main_article_pdf'}])
        prompt = self.root/'dataset/tasks/basic/B001/complete-prompt.md'
        prompt.write_text(prompt.read_text()+' New task rule.')
        with self.assertRaises(Stop) as caught:
            dataset_identity.verify_prepared(reader, live_sources=True)
        self.assertEqual(caught.exception.status, 'stale_preparation')
        self.assertEqual(dataset_identity.verify_prepared(reader), origin)

    def test_freeze_rejects_changed_task_and_legacy_preparation(self):
        self.manifest(); self.frozen.unlink()
        p = self.root/'prepared/materials.json'; value = read(p)
        value['protocol'] = 'biotracebench-materials-1'; write(p, value); seal(p.parent)
        with self.assertRaises(Stop) as caught:
            freeze(self.root/'draft.json', self.frozen)
        self.assertEqual(caught.exception.status, 'stale_preparation')

    def test_expected_new_root_rejects_cache_from_old_root(self):
        other = self.root/'new-dataset'; source_fixture(other)
        reader = Reader(self.root/'prepared')
        with self.assertRaises(Stop):
            dataset_identity.verify_prepared(reader, dataset_identity.dataset(other))

    def test_recovery_does_not_need_live_dataset_or_credentials(self):
        self.manifest(); self.assertIsNone(self.execute()['failure'])
        (self.root/'dataset').rename(self.root/'moved-dataset')
        self.assertIsNone(self.execute(offline=True)['failure'])
        self.assertEqual(self.provider.completions, 3)

    def test_main_pdf_excluded_before_content_access_or_upload(self):
        dataset = self.root/'dataset'
        original = Path.open
        def guarded(path, *args, **kwargs):
            if path.suffix.lower() == '.pdf' or 'gold_standard' in path.parts:
                raise AssertionError('Forbidden source access')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', guarded):
            report = prepare(dataset, 'B001', self.root/'second-preparation')
            reader = Reader(self.root/'second-preparation')
            dataset_identity.verify_prepared(reader, live_sources=True)
        self.assertEqual(report['status'], 'ready_offline')
        self.assertFalse(any(p.suffix.lower() == '.pdf' for p in reader.folder.rglob('*')))
        (reader.folder/'forbidden.PDF').write_bytes(b'not read')
        with patch.object(Path, 'open', guarded), self.assertRaises(Stop) as caught:
            Reader(reader.folder)
        self.assertEqual(caught.exception.status, 'blocked_pdf')

    def test_cli_draft_requires_dataset_and_rejects_wrong_package(self):
        from biotracebench.cli import main
        self.manifest()
        parent = self.root/'prepared-parent'; parent.mkdir()
        (self.root/'prepared').rename(parent/'B001')
        write(self.root/'profile.json', {'provider_template': str(Path(__file__).resolve().parents[1]/'configs/models/conversation-vendors/kimi.json'), 'settings': read(self.root/'draft.json')['model']})
        args = ['draft', '--profile', str(self.root/'profile.json'), '--prepared', str(parent), '--template', str(self.root/'draft.json'), '--out', str(self.root/'new-draft.json')]
        with self.assertRaisesRegex(ValueError, '--dataset'):
            main(args)
        other = self.root/'other-dataset'; source_fixture(other)
        with self.assertRaises(Stop):
            main(args+['--dataset', str(other)])
        main(args+['--dataset', str(self.root/'dataset')])
        self.assertEqual(read(self.root/'new-draft.json')['dataset']['root'], str((self.root/'dataset').resolve()))

    def test_office_pdf_member_is_not_opened_or_copied(self):
        material = self.root/'dataset/materials/basic/B001'
        document = material/'embedded.docx'
        with zipfile.ZipFile(document, 'w') as archive:
            archive.writestr('word/document.xml', '<document/>')
            archive.writestr('word/embeddings/forbidden.PDF', b'never open')
        m = read(material/'materials.json')
        m['files'].append({'path':document.name,'input_use':'model','role':'supplement',
                           'bytes':document.stat().st_size,'sha256':sha(document)})
        write(material/'materials.json',m)
        original=zipfile.ZipFile.open
        def guard(archive,name,*args,**kwargs):
            filename=name.filename if isinstance(name,zipfile.ZipInfo) else name
            if Path(filename).suffix.lower()=='.pdf':
                raise AssertionError('PDF member opened')
            return original(archive,name,*args,**kwargs)
        target=self.root/'office-preparation'
        with patch.object(zipfile.ZipFile,'open',guard):
            report=prepare(self.root/'dataset','B001',target)
        self.assertEqual(report['status'],'blocked')
        self.assertIn('Unsupported embedded PDF member',report['errors'][0]['error'])
        self.assertFalse(list(target.glob('*/source.docx')))

    def test_clinical_four_tables_share_the_same_business_and_transport_schema(self):
        from biotracebench.output_contract import output_schema
        from biotracebench.schema import validate
        from test_biotracebench import CLINICAL_ANSWER
        tables={}
        for key,rows in CLINICAL_ANSWER.items():
            fields={field:{'type':'integer' if isinstance(value,int) else 'string'} for field,value in (rows[0] if rows else {}).items()}
            tables[key]={'type':'array','items':{'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}}
        domain={'type':'object','properties':tables,'required':list(CLINICAL_ANSWER),'additionalProperties':False}
        schemas=[output_schema(domain,stage,submission.PROTOCOL)['schema'] for stage in ('i0','gsr','ssr')]
        self.assertEqual(schemas[0],schemas[1]);self.assertEqual(schemas[1],schemas[2])
        self.assertEqual(schemas[0]['properties']['database'],domain)
        self.assertEqual(validate({'database':CLINICAL_ANSWER,'annotations':[]},schemas[0]),[])

    def relation_fixture(self):
        fields = ['population_a_id', 'relationship', 'population_b_id']
        dictionary = {'population': {'identifier': 'population_id', 'fields': [{'key': 'population_id'}]},
                      'population_relation': {'identifier': None, 'fields': [{'key': k} for k in fields]}}
        key = {'population_a_id': 'P1', 'relationship': 'subset of', 'population_b_id': 'P2'}
        database = {'population': [{'population_id': 'P1'}, {'population_id': 'P2'}],
                    'population_relation': [copy.deepcopy(key)]}
        annotation = {'table': 'population_relation', 'record_id': None, 'record_key': copy.deepcopy(key),
                      'field': None, 'kind': 'evidence', 'source': 'm0001', 'locator': 'characters 0:20',
                      'text': 'Synthetic source supports this relation.'}
        return dictionary, database, annotation

    def annotation_report(self, database, dictionary, annotation, protocol=submission.PROTOCOL):
        return submission.annotation_record([annotation], database, dictionary, Reader(self.root / 'prepared'),
            case='SYN', stage='ssr', raw_hash='synthetic', database_hash='synthetic', transport='paired', protocol=protocol)

    def test_relation_composite_key_binds_without_modifying_the_business_tables(self):
        dictionary, database, annotation = self.relation_fixture()
        original = copy.deepcopy((database, annotation))
        self.assertEqual(self.annotation_report(database, dictionary, annotation)['diagnostics'], [])
        self.assertEqual((database, annotation), original)
        self.assertNotIn('record_id', database['population_relation'][0])
        self.assertNotIn('record_key', database['population_relation'][0])

    def test_relation_direction_duplicates_and_missing_records_remain_diagnostic(self):
        dictionary, database, annotation = self.relation_fixture()
        annotation['record_key']['population_a_id'] = 'P2'
        annotation['record_key']['population_b_id'] = 'P1'
        self.assertEqual(self.annotation_report(database, dictionary, annotation)['diagnostics'][0]['error'], 'unresolved_record_binding')
        dictionary, database, annotation = self.relation_fixture()
        database['population_relation'].append(copy.deepcopy(database['population_relation'][0]))
        self.assertEqual(self.annotation_report(database, dictionary, annotation)['diagnostics'][0]['error'], 'ambiguous_record_binding')
        database['population_relation'] = []
        self.assertEqual(self.annotation_report(database, dictionary, annotation)['diagnostics'][0]['error'], 'unresolved_record_binding')

    def test_annotation_schema_requires_exactly_one_nonnull_record_reference(self):
        from biotracebench.schema import validate
        dictionary, database, annotation = self.relation_fixture()
        shape = submission.schema({})['properties']['annotations']['items']
        self.assertEqual(validate(annotation, shape), [])
        for invalid in (dict(annotation, record_id='invented'), dict(annotation, record_key=None),
                        dict(annotation, record_key={'population_a_id': 'P1'})):
            self.assertTrue(validate(invalid, shape))
            self.assertEqual(self.annotation_report(database, dictionary, invalid)['diagnostics'][0]['error'], 'annotation_structure')
        old = dict(annotation); old.pop('record_key'); old['record_id'] = 'invented'
        self.assertTrue(validate(old, shape))

    def test_legacy_annotation_schema_and_primary_id_binding_remain_available(self):
        from biotracebench.schema import validate
        dictionary, database, _ = self.relation_fixture()
        old = self.annotated(record='P1'); old.pop('record_key')
        old.update(table='population', field=None)
        report = self.annotation_report(database, dictionary, old, submission.LEGACY_PROTOCOL)
        self.assertEqual(report['protocol'], submission.LEGACY_PROTOCOL)
        self.assertEqual(report['diagnostics'], [])
        legacy_schema = submission.schema({}, submission.LEGACY_PROTOCOL)['properties']['annotations']['items']
        self.assertEqual(validate(old, legacy_schema), [])
        self.assertNotIn('record_key', old)

    def test_read_only_export_retains_legacy_annotation_payload(self):
        self.manifest()
        self.execute(self.sender([]))
        final = self.out / 'B001/ssr/final'
        old = read(final / 'annotations.json')
        old['protocol'] = submission.LEGACY_PROTOCOL
        old['annotations'] = [self.annotated()]
        old['annotations'][0].pop('record_key')
        write(final / 'annotations.json', old); seal(final)
        before = {str(p): sha(p) for p in self.out.rglob('*') if p.is_file()}
        run_report(self.out, self.root / 'old-export')
        self.assertEqual(read(self.root / 'old-export/B001/ssr/annotations.json'), old)
        self.assertEqual(before, {p: sha(p) for p in before})


if __name__ == '__main__':
    unittest.main()
