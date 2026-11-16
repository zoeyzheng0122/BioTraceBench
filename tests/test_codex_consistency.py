"""Fresh Codex context comparisons with native synthetic phase archives."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from model_conversation.archive import digest
from biotracebench_scoring import codex_consistency as consistency
from biotracebench_scoring.task_grading_contract import inventory, mark_all
from test_biotracebench_task_grading import reply_for

DICT = {
    'sample': {'identifier': 'id', 'fields': [{'key': key} for key in ('id', 'sample_material')]},
    'result': {'identifier': 'id', 'references': {'sample_id': 'sample'},
               'fields': [{'key': key} for key in ('id', 'sample_id', 'result_value')]}}
POLICY = {'reference_contract': 'biotracebench-fixed-reference-1', 'field_roles': {}}
DB = {'sample': [{'id': 'S1', 'sample_material': 'Liver protein'}],
      'result': [{'id': 'R1', 'sample_id': 'S1', 'result_value': 2}]}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value))


def job(root, number, *, verdict='correct', unrelated_value=2, material='Liver protein',
        rename=False, actual_model='synthetic-codex', two_samples=False, swap_samples=False):
    reference = copy.deepcopy(DB)
    if two_samples:
        reference['sample'].append({'id': 'S2', 'sample_material': 'Plasma'})
        reference['result'].append({'id': 'R2', 'sample_id': 'S2', 'result_value': 3})
    prediction = copy.deepcopy(reference)
    prediction['result'][0]['result_value'] = unrelated_value
    prediction['sample'][0]['sample_material'] = material
    if rename:
        prediction['sample'][0]['id'] = 'local-sample-nine'
        prediction['result'][0]['sample_id'] = 'local-sample-nine'
        prediction['result'][0]['id'] = 'local-result-eight'
    inv = inventory(prediction, reference, DICT, POLICY)
    payload = {'inventory': inv, 'dictionary': DICT, 'policy': POLICY, 'sources': [],
               'task_definition': 'Recover the selected liver sample and result.',
               'semantic_definition': {'contract': 'synthetic-semantic'}, 'field_rubric': {'required': 'field-local'}}
    packet = {'payload': payload, 'input_identity': digest(payload)}
    pairs = None
    if swap_samples:
        sides = {side: [r for r in inv['rows'] if r['side'] == side] for side in ('prediction', 'reference')}
        reference_rows = sides['reference'].copy()
        sample_indices = [i for i, r in enumerate(reference_rows) if r['table'] == 'sample']
        a, b = sample_indices
        reference_rows[a], reference_rows[b] = reference_rows[b], reference_rows[a]
        pairs = list(zip(sides['prediction'], reference_rows))
    marking = reply_for(inv, pairs=pairs, overrides={'sample_material': verdict, 'sample_id': 'correct'})
    score = mark_all(inv, marking)
    result = {'plan_identity': 'plan', 'input_identity': packet['input_identity'], 'marking': marking,
              'score': score, 'configured_profile': {'model': 'synthetic-codex'},
              'actual_models': [actual_model], 'local_terminal': False}
    result['result_identity'] = digest(result)
    folder = root / ('job-' + str(number))
    request = {'payload': payload, 'instruction': 'Synthetic request without labels.'}
    write(folder / 'whole/attempt-001/request.json', request)
    write(folder / 'whole/attempt-001/reply.json', marking)
    write(folder / 'whole/accepted.json', {'request_identity': digest(request),
                                         'reply_identity': digest(marking), 'reply': marking})
    write(folder / 'packet.json', packet); write(folder / 'result.json', result)
    return {'job_id': 'job-' + str(number), 'case': 'synthetic', 'model': 'generation-model',
            'condition': 'i0', 'domain': 'basic', 'status': 'complete',
            'result': str(folder / 'result.json'), 'packet': str(folder / 'packet.json')}


class CodexConsistencyTests(unittest.TestCase):
    def inspect(self, root, positions):
        write(root / 'index.json', {'plan_identity': 'plan', 'positions': positions})
        summary = consistency.inspect(root / 'index.json', root / 'report.json')
        return summary, consistency.read(root / 'report.json')

    def test_unrelated_downstream_value_does_not_hide_same_sample_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            positions = [job(root, 1), job(root, 2, verdict='incorrect', unrelated_value=7)]
            hashes = {str(p): consistency.sha(p) for p in root.rglob('*.json')}
            summary, report = self.inspect(root, positions)
            self.assertEqual(summary['inspected_native_jobs'], 2)
            self.assertEqual(summary['local_context_conflicts'], 1)
            conflict = report['conflicts'][0]
            self.assertEqual({m['field'] for m in conflict['members']}, {'sample_material'})
            self.assertEqual({m['verdict'] for m in conflict['members']}, {'correct', 'incorrect'})
            self.assertTrue(all(consistency.sha(path) == expected for path, expected in hashes.items()))
            for origin in report['origins'].values():
                self.assertEqual(origin['native_origin']['actual_model'], 'synthetic-codex')
                self.assertTrue(origin['result_sha256'])
                self.assertTrue(origin['packet_sha256'])

    def test_changed_scientific_material_prevents_context_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary, _ = self.inspect(root, [job(root, 1), job(root, 2, verdict='incorrect', material='Plasma')])
            self.assertEqual(summary['local_context_conflicts'], 0)
            self.assertEqual(summary['repeated_local_context_groups'], 0)

    def test_internal_id_renaming_preserves_context_and_alignment_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary, _ = self.inspect(root, [job(root, 1), job(root, 2, rename=True)])
            self.assertGreater(summary['repeated_local_context_groups'], 0)
            self.assertEqual(summary['repeated_complete_input_alignment_groups'], 1)
            self.assertEqual(summary['local_context_conflicts'], 0)
            self.assertEqual(summary['alignment_conflicts'], 0)

    def test_actual_backend_model_is_part_of_the_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary, _ = self.inspect(root, [job(root, 1), job(root, 2, verdict='incorrect', actual_model='other-codex')])
            self.assertEqual(summary['repeated_local_context_groups'], 0)
            self.assertEqual(summary['local_context_conflicts'], 0)

    def test_same_complete_input_with_a_different_mapping_is_a_review_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary, report = self.inspect(root, [job(root, 1, two_samples=True),
                                                  job(root, 2, two_samples=True, swap_samples=True)])
            self.assertEqual(summary['repeated_complete_input_alignment_groups'], 1)
            self.assertEqual(summary['alignment_conflicts'], 1)
            self.assertTrue(any(g['kind'] == 'complete_input_alignment' for g in report['conflicts']))

    def test_shared_native_job_fanout_is_not_multiple_independent_judgments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); route = job(root, 1)
            summary, report = self.inspect(root, [route, {**route, 'condition': 'ssr'}])
            self.assertEqual(summary['inspected_native_jobs'], 1)
            self.assertEqual(summary['repeated_local_context_groups'], 0)
            self.assertEqual(len(next(iter(report['origins'].values()))['positions']), 2)

    def test_native_reply_integrity_is_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); route = job(root, 1)
            write(root / 'job-1/whole/attempt-001/reply.json', {'changed': True})
            with self.assertRaisesRegex(ValueError, 'matching native'):
                self.inspect(root, [route])


if __name__ == '__main__': unittest.main()
