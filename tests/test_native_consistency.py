"""Exact repeated native contexts; synthetic judgments, no scientific oracle."""
import copy
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from model_conversation.archive import read, sha, write
from biotracebench_scoring import native_codex as native, native_consistency as consistency
from biotracebench_scoring.logical_contract import bind_policy, policy_template, scaffold_policy
from biotracebench_scoring.task_grading_contract import inventory


DICT = {
    'sample': {'identifier': 'id', 'fields': [{'key': k} for k in ('id', 'name', 'time', 'method')]},
    'result': {'identifier': 'id', 'references': {'sample_id': 'sample'},
               'fields': [{'key': k} for k in ('id', 'sample_id', 'value')]}}
PHYSICAL = {'reference_contract': 'biotracebench-fixed-reference-1', 'field_roles': {}}
GOLD = {'sample': [{'id': 'SA', 'name': 'Arm A', 'time': 'week 6', 'method': 'ANCOVA'},
                   {'id': 'SB', 'name': 'Arm B', 'time': 'week 6', 'method': 'ANCOVA'}],
        'result': [{'id': 'RA', 'sample_id': 'SA', 'value': 5},
                   {'id': 'RB', 'sample_id': 'SB', 'value': 6}]}
ACTOR = {'kind': 'native_codex', 'agent_id': '/root/synthetic-consistency'}


def authored_policy():
    inv = inventory({}, GOLD, DICT, PHYSICAL)
    result = scaffold_policy(inv)
    for field in result['fields']:
        for assertion in field['required_assertions']:
            assertion.update(text='Recover this synthetic task fact: ' + field['field'],
                             placement='strict', basis='The synthetic task explicitly assigns this field.')
    return policy_template(bind_policy(result, inv), inv)


def prediction(renamed=False, permuted=False):
    value = copy.deepcopy(GOLD)
    if renamed:
        for index, item in enumerate(value['sample']): item['id'] = 'new-sample-' + str(index)
        for index, item in enumerate(value['result']):
            item['id'] = 'new-result-' + str(index)
            item['sample_id'] = value['sample'][index]['id']
    if permuted:
        value['sample'].reverse(); value['result'].reverse()
    # Explicit fixture mapping, supplied before field assertions are authored.
    mapping = {table: list(reversed(range(2))) if permuted else list(range(2)) for table in DICT}
    return value, mapping


def native_reply(inv, template, mapping, bad=None):
    by_row = {r['id']: r for r in inv['rows']}
    cells = {(c['row'], c['field']): c for c in inv['cells']}
    refs = {(r['table'], r['row_index']): r['id'] for r in inv['rows'] if r['side'] == 'reference'}
    records, mapped = [], {}
    for r in inv['rows']:
        if r['side'] != 'prediction': continue
        indices = mapping.get(r['table'], [])
        target = indices[r['row_index']] if r['row_index'] < len(indices) else None
        ref = refs[(r['table'], target)] if target is not None else None
        records.append({'prediction_row': r['id'], 'reference_row': ref,
                        'verdict': 'matched' if ref else 'extra',
                        'reason': 'Explicit synthetic scientific correspondence, independently supplied.'})
        if ref: mapped[ref] = r['id']
    for ref in refs.values():
        if ref not in mapped:
            records.append({'prediction_row': None, 'reference_row': ref, 'verdict': 'missing',
                            'reason': 'No corresponding submitted synthetic object.'})
    fields = []
    for spec in bind_policy(template, inv)['fields']:
        p = mapped.get(spec['reference_row']); c = cells.get((p, spec['field']))
        val = json.loads(c['value_json']) if c else None
        ev = [{'cell': c['id'], 'path': '', 'quote': val if isinstance(val, str) else None}] if c and c['nonempty'] else []
        state = 'incorrect' if spec['id'] == bad else 'correct' if ev else 'missing'
        fields.append({'field_id': spec['id'], 'prediction_evidence': ev,
                       'assertions': [{'assertion_id': a['id'], 'verdict': state, 'evidence': ev,
                                       'reason': 'Explicit fixture native assertion judgment.'}
                                      for a in spec['required_assertions']],
                       'integrity': {'verdict': 'correct', 'evidence': [],
                                     'reason': 'Fixture judges no erroneous added assertion.'},
                       'verdict': state if spec['required_assertions'] else 'not_scored',
                       'reason': 'Explicit fixture native whole-field judgment.'})
    links = []
    for rid, r in by_row.items():
        if r['side'] != 'prediction' or r['table'] != 'result': continue
        source = cells[rid, 'sample_id']; sid = json.loads(source['value_json'])
        target = next(c for c in inv['cells'] if c['side'] == 'prediction' and c['table'] == 'sample'
                      and c['field'] == 'id' and json.loads(c['value_json']) == sid)
        links.append({'id': 'link-' + rid, 'from_row': rid, 'to_row': target['row'], 'kind': 'identifier',
                      'from_evidence': {'cell': source['id'], 'path': '', 'quote': sid},
                      'to_evidence': {'cell': target['id'], 'path': '', 'quote': sid},
                      'reason': 'Actual submitted sample identifier establishes this fixture relationship.'})
    return {'records': records, 'fields': fields, 'links': links, 'unscored': [], 'reference_issues': []}


def campaign(root, variants, *, finish=True, first_bad=None, final_bad=None, staged=False):
    archive = root / 'archive'; archive.mkdir()
    positions, files, inputs = [], {}, []
    template = authored_policy()
    for number, (pred, mapping) in enumerate(variants):
        inv = inventory(pred, GOLD, DICT, PHYSICAL)
        name = f'packet-{number}.json.gz'; path = archive / name
        path.write_bytes(gzip.compress(json.dumps({'inventory': inv}).encode()))
        files[name] = sha(path)
        positions.append({'case': 'SYNTHETIC', 'model': 'PRIVATE_MODEL_ROUTE_' + str(number),
                          'condition': 'i0', 'domain': 'synthetic', 'judgment': name, 'zero_cause': None})
        inputs.append((inv, mapping))
    write(archive / 'manifest.json', {'positions': positions, 'files': files})
    write(root / 'contexts.json', {'SYNTHETIC': {'task_definition': 'Recover both arms at week 6 using ANCOVA.',
          'dictionary': DICT, 'policy': PHYSICAL, 'task_policy': template,
          'sources': [{'id': 'synthetic-source', 'text': 'Synthetic arm definitions, values and method.'}]}})
    native.prepare_native(archive / 'manifest.json', root / 'contexts.json', root / 'plan')
    jobs = read(root / 'plan/plan.json')['jobs']
    for index, (job, (inv, mapping)) in enumerate(zip(jobs, inputs)):
        if not finish: continue
        for phase in ('first', 'review'):
            bad = (first_bad or {}).get(index) if phase == 'first' else (final_bad or {}).get(index)
            ans = native_reply(inv, template, mapping, bad)
            if staged:
                receipt = native.ingest_native(root / 'plan', job, {'records': ans['records']}, ACTOR,
                                                phase=phase, scope='records')
                ans = {k: v for k, v in ans.items() if k != 'records'}
                result = native.ingest_native(root / 'plan', job, ans, ACTOR, phase=phase, scope='fields',
                                               mapping_identity=receipt['record_mapping_identity'])
            else:
                result = native.ingest_native(root / 'plan', job, ans, ACTOR, phase=phase)
            if result['status'] != 'accepted': raise AssertionError(result)
    return template, inputs, jobs


class NativeConsistencyTests(unittest.TestCase):
    def test_id_renaming_and_row_permutation_reveal_conflicting_native_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            campaign(root, [prediction(), prediction(True, True)], final_bad={1: 'sample:0:method'})
            report = consistency.inspect(root / 'plan')
            self.assertEqual(report['inspected_jobs'], 2)
            conflict = next(g for g in report['conflicts'] if g['kind'] == 'logical_field')
            self.assertEqual(conflict['members'][0]['target'], {'table': 'sample', 'row_index': 0, 'field': 'method'})
            self.assertEqual({m['job_id'] for m in conflict['members']}, {'n-00001', 'n-00002'})
            self.assertGreater(report['repeated_context_groups'], 0)
            self.assertIn('submission', report['contexts'][conflict['context_identity']])

    def test_different_time_or_method_never_enters_same_exact_context_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); later = prediction(True); later[0]['sample'][0]['time'] = 'week 12'
            method = prediction(True, True); method[0]['sample'][0]['method'] = 'mixed effects model'
            campaign(root, [prediction(), later, method],
                     final_bad={1: 'sample:0:time', 2: 'sample:1:method'})
            report = consistency.inspect(root / 'plan')
            self.assertEqual(report['groups'], [])
            self.assertEqual(report['conflict_groups'], 0)

    def test_wrong_actual_foreign_key_is_preserved_in_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); wrong = prediction(True)
            wrong[0]['result'][0]['sample_id'] = wrong[0]['sample'][1]['id']
            campaign(root, [prediction(), wrong], final_bad={1: 'result:0:sample_id'})
            self.assertEqual(consistency.inspect(root / 'plan')['groups'], [])

    def test_first_and_review_are_separate_and_only_final_is_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            campaign(root, [prediction(), prediction(True, True)], first_bad={1: 'sample:0:method'})
            final = consistency.inspect(root / 'plan')
            first = consistency.inspect(root / 'plan', phase='first')
            review = consistency.inspect(root / 'plan', phase='review')
            self.assertEqual(final['conflict_groups'], 0)
            self.assertEqual(review['conflict_groups'], 0)
            self.assertGreater(first['conflict_groups'], 0)
            self.assertEqual({v['phase'] for v in final['origins'].values()}, {'review'})
            self.assertEqual({v['phase'] for v in first['origins'].values()}, {'first'})

    def test_staged_imports_reconstruct_only_their_frozen_record_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); campaign(root, [prediction(), prediction(True, True)], staged=True)
            report = consistency.inspect(root / 'plan')
            self.assertGreater(report['repeated_context_groups'], 0)
            self.assertEqual(report['conflict_groups'], 0)

    def test_completed_replay_index_is_verified_without_private_route_or_label_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); campaign(root, [prediction(), prediction(True, True)])
            replay = native.replay_native(root / 'plan', root / 'replay')
            original = Path.read_text
            forbidden = (root / 'plan/private/routes.json').resolve()
            opened = []
            def guarded(path, *args, **kwargs):
                if path.resolve() == forbidden: raise AssertionError('Private model routes must not be read')
                opened.append(str(path))
                return original(path, *args, **kwargs)
            with patch.object(Path, 'read_text', guarded), \
                    patch('subprocess.Popen', side_effect=AssertionError('No judge process')), \
                    patch('socket.socket', side_effect=AssertionError('No judge network')):
                report = consistency.inspect(replay['index_path'], root / 'consistency.json')
            self.assertEqual(report['conflict_groups'], 0)
            self.assertNotIn('PRIVATE_MODEL', json.dumps(report))
            self.assertNotIn(str(forbidden), opened)
            self.assertEqual(read(root / 'consistency.json')['format'], consistency.FORMAT)

    def test_report_never_adjudicates_or_mutates_native_judgments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); campaign(root, [prediction(), prediction(True)], final_bad={1: 'sample:0:method'})
            before = {str(p): p.read_bytes() for p in (root / 'plan').rglob('*.json')}
            report = consistency.inspect(root / 'plan', root / 'report.json')
            self.assertGreater(report['conflict_groups'], 0)
            self.assertEqual(before, {str(p): p.read_bytes() for p in (root / 'plan').rglob('*.json')})
            self.assertNotIn('preferred', json.dumps(report))
            self.assertIn('No judgment', report['action'])

    def test_missing_phase_and_invalid_or_unresolved_imports_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); template, inputs, jobs = campaign(root, [prediction()], finish=False)
            inv, mapping = inputs[0]; ans = native_reply(inv, template, mapping)
            native.ingest_native(root / 'plan', jobs[0], ans, ACTOR, phase='first')
            with self.assertRaisesRegex(ValueError, 'accepted complete final'): consistency.inspect(root / 'plan')
            invalid = copy.deepcopy(ans); invalid['fields'][0]['verdict'] = 'uncertain'
            rejected = native.ingest_native(root / 'plan', jobs[0], invalid, ACTOR, phase='review')
            self.assertEqual(rejected['status'], 'validation_error')
            with self.assertRaisesRegex(ValueError, 'accepted complete final'): consistency.inspect(root / 'plan')
            receipt = next((root / 'plan/imports' / jobs[0]).glob('00001.json'))
            data = read(receipt); data['score']['unresolved_items'] = 1; write(receipt, data)
            with self.assertRaisesRegex(ValueError, 'identity mismatch'): consistency.inspect(root / 'plan', phase='first')

    def test_tampered_snapshot_and_missing_input_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); campaign(root, [prediction()])
            replay = native.replay_native(root / 'plan', root / 'replay')
            path = Path(replay['index_path']); data = read(path); data['snapshot_identity'] = 'tampered'; write(path, data)
            with self.assertRaisesRegex(ValueError, 'snapshot'): consistency.inspect(path)
            (root / 'plan/judge-inputs/jobs/n-00001/packet.json').unlink()
            with self.assertRaises((FileNotFoundError, ValueError)): consistency.inspect(root / 'plan')

    def test_unmatched_extra_ids_are_not_arbitrarily_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); a, b = prediction(), prediction(True, True)
            a[0]['sample'].append({'id': 'extra-A', 'name': 'surplus', 'time': 'week 6', 'method': 'ANCOVA'})
            b[0]['sample'].append({'id': 'extra-B', 'name': 'surplus', 'time': 'week 6', 'method': 'ANCOVA'})
            campaign(root, [a, b])
            report = consistency.inspect(root / 'plan')
            self.assertEqual(report['groups'], [])
            self.assertIn('Unmatched objects', report['limitations'][2])


if __name__ == '__main__':
    unittest.main()
