"""Synthetic regressions for mapping drift and unrelated-object edits."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from model_conversation.archive import digest, encoded, read, write, sha
from biotracebench_scoring.grading_context import Context
from biotracebench_scoring.grading_consistency import (
    VERSION, alignment_hint, checked_memory, context_identity, extend_memory, validate_decisions)
from biotracebench_scoring.task_grading_contract import inventory, mark_all
import test_biotracebench_task_grading as f


DICTIONARY = {
    'sample': {'identifier': 'id', 'fields': [{'key': k} for k in ('id', 'label', 'time', 'value')]},
    'condition': {'identifier': 'id', 'references': {'sample_id': 'sample'},
                  'fields': [{'key': k} for k in ('id', 'label', 'sample_id', 'dose')]},
    'result': {'identifier': 'id', 'references': {'sample_id': 'sample'},
               'fields': [{'key': k} for k in ('id', 'label', 'sample_id', 'outcome')]}}
GOLD = {'sample': [{'id': 'S1', 'label': 'A', 'time': 'day 1', 'value': 10},
                   {'id': 'S2', 'label': 'B', 'time': 'day 1', 'value': 20}],
        'condition': [{'id': 'C1', 'label': 'dose A', 'sample_id': 'S1', 'dose': 5},
                      {'id': 'C2', 'label': 'dose B', 'sample_id': 'S2', 'dose': 10}],
        'result': [{'id': 'R1', 'label': 'result A', 'sample_id': 'S1', 'outcome': 10},
                   {'id': 'R2', 'label': 'result B', 'sample_id': 'S2', 'outcome': 20}]}


def packet(prediction=None, gold=None, dictionary=None):
    dictionary = copy.deepcopy(dictionary or DICTIONARY)
    gold = copy.deepcopy(gold or GOLD)
    inv = inventory(copy.deepcopy(prediction or gold), gold, dictionary, f.POLICY)
    return {'inventory': inv, 'consistency_scope': {'reference_sha256': 'synthetic-fixed',
            'prompt_identity': 'synthetic-whole'}, 'request': {'payload': {
            'inventory': inv, 'dictionary_json': encoded(dictionary).decode(),
            'scoring_policy_json': encoded(f.POLICY).decode(), 'task_definition': 'Fixed synthetic task',
            'sources': [], 'consistency_memory': checked_memory(None, [])}}}


def marked(p, reply=None):
    result = mark_all(p['inventory'], reply or f.reply_for(p['inventory']))
    result.update(grading_model='synthetic-judge', request_identity=digest(p['request']),
                  score_binding=copy.deepcopy(p['consistency_scope']))
    return result


def attach(p, memory):
    p['request']['payload']['consistency_memory'] = copy.deepcopy(memory)
    hint = alignment_hint(p)
    if hint is not None:
        p['request']['payload']['frozen_record_alignment'] = hint


def flip(result, table, label, field):
    row = next(c['prediction']['row'] for c in result['cells'] if c.get('prediction')
               and c['prediction']['table'] == table and c['prediction']['field'] == 'label'
               and c['prediction']['value_json'] == json.dumps(label))
    cell = next(c for c in result['cells'] if c.get('prediction')
                and c['prediction']['row'] == row and c['prediction']['field'] == field)
    cell['verdict'] = 'incorrect'
    return cell


class ObjectContextTests(unittest.TestCase):
    def test_identical_input_cannot_escape_by_changing_record_mapping(self):
        p = packet(); memory = extend_memory(p, marked(p)); other = packet(); attach(other, memory)
        inv = other['inventory']; rows = {r['id']: r for r in inv['rows']}
        old = marked(other)['records']; first = old[0]
        pairs = [(rows[r['prediction_row']], rows[r['reference_row']]) for r in old[1:]]
        pairs += [(rows[first['prediction_row']], None), (None, rows[first['reference_row']])]
        changed = marked(other, f.reply_for(inv, pairs=pairs))
        self.assertEqual(Context(p).input_identity(), Context(other).input_identity())
        self.assertEqual(context_identity(other, marked(other)['records']),
                         context_identity(other, changed['records']))
        from biotracebench_scoring.task_grading_batches import check_pair_reply
        with self.assertRaisesRegex(ValueError, 'scientific record alignment'):
            check_pair_reply(inv, {'records': changed['records']}, packet=other)
        before = copy.deepcopy(changed)
        with self.assertRaisesRegex(ValueError, 'Inconsistent repeated scientific record alignment'):
            validate_decisions(other, changed)
        self.assertEqual(changed, before)

    def test_unrelated_object_edit_keeps_local_decision(self):
        p = packet(); memory = extend_memory(p, marked(p)); pred = copy.deepcopy(GOLD)
        pred['sample'][1]['value'] = 99
        pred['result'][1]['outcome'] = 99
        other = packet(pred); attach(other, memory)
        self.assertIsNone(alignment_hint(other))
        changed = marked(other); flip(changed, 'sample', 'A', 'time')
        with self.assertRaisesRegex(ValueError, 'Inconsistent repeated scientific judgment'):
            validate_decisions(other, changed)

    def test_changed_own_time_does_not_force_history(self):
        p = packet(); memory = extend_memory(p, marked(p)); pred = copy.deepcopy(GOLD)
        pred['sample'][0]['time'] = 'day 9'
        other = packet(pred); attach(other, memory); result = marked(other)
        flip(result, 'sample', 'A', 'label')
        validate_decisions(other, result)

    def test_changed_link_target_does_not_force_history(self):
        p = packet(); memory = extend_memory(p, marked(p)); pred = copy.deepcopy(GOLD)
        pred['result'][0]['sample_id'] = 'S2'
        other = packet(pred); attach(other, memory); result = marked(other)
        flip(result, 'result', 'result A', 'outcome')
        validate_decisions(other, result)

    def test_changed_related_condition_does_not_force_history(self):
        p = packet(); memory = extend_memory(p, marked(p)); pred = copy.deepcopy(GOLD)
        pred['condition'][0]['dose'] = 15
        other = packet(pred); attach(other, memory); result = marked(other)
        flip(result, 'sample', 'A', 'label')
        validate_decisions(other, result)

    def test_changed_relation_direction_does_not_force_history(self):
        dictionary = copy.deepcopy(DICTIONARY)
        dictionary['sample_relation'] = {'references': {'left': 'sample', 'right': 'sample'},
            'fields': [{'key': k} for k in ('left', 'right', 'relationship')]}
        gold = copy.deepcopy(GOLD)
        gold['sample_relation'] = [{'left': 'S1', 'right': 'S2', 'relationship': 'subset of'}]
        p = packet(gold=gold, dictionary=dictionary); memory = extend_memory(p, marked(p))
        pred = copy.deepcopy(gold); pred['sample_relation'][0]['relationship'] = 'superset of'
        other = packet(pred, gold, dictionary); attach(other, memory); result = marked(other)
        flip(result, 'sample', 'A', 'label')
        validate_decisions(other, result)

    def test_row_permutation_and_internal_id_rename_restore_actual_pairs(self):
        p = packet(); memory = extend_memory(p, marked(p)); pred = copy.deepcopy(GOLD)
        for rows in pred.values():
            for row in rows:
                row['id'] = 'renamed-' + row['id']
                if 'sample_id' in row:row['sample_id'] = 'renamed-' + row['sample_id']
            rows.reverse()
        other = packet(pred); attach(other, memory)
        self.assertEqual(Context(p).input_identity(), Context(other).input_identity())
        hint = other['request']['payload']['frozen_record_alignment']
        rows = {r['id']: r for r in other['inventory']['rows']}
        pairs = [(rows[r['prediction_row']], rows[r['reference_row']]) for r in hint['records']]
        reply = f.reply_for(other['inventory'], pairs=pairs, overrides={'sample_id': 'correct'})
        result = marked(other, reply)
        validate_decisions(other, result)
        self.assertEqual(result['field'], marked(p)['field'])
        self.assertEqual(result['record'], marked(p)['record'])
        # Association decisions use referents, not arbitrary ID spellings.
        flip(result, 'condition', 'dose A', 'sample_id')
        with self.assertRaisesRegex(ValueError, 'Inconsistent repeated scientific judgment'):
            validate_decisions(other, result)

    def test_scientific_uncertainty_cannot_evade_same_context_history(self):
        p = packet(); memory = extend_memory(p, marked(p)); other = packet(); attach(other, memory)
        reply = f.reply_for(other['inventory'])
        cell = next(c for c in reply['cells'] if c['verdict'] == 'correct')
        cell.update(verdict='uncertain')
        result = marked(other, reply)
        with self.assertRaisesRegex(ValueError, 'Inconsistent repeated scientific judgment'):
            validate_decisions(other, result)

    def test_undeclared_classification_cannot_evade_history(self):
        gold = copy.deepcopy(GOLD)
        gold['sample'][0]['undeclared_note'] = 'Same synthetic scientific assertion'
        p = packet(gold=gold); memory = extend_memory(p, marked(p))
        other = packet(gold=gold); attach(other, memory)
        reply = f.reply_for(other['inventory'])
        ids = {c['id'] for c in other['inventory']['cells']
               if c['field'] == 'undeclared_note' and c['side'] == 'prediction'}
        cell = next(c for c in reply['cells'] if c['prediction_cell'] in ids)
        cell.update(category='uncertain', verdict='uncertain')
        result = marked(other, reply)
        with self.assertRaisesRegex(ValueError, 'Inconsistent repeated scientific judgment'):
            validate_decisions(other, result)

    def test_indistinguishable_duplicate_objects_do_not_freeze_alignment(self):
        pred = copy.deepcopy(GOLD); pred['sample'].append({**pred['sample'][0], 'id': 'S3'})
        p = packet(pred); result = marked(p)
        self.assertIsNone(Context(p).input_identity())
        self.assertEqual(extend_memory(p, result)['alignments'], [])

    def test_cyclic_schema_does_not_claim_a_unique_complete_alignment(self):
        dictionary = copy.deepcopy(DICTIONARY)
        dictionary['sample']['references'] = {'parent': 'sample'}
        dictionary['sample']['fields'].append({'key': 'parent'})
        gold = copy.deepcopy(GOLD)
        gold['sample'][0]['parent'] = 'S2'; gold['sample'][1]['parent'] = 'S1'
        p = packet(gold=gold, dictionary=dictionary)
        self.assertIsNone(Context(p).input_identity())
        self.assertEqual(extend_memory(p, marked(p))['alignments'], [])

    def test_legacy_verdicts_are_not_silently_relabelled(self):
        legacy = {'version': 'biotracebench-context-decisions-1', 'context_aliases': [], 'decisions': []}
        self.assertEqual(checked_memory(legacy, [])['version'], VERSION)
        legacy['decisions'] = [{'verdict': 'correct'}]
        with self.assertRaisesRegex(ValueError, 'Legacy scientific decisions'):
            checked_memory(legacy, [])
        with self.assertRaisesRegex(ValueError, 'Invalid scientific consistency memory'):
            checked_memory({'version': VERSION, 'context_aliases': [], 'decisions': []}, [])

    def test_alignment_memory_cannot_hide_labels_scores_or_unknown_objects(self):
        p = packet(); memory = extend_memory(p, marked(p))
        other = copy.deepcopy(memory); other['alignments'][0]['origin']['condition'] = 'hidden'
        with self.assertRaises(ValueError):checked_memory(other, [])
        other = copy.deepcopy(memory); other['alignments'][0]['pairs'][0]['score'] = 1
        with self.assertRaises(ValueError):checked_memory(other, [])
        other = copy.deepcopy(memory); other['decisions'][0]['verdict'] = 'extra'
        with self.assertRaisesRegex(ValueError, 'fixed presence rules'):checked_memory(other, [])
        other = copy.deepcopy(memory); other['alignments'][0]['pairs'][0]['prediction_object'] = 'absent'
        p['request']['payload']['consistency_memory'] = checked_memory(other, [])
        with self.assertRaisesRegex(ValueError, 'absent'):
            alignment_hint(p)

    def test_staged_memory_retains_actual_phase_identity(self):
        from biotracebench_scoring.task_grading_batches import (
            PROTOCOL, pair_request, cell_request, batches, PAIR_INSTRUCTION, CELL_INSTRUCTION)
        p = packet(); result = marked(p)
        actual = [pair_request(p['request']), *[cell_request(p['request'], result['records'], b)
                   for b in batches(p['inventory'], result['records'])]]
        result.update(grading_method=PROTOCOL, request_identity=digest(actual))
        result['score_binding']['prompt_identity'] = digest({'records': PAIR_INSTRUCTION, 'cells': CELL_INSTRUCTION})
        memory = extend_memory(p, result, actual_requests=actual)
        self.assertEqual(memory['alignments'][0]['origin']['request_identity'], digest(actual))
        with self.assertRaisesRegex(ValueError, 'exact archived request'):
            extend_memory(p, result)
        tampered = copy.deepcopy(actual); tampered[-1]['payload']['sources'] = [{'fake': True}]
        with self.assertRaisesRegex(ValueError, 'exact actual phase requests'):
            extend_memory(p, result, actual_requests=tampered)

    def test_live_prepare_exposes_frozen_pairs_and_rejects_mapping_drift(self):
        from biotracebench_scoring import task_grading as grading
        from model_api import Backend
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'DASHSCOPE_API_KEY': 'synthetic-secret'}):
            root = Path(tmp); fixture = f.WorkflowTests(); fixture.fixture(root, stages=('i0', 'gsr'))
            write(root/'memory.json', {'SYN': checked_memory(None, [])})
            args = (root/'submission', root/'gold', root/'policy.json', f.PROFILE, root/'budget.json')
            grading.prepare(*args, root/'one-plan', provisional=True, selected_conditions=['i0'],
                            scoring_revision='object-2', consistency_path=root/'memory.json')
            grading.execute(root/'one-plan', root/'one', backend=fixture.backend([]))
            p = read(root/'one-plan/plan.json')['packets'][0]
            path = next((root/'one/tasks').glob('*/marking.json')); old_sha = sha(path)
            memory = extend_memory(p, read(path)['result']); write(root/'memory.json', {'SYN': memory})
            grading.prepare(*args, root/'two-plan', provisional=True, selected_conditions=['gsr'],
                            scoring_revision='object-2', consistency_path=root/'memory.json')
            prepared = read(root/'two-plan/plan.json')['packets'][0]
            self.assertIn('frozen_record_alignment', prepared['request']['payload'])
            calls = []
            def sender(endpoint, wire, headers, timeout):
                calls.append(json.loads(wire))
                payload = json.loads(calls[-1]['messages'][1]['content'][0]['text'])['payload']
                inv = payload['inventory']; rows = inv['rows']
                pr = next(r for r in rows if r['side'] == 'prediction')
                gr = next(r for r in rows if r['side'] == 'reference')
                reply = f.reply_for(inv, pairs=[(pr, None), (None, gr)])
                return 200, {}, json.dumps({'model': 'qwen3.8-max-0902', 'id': 'synthetic-drift',
                    'usage': {'prompt_tokens': 100, 'completion_tokens': 20},
                    'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(reply)}}]}).encode()
            result = grading.execute(root/'two-plan', root/'two', backend=Backend(f.PROFILE, sender=sender))
            self.assertEqual(result['outputs'][0]['status'], 'failed_grading_response')
            self.assertIn('scientific record alignment', result['outputs'][0]['reason'])
            self.assertEqual(sha(path), old_sha)
            self.assertEqual(len(calls), 1)
            self.assertTrue((root/'two/costs.json').exists())


if __name__ == '__main__':
    unittest.main()
