"""Native imports: immutable evidence, blinded routing and offline recovery."""
import copy
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from model_conversation.archive import read, sha, write
from biotracebench_scoring import native_codex as native
from biotracebench_scoring.logical_contract import bind_policy, policy_template
from biotracebench_scoring.task_grading_contract import inventory


DICT = {'sample': {'identifier': 'id', 'fields': [{'key': key}
          for key in ('id', 'label', 'value', 'optional')]}}
POLICY = {'version': 'biotracebench-score-2',
          'reference_contract': 'biotracebench-fixed-reference-1',
          'compound_fields': [], 'field_roles': {}, 'frozen': False,
          'null_policy': 'PRIVATE_OLD_PHYSICAL_PRESENCE_RULE',
          'numeric_policy': 'Qwen applies exact numeric equality.',
          'unit_catalog': {'version': 'synthetic-units'}}
GOLD = {'sample': [{'id': 'S1', 'label': 'Arm A', 'value': 5, 'optional': None}]}
ACTOR = {'kind': 'native_codex', 'agent_id': '/root/synthetic', 'session_id': 'synthetic-test'}


def fixture_policy(inv):
    """Explicit scientific requirements for the two synthetic quantities."""
    references = [c for c in inv['cells'] if c['side'] == 'reference'
                  and c['role'] == 'scientific']
    fields = []
    assertions = {'label': 'The source-defined arm is Arm A.',
                  'value': 'The source-reported value is exactly 5.'}
    for cell in references:
        value = json.loads(cell['value_json'])
        fields.append({'id': 'sample:0:' + cell['field'], 'reference_row': cell['row'],
            'field': cell['field'], 'required_assertions': [
                {'id': 'required', 'text': assertions[cell['field']], 'placement': 'strict',
                 'basis': 'Synthetic task explicitly assigns the quantity to this field.',
                 'reference_evidence': [{'cell': cell['id'], 'path': '',
                                         'quote': value if isinstance(value, str) else None}]}]
            if cell['nonempty'] else []})
    return policy_template({'contract': 'biotracebench-logical-fields-2',
                            'fields': fields, 'links': []}, inv)


def fixture_reply(inv, template):
    """Explicit, known-correct fixture assertions; never used on real data."""
    pred = next(r for r in inv['rows'] if r['side'] == 'prediction')
    ref = next(r for r in inv['rows'] if r['side'] == 'reference')
    fields = []
    for spec in bind_policy(template, inv)['fields']:
        cell = next(c for c in inv['cells'] if c['row'] == pred['id'] and c['field'] == spec['field'])
        value = json.loads(cell['value_json'])
        evidence = [{'cell': cell['id'], 'path': '',
                     'quote': value if isinstance(value, str) else None}] if cell['nonempty'] else []
        fields.append({'field_id': spec['id'], 'prediction_evidence': evidence,
            'assertions': [{'assertion_id': a['id'], 'verdict': 'correct', 'evidence': evidence,
                            'reason': 'The explicit synthetic requirement is expressed exactly.'}
                           for a in spec['required_assertions']],
            'integrity': {'verdict': 'correct', 'evidence': [],
                          'reason': 'The synthetic expression adds no unsupported assertion.'},
            'verdict': 'correct' if spec['required_assertions'] else 'not_scored',
            'reason': 'The synthetic field preserves its declared quantity.'})
    return {'records': [{'prediction_row': pred['id'], 'reference_row': ref['id'],
                         'verdict': 'matched', 'reason': 'Both rows describe source-defined Arm A.'}],
            'fields': fields, 'unscored': [], 'reference_issues': []}


class NativeCodexTests(unittest.TestCase):
    def test_implementation_binds_counting_and_input_identity_dependencies(self):
        bound = native._implementation()
        for path in ('evaluation.py', 'reference_policy.py', 'scoring_items.py',
                     'grading_precision.py', 'model_conversation/archive.py'):
            self.assertIn(path, bound)
            self.assertEqual(len(bound[path]), 64)

    def fixture(self, root, *, terminal=False, task_definition='Report Arm A and its value of 5.'):
        inv = inventory(GOLD, GOLD, DICT, POLICY)
        policy = fixture_policy(inv)
        archive = root / 'archive'; archive.mkdir()
        old = {'inventory': inv, 'marking': {'reason': 'PRIVATE_OLD_MARK_SENTINEL'},
               'scores': 'PRIVATE_OLD_SCORE_SENTINEL', 'human_labels': 'PRIVATE_HUMAN_SENTINEL'}
        packet = archive / 'packet.json.gz'
        packet.write_bytes(gzip.compress(json.dumps(old).encode()))
        write(archive / 'reference.json', GOLD)
        positions = [{'case': 'SYNTHETIC', 'model': model, 'condition': condition,
                      'domain': 'basic', 'judgment': 'packet.json.gz', 'zero_cause': None,
                      'expected': 'PRIVATE_EXPECTED_SENTINEL'}
                     for model, condition in [('PRIVATE_MODEL_A', 'i0'), ('PRIVATE_MODEL_B', 'gsr')]]
        if terminal:
            positions.append({'case': 'SYNTHETIC', 'model': 'PRIVATE_MODEL_C', 'condition': 'ssr',
                              'domain': 'basic', 'judgment': None, 'zero_cause': 'no_usable_output'})
        write(archive / 'manifest.json', {'positions': positions,
              'files': {'packet.json.gz': sha(packet)}, 'cases': [{'case': 'SYNTHETIC',
                  'reference': 'reference.json', 'current_reference_sha256': sha(archive/'reference.json')}]})
        write(root / 'contexts.json', {'SYNTHETIC': {'task_definition': task_definition,
            'dictionary': DICT, 'policy': POLICY, 'task_policy': policy,
            'sources': [{'id': 'source-a', 'text': 'Arm A has value 5.'}],
            'field_rubric': 'PRIVATE_OLD_RUBRIC_SENTINEL', 'input_identity': 'PRIVATE_ROUTE_SENTINEL'}})
        prepared = native.prepare_native(archive/'manifest.json', root/'contexts.json', root/'plan')
        return inv, policy, prepared

    def finish(self, root, inv, policy):
        reply = fixture_reply(inv, policy)
        for phase in ('first', 'review'):
            self.assertEqual(native.ingest_native(root/'plan', 'n-00001', reply, ACTOR,
                             phase=phase)['status'], 'accepted')
        return reply

    def test_prepare_blinds_prior_marks_model_and_routes_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, _, prepared = self.fixture(root)
            self.assertEqual((prepared['positions'], prepared['unique_jobs']), (2, 1))
            text = '\n'.join(p.read_text() for p in (root/'plan/judge-inputs').rglob('*.json'))
            for sentinel in ('PRIVATE_OLD', 'PRIVATE_MODEL', 'PRIVATE_ROUTE', 'PRIVATE_HUMAN', 'PRIVATE_EXPECTED'):
                self.assertNotIn(sentinel, text)
            self.assertIn('PRIVATE_MODEL_A', (root/'plan/private/routes.json').read_text())
            self.assertIn('Native Codex applies exact numeric equality.', text)

    def test_first_review_replay_export_and_same_import_are_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); inv, policy, _ = self.fixture(root)
            reply = self.finish(root, inv, policy)
            receipts = sorted((root/'plan/imports/n-00001').glob('*.json'))
            before = [p.read_bytes() for p in receipts]
            native.ingest_native(root/'plan', 'n-00001', reply, ACTOR, phase='review')
            first = native.replay_native(root/'plan', root/'out')
            second = native.replay_native(root/'plan', root/'out')
            self.assertEqual(first, second)
            self.assertEqual(first['completed_positions'], 2)
            self.assertEqual([p.read_bytes() for p in receipts], before)
            exported = native.export_native(root/'plan', root/'export', require_complete=True)
            data = read(exported['path'])
            self.assertEqual(data['positions'][0]['field_items'], [['sample', 0, 'label', True],
                                                                  ['sample', 0, 'value', True]])
            self.assertEqual(data['positions'][0]['record_items'], [['sample', 0, True]])
            self.assertTrue(all(sha(path) == value for path, value in data['source_sha256'].items()))

    def test_pending_campaign_exports_full_position_grid_without_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            result = native.export_native(root/'plan', root/'out')
            data = read(result['path'])
            self.assertEqual(len(data['positions']), 2)
            self.assertTrue(all(p['status'] == 'awaiting_first_pass' and p['score'] is None
                                for p in data['positions']))
            with self.assertRaisesRegex(ValueError, 'complete exact native replay'):
                native.export_native(root/'plan', root/'other', require_complete=True)

    def test_record_stage_freezes_mapping_and_field_request_contains_no_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); inv, policy, _ = self.fixture(root)
            reply = fixture_reply(inv, policy)
            mapping = native.ingest_native(root/'plan', 'n-00001', {'records': reply['records']},
                                             ACTOR, scope='records')
            request = native.native_request(root/'plan', 'n-00001', scope='fields')
            self.assertEqual(request['record_mapping_identity'], mapping['record_mapping_identity'])
            self.assertNotIn('score', request)
            self.assertNotIn('actor', request)
            fields = {k: v for k, v in reply.items() if k != 'records'}
            rejected = native.ingest_native(root/'plan', 'n-00001', fields, ACTOR, scope='fields',
                                             mapping_identity='wrong')
            self.assertEqual(rejected['status'], 'validation_error')
            accepted = native.ingest_native(root/'plan', 'n-00001', fields, ACTOR, scope='fields',
                                             mapping_identity=mapping['record_mapping_identity'])
            self.assertEqual(accepted['status'], 'accepted')
            self.assertEqual(native.replay_native(root/'plan', root/'out')['completed_jobs'], 0)

    def test_invalid_attempt_is_retained_and_later_valid_import_recovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); inv, policy, _ = self.fixture(root)
            rejected = native.ingest_native(root/'plan', 'n-00001', {'records': []}, ACTOR)
            self.assertEqual(rejected['status'], 'validation_error')
            saved = (root/'plan/imports/n-00001/00001.json').read_bytes()
            self.assertEqual(native.replay_native(root/'plan', root/'out')['status'], 'incomplete')
            self.finish(root, inv, policy)
            self.assertEqual(native.replay_native(root/'plan', root/'out')['status'], 'completed')
            self.assertEqual((root/'plan/imports/n-00001/00001.json').read_bytes(), saved)

    def test_completed_phase_is_immutable_and_actor_claim_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); inv, policy, _ = self.fixture(root)
            reply = fixture_reply(inv, policy)
            for actor in ({'kind': 'codex_cli', 'agent_id': 'x'},
                          {'kind': 'native_codex', 'agent_id': 'x', 'transport_receipt': 'fake'}, {}):
                with self.assertRaises(ValueError):
                    native.ingest_native(root/'plan', 'n-00001', reply, actor)
            native.ingest_native(root/'plan', 'n-00001', reply, ACTOR)
            altered = copy.deepcopy(reply); altered['fields'][0]['reason'] = 'Changed native claim.'
            with self.assertRaises(FileExistsError):
                native.ingest_native(root/'plan', 'n-00001', altered, ACTOR)

    def test_frozen_input_route_and_import_tampering_are_rejected(self):
        for kind in ('packet', 'context', 'route', 'import'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); inv, policy, _ = self.fixture(root)
                self.finish(root, inv, policy)
                target = {'packet': root/'plan/judge-inputs/jobs/n-00001/packet.json',
                          'context': root/'plan/judge-inputs/tasks/t-00001/context.json',
                          'route': root/'plan/private/routes.json',
                          'import': root/'plan/imports/n-00001/00001.json'}[kind]
                target.write_text('{}')
                with self.assertRaises((ValueError, KeyError)):
                    native.replay_native(root/'plan', root/'out')

    def test_local_zero_completes_without_a_native_actor_or_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch('subprocess.Popen', side_effect=AssertionError('No process allowed')), \
                    patch('socket.socket', side_effect=AssertionError('No network allowed')):
                inv, policy, prepared = self.fixture(root, terminal=True)
                self.assertEqual(prepared['unique_jobs'], 2)
                self.finish(root, inv, policy)
                result = native.replay_native(root/'plan', root/'out')
                index = read(result['index_path'])
            self.assertEqual(result['completed_positions'], 3)
            terminal = next(p for p in index['position_results'] if p['zero_cause'])
            self.assertEqual(terminal['status'], 'local_zero_completed')
            self.assertEqual(terminal['score']['field']['tp'], 0)
            with self.assertRaisesRegex(ValueError, 'Local terminal jobs'):
                native.ingest_native(root/'plan', terminal['job_id'], {}, ACTOR)


if __name__ == '__main__':
    unittest.main()
