"""Canonical conditions preserve independent starts and immutable responses."""
import copy
import json
import unittest
from test_biotracebench import ANSWER
from biotracebench import conditions, prompts
from biotracebench.common import read, write, sha, digest
from biotracebench.runner import freeze, validate_manifest, increase_limits
from biotracebench.export import run_report
from biotracebench_analysis.statistics import aggregate
from biotracebench.prompts import CONTINUE_OUTPUT

class ConditionTests(unittest.TestCase):
    def setUp(self):
        import tempfile, socket
        from pathlib import Path
        from unittest.mock import patch
        from test_biotracebench import source_fixture, SyntheticProvider
        from biotracebench.materials import prepare
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.network = patch.object(socket, 'socket', side_effect=AssertionError('Live network forbidden'))
        self.network.start()
        source_fixture(self.root / 'dataset')
        prepare(self.root / 'dataset', 'B001', self.root / 'prepared')
        self.out = self.root / 'run'
        self.frozen = self.root / 'frozen.json'
        self.provider = SyntheticProvider()
        self.wire = []

    def tearDown(self):
        self.network.stop()
        self.temp.cleanup()

    def manifest(self, strict=False):
        from test_biotracebench import MODEL, TARIFF
        from biotracebench import schema
        from model_conversation import Adapter
        from biotracebench.common import seal
        if strict:
            value = read(self.root / 'prepared/schema.json')
            for table, rows in ANSWER.items():
                properties = {key: {'type': 'array', 'items': {'type': 'string'}} if isinstance(v, list)
                              else {'type': 'integer'} if isinstance(v, int) else {'type': 'string'} for key, v in rows[0].items()}
                value['properties'][table]['items'] = {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}
            write(self.root / 'prepared/schema.json', value)
            seal(self.root / 'prepared')
        model = Adapter(copy.deepcopy(MODEL)).c
        model['capabilities'] = {**model.get('capabilities', {}), 'vision': True, 'tools': False, 'json_schema': True}
        limits = {'max_requests': 32, 'max_total_tokens': 100000, 'max_cost': '8'}
        draft = {'protocol': 'biotracebench-run-2', 'state': 'draft', 'input_mode': 'all_materials',
                 'pdf_policy': 'structured_article_with_pdf_attachments', 'concurrency': 1, 'stages': list(conditions.CANONICAL),
                 'tasks': [{'case_id': 'B001', 'prepared': str(self.root / 'prepared'), 'required_reads': []}],
                 'model': model, 'budgets': {s: dict(limits) for s in conditions.CANONICAL}, 'max_total_cost': '24',
                 'tariff': copy.deepcopy(TARIFF), 'parameter_basis': [{'source': 'synthetic fixtures only'}]}
        if strict:
            draft['final_output_policy'] = 'json_schema_strict'
        write(self.root / 'draft.json', draft)
        return freeze(self.root / 'draft.json', self.frozen)

    def send(self, *args):
        if 'estimate' not in args[0]:
            self.wire.append(json.loads(args[1]))
        return self.provider(*args)

    def execute(self, sender=None, offline=False):
        import os
        from unittest.mock import patch
        from biotracebench.runner import run
        with patch.dict(os.environ, {} if offline else {'MOONSHOT_API_KEY': 'synthetic'}, clear=offline):
            return run(self.frozen, self.out, sender=sender or self.send, offline=offline)

    def response(self, text=None, tool=None, finish='stop'):
        from biotracebench.common import encoded
        self.provider.completions += 1
        message = {'role': 'assistant', 'content': text, 'reasoning_content': 'preserved synthetic reasoning'}
        if tool:
            message['tool_calls'] = [{'id': 'injected', 'type': 'function', 'function': {'name': tool, 'arguments': '{}'}}]
        return 200, {}, encoded({'model': 'kimi-k3', 'choices': [{'message': message, 'finish_reason': finish}],
                                'usage': {'prompt_tokens': 200, 'completion_tokens': 20, 'cached_tokens': 0, 'cache_write_tokens': 0}})

    def test_new_run_paths_forks_logs_costs_export_and_offline_replay(self):
        manifest = self.manifest()
        result = self.execute()
        self.assertIsNone(result['failure'])
        self.assertEqual(result['tasks']['B001'], dict.fromkeys(conditions.CANONICAL, 'completed'))
        self.assertEqual(self.provider.completions, 3)
        self.assertEqual({p.name for p in (self.out / 'B001').iterdir()}, set(conditions.CANONICAL))
        g = read(self.out / 'B001/gsr/branch.json')
        s = read(self.out / 'B001/ssr/branch.json')
        self.assertEqual(g['i0_history_sha256'], s['i0_history_sha256'])
        self.assertEqual(g['stage'], 'gsr')
        self.assertNotIn('initial_history_sha256', g)
        self.assertEqual(manifest['prompt_hashes']['ssr'], digest(prompts.SSR))
        self.assertNotIn('integrated_review', manifest['prompt_hashes'])
        self.assertIn('ssr_output_contract', manifest)
        self.assertNotIn('ir_output_contract', manifest)
        for stage in conditions.CANONICAL:
            self.assertEqual(read(self.out / 'B001' / stage / 'final/database.json'), ANSWER)
            self.assertTrue((self.out / 'B001' / stage / 'calls/00000/completion/response.bin').exists())
        costs = read(self.out / 'costs.json')
        self.assertEqual({r['stage'] for r in costs['calls']}, set(conditions.CANONICAL))
        self.assertIn('I0+GSR', str(costs)); self.assertIn('I0+SSR', str(costs))
        self.assertNotIn('I0+IR', str(costs))
        self.assertIsNone(self.execute(offline=True)['failure'])
        self.assertEqual(self.provider.completions, 3)
        run_report(self.out, self.root / 'export')
        self.assertEqual(read(self.root / 'export/B001/ssr/database.json'), ANSWER)
        identity = read(self.root / 'export/condition-identity.json')
        self.assertFalse(identity['historical'])
        self.assertIn('GSR', (self.root / 'export/index.html').read_text())
        self.assertIn('SSR', (self.root / 'export/index.html').read_text())

    def test_strict_schemas_preserve_database_with_new_names(self):
        manifest = self.manifest(strict=True)
        self.assertIsNone(self.execute()['failure'])
        schemas = [b['response_format']['json_schema'] for b in self.wire]
        self.assertEqual([x['name'] for x in schemas], ['biotracebench_i0', 'biotracebench_gsr', 'biotracebench_ssr'])
        self.assertEqual(schemas[0]['schema'], schemas[1]['schema'])
        self.assertEqual(schemas[0]['schema'], schemas[2]['schema'])
        self.assertEqual(set(schemas[0]['schema']['properties']), {'database', 'annotations'})
        self.assertEqual(set(manifest['tasks'][0]['output_schema_hashes']), set(conditions.CANONICAL))


    def test_mixed_names_and_legacy_strategy_in_new_protocol_rejected(self):
        self.manifest()
        original = read(self.root / 'draft.json')
        bad = copy.deepcopy(original); bad['stages'][1] = 'ordinary_review'
        with self.assertRaises(ValueError): validate_manifest(bad, frozen=False)
        bad = copy.deepcopy(original); bad['budgets']['integrated_review'] = bad['budgets'].pop('ssr')
        with self.assertRaises(ValueError): validate_manifest(bad, frozen=False)
        bad = copy.deepcopy(original); bad['ontology_mode'] = 'model_query'
        with self.assertRaises(ValueError): validate_manifest(bad, frozen=False)
        bad = copy.deepcopy(original); bad['protocol'] = 'biotracebench-run-1'
        with self.assertRaises(ValueError): validate_manifest(bad, frozen=False)


    def test_approved_extension_continues_new_i0_without_extra_review(self):
        manifest = self.manifest()
        full = json.dumps(ANSWER); prefix = full[:10]
        def send(*args):
            if 'estimate' in args[0]: return self.provider(*args)
            body = json.loads(args[1])
            if self.provider.completions == 0:
                return self.response(prefix, finish='length')
            if body['messages'][-1].get('content') == CONTINUE_OUTPUT:
                return self.response(full[10:])
            return self.send(*args)
        result = self.execute(send)
        self.assertEqual(result['tasks']['B001']['i0'], 'paused_truncated')
        response_path = self.out / 'B001/i0/calls/00000/completion/response.bin'
        original_hash = sha(response_path)
        increase_limits(self.frozen, self.out, {'max_output_tokens': manifest['model']['max_output_tokens'] * 2}, targets=['B001/i0'])
        from biotracebench.limits import effective, extensions
        entries = extensions(manifest, self.out)
        self.assertEqual(effective(manifest, entries, 'B001', 'i0')['model']['max_output_tokens'], 2000)
        self.assertEqual(effective(manifest, entries, 'B001', 'gsr')['model']['max_output_tokens'], 1000)
        self.assertEqual(effective(manifest, entries, 'B001', 'ssr')['model']['max_output_tokens'], 1000)
        result = self.execute(send)
        self.assertIsNone(result['failure'])
        self.assertEqual(self.provider.completions, 4)
        self.assertEqual(sha(response_path), original_hash)
        self.assertEqual(read(self.out / 'B001/i0/final/database.json'), ANSWER)

    def test_aggregate_changes_names_without_changing_values_or_intervals(self):
        before = []
        for n, domain in enumerate(('basic', 'clinical')):
            scores = {}
            for index, stage in enumerate(conditions.LEGACY):
                scores[stage] = {'status': 'final_under_frozen_dictionary', **{m: dict.fromkeys(('precision', 'recall', 'f1'), 0.2 + 0.1 * index + 0.01 * n) for m in ('field', 'record')}}
            before.append({'study_id': str(n), 'domain': domain, 'conditions': scores})
        after = copy.deepcopy(before)
        for study in after:
            study['conditions'] = {conditions.canonical(k): v for k, v in study['conditions'].items()}
        old = aggregate(before); new = aggregate(after)
        for domain, stages in old['means'].items():
            self.assertEqual({conditions.canonical(k): v for k, v in stages.items()}, new['means'][domain])
        for key, value in old['paired_differences'].items():
            domain, metric, contrast = key.split(':')
            a, b = contrast.split('-')
            self.assertEqual(value, new['paired_differences'][f'{domain}:{metric}:{conditions.canonical(a)}-{conditions.canonical(b)}'])
        with self.assertRaises(ValueError): aggregate([before[0], after[1]])
