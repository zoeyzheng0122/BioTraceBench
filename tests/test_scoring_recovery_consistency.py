"""Synthetic recovery, revision selection and repeated-decision regressions."""
import copy
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from biotracebench.submission import evaluable_json
from biotracebench_scoring.scoring_input import load_submission
from biotracebench_scoring.task_grading_contract import inventory, mark_all
from biotracebench_scoring.grading_consistency import (
    VERSION, checked_memory, context_identity, extend_memory, validate_decisions)
from biotracebench_scoring.grading_revision import eligible, selected_status
from model_conversation.archive import write, seal, sha, encoded, read, digest
import test_biotracebench_task_grading as f


class RecoveryTests(unittest.TestCase):
    def test_intact_prefix_keeps_original_precision_and_format_failure(self):
        text = '  {"database":{"sample":[{"value":1.2300}]},"annotations":[]} } \n'
        value, info = evaluable_json(text)
        self.assertEqual(value['database']['sample'][0]['value'].as_tuple(), Decimal('1.2300').as_tuple())
        self.assertFalse(info['strict_json_valid'])
        self.assertEqual(text[info['character_start']:info['character_end']], text.strip()[:-2])
        self.assertFalse(info['scientific_values_rewritten'])

    def test_ambiguous_or_duplicate_content_is_not_recovered(self):
        for text in ['{"x":1,"x":2}}', '{"x":NaN}}', '{"x":1}}}',
                     '{"x":1}{"x":2}', 'note {"x":1}}', '{"x":1} trailing',
                     '{"database":{"sample":[']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                evaluable_json(text)

    def test_archived_null_database_recovers_without_mutating_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            final = run/'SYN/ssr/final'
            write(final/'database.json', None)
            text = json.dumps({'database': f.GOLD, 'annotations': []})+'}'
            (final/'raw-answer.txt').write_text(text)
            write(final/'output-assessment.json', {'final_response_received': True})
            seal(final)
            before = {p.name: sha(p) for p in final.iterdir()}
            value, info = load_submission(run, 'SYN', 'ssr')
            self.assertEqual(value, f.GOLD)
            self.assertEqual(info['availability'], 'recovered_complete_object')
            self.assertEqual(before, {p.name: sha(p) for p in final.iterdir()})

    def test_terminal_structured_ambiguity_is_not_a_scientific_zero(self):
        for text in ['{"database":{},"database":{}}', '{"database":{"sample":[', '{}{}']:
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                run = Path(tmp); final = run/'SYN/ssr/final'
                write(final/'database.json', None)
                (final/'raw-answer.txt').write_text(text)
                write(final/'output-assessment.json', {'final_response_received': True})
                seal(final)
                value, info = load_submission(run, 'SYN', 'ssr')
                self.assertIsNone(value)
                self.assertEqual(info['availability'], 'unreadable_requires_review')
                self.assertIn('extraction_error', info)


class ConsistencyTests(unittest.TestCase):
    def fixture(self, accession='GEO:GSM1 (sample)', name='A', local_id='S1', extra=None):
        dictionary = copy.deepcopy(f.DICT)
        dictionary['sample']['fields'].append({'key': 'sample_accession'})
        gold = copy.deepcopy(f.GOLD)
        gold['sample'][0]['sample_accession'] = 'GEO:GSM1 (sample)'
        pred = copy.deepcopy(gold)
        pred['sample'][0].update(id=local_id, label=name, sample_accession=accession, **(extra or {}))
        inv = inventory(pred, gold, dictionary, f.POLICY)
        source = {'id': 'm1', 'source': 'synthetic.txt', 'locator': 'line 1',
                  'text': 'GSM1 and SRS1 identify the same synthetic sample.'}
        aliases = [{'table': 'sample', 'field': 'sample_accession',
            'values': [json.dumps(x) for x in ('GEO:GSM1 (sample)', 'GEO:GSM1 (sample); SRA:SRS1 (sample)')],
            'source_ids': ['m1']}]
        memory = {'version': VERSION, 'context_aliases': aliases, 'decisions': [], 'alignments': []}
        payload = {'inventory': inv, 'dictionary_json': encoded(dictionary).decode(),
                   'scoring_policy_json': encoded(f.POLICY).decode(), 'sources': [source],
                   'task_definition': 'Synthetic fixed task', 'consistency_memory': memory}
        packet = {'inventory': inv, 'request': {'payload': payload},
                  'consistency_scope': {'reference_sha256': 'synthetic-reference'}}
        result = mark_all(inv, f.reply_for(inv))
        result.update(grading_model='synthetic-judge', request_identity=digest(packet['request']),
                      score_binding=copy.deepcopy(packet['consistency_scope']))
        return packet, result

    def test_same_context_conflict_is_rejected_without_rewriting_reply(self):
        packet, result = self.fixture()
        memory = extend_memory(packet, result)
        other = copy.deepcopy(result)
        cell = next(c for c in other['cells'] if c['reference']['field'] == 'label')
        cell['verdict'] = 'incorrect'
        packet['request']['payload']['consistency_memory'] = memory
        before = copy.deepcopy(other)
        with self.assertRaisesRegex(ValueError, 'Inconsistent repeated'):
            validate_decisions(packet, other)
        self.assertEqual(before, other)

    def test_source_backed_accession_addition_normalizes_context_only(self):
        packet, result = self.fixture()
        memory = extend_memory(packet, result)
        other, marks = self.fixture('GEO:GSM1 (sample); SRA:SRS1 (sample)')
        self.assertEqual(context_identity(packet, result['records']), context_identity(other, marks['records']))
        other['request']['payload']['consistency_memory'] = memory
        # The different accession value is still a whole-cell model judgment.
        accession = next(c for c in marks['cells'] if c['reference']['field'] == 'sample_accession')
        self.assertEqual(accession['verdict'], 'incorrect')
        validate_decisions(other, marks)
        label = next(c for c in marks['cells'] if c['reference']['field'] == 'label')
        label['verdict'] = 'incorrect'
        with self.assertRaisesRegex(ValueError, 'Inconsistent repeated'):
            validate_decisions(other, marks)

    def test_changed_object_or_time_or_reference_does_not_reuse(self):
        packet, result = self.fixture()
        memory = extend_memory(packet, result)
        for other, marks in [self.fixture(name='B'), self.fixture(extra={'time': 'day 9'})]:
            other['request']['payload']['consistency_memory'] = memory
            self.assertNotEqual(context_identity(packet, result['records']), context_identity(other, marks['records']))
            validate_decisions(other, marks)
        other = copy.deepcopy(packet)
        other['consistency_scope']['reference_sha256'] = 'different-reference'
        self.assertNotEqual(context_identity(packet, result['records']), context_identity(other, result['records']))

    def test_internal_identifier_rename_keeps_context(self):
        packet, result = self.fixture()
        renamed, other = self.fixture(local_id='renamed')
        self.assertEqual(context_identity(packet, result['records']), context_identity(renamed, other['records']))

    def test_memory_requires_sources_and_actual_model_provenance(self):
        packet, result = self.fixture()
        memory = packet['request']['payload']['consistency_memory']
        with self.assertRaises(ValueError): checked_memory(memory, [])
        result.pop('request_identity')
        with self.assertRaises(ValueError): extend_memory(packet, result)

    def test_memory_cannot_hide_labels_or_normalize_numeric_fields(self):
        packet, result = self.fixture()
        memory = extend_memory(packet, result)
        memory['decisions'][0]['origin']['condition'] = 'synthetic-condition'
        with self.assertRaises(ValueError): checked_memory(memory, packet['request']['payload']['sources'])
        memory = copy.deepcopy(packet['request']['payload']['consistency_memory'])
        memory['context_aliases'][0]['field'] = 'value'
        with self.assertRaises(ValueError): checked_memory(memory, packet['request']['payload']['sources'])

    def test_association_ids_normalize_but_changed_target_does_not(self):
        dictionary = {'sample': {'identifier':'id','fields':[{'key':x} for x in ('id','label')]},
            'condition': {'identifier':'id','references':{'sample_id':'sample'},
                'fields':[{'key':x} for x in ('id','sample_id','time')]}}
        gold = {'sample':[{'id':'S1','label':'A'}],
                'condition':[{'id':'C1','sample_id':'S1','time':'day 1'}]}
        def build(pred):
            inv = inventory(pred,gold,dictionary,f.POLICY)
            packet = {'inventory':inv,'request':{'payload':{'inventory':inv,
                'dictionary_json':encoded(dictionary).decode(),'scoring_policy_json':'fixed',
                'task_definition':'fixed task','sources':[]}}}
            return context_identity(packet,f.reply_for(inv)['records'])
        renamed = {'sample':[{'id':'new','label':'A'}],
                   'condition':[{'id':'new-condition','sample_id':'new','time':'day 1'}]}
        self.assertEqual(build(gold),build(renamed))
        changed = copy.deepcopy(renamed)
        changed['condition'][0]['sample_id'] = 'absent'
        self.assertNotEqual(build(gold),build(changed))

    def test_uncertain_identity_never_shares_decisions(self):
        packet, result = self.fixture()
        reply = f.reply_for(packet['inventory'])
        reply['records'][0]['verdict'] = 'uncertain'
        for c in reply['cells']:
            if c['verdict'] in {'correct','incorrect'}: c['verdict'] = 'uncertain'
        result.update(mark_all(packet['inventory'],reply))
        self.assertEqual(extend_memory(packet, result)['decisions'], [])


class RevisionTests(unittest.TestCase):
    def test_success_with_same_gold_cannot_satisfy_required_new_revision(self):
        entry = {'status': 'automatic_scoring_completed', 'score_binding': {'reference_sha256': 'g'}}
        self.assertTrue(eligible(entry, 'g'))
        self.assertFalse(eligible(entry, 'g', 'repair-1'))
        self.assertEqual(selected_status(entry, 'g', 'repair-1'), 'superseded_scoring_revision')
        entry['score_binding']['scoring_revision'] = 'repair-1'
        self.assertTrue(eligible(entry, 'g', 'repair-1'))
        self.assertFalse(eligible(entry, 'changed', 'repair-1'))

    def test_prepare_binds_sources_memory_and_revision(self):
        from biotracebench_scoring import task_grading as grading
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f.WorkflowTests().fixture(root)
            sources = {'SYN': [{'id': 'm1', 'source': 'synthetic.txt', 'locator': 'line 1', 'text': 'A'}]}
            write(root/'sources.json', sources)
            write(root/'memory.json', {'SYN': {'version': VERSION, 'context_aliases': [], 'decisions': [], 'alignments': []}})
            grading.prepare(root/'submission', root/'gold', root/'policy.json', f.PROFILE,
                root/'budget.json', root/'new-plan', provisional=True, scoring_revision='repair-1',
                sources_path=root/'sources.json', consistency_path=root/'memory.json')
            plan = read(root/'new-plan/plan.json')
            binding = plan['entries'][0]['score_binding']
            self.assertEqual(binding['scoring_revision'], 'repair-1')
            self.assertIn('sources_identity', binding)
            self.assertIn('consistency_memory_identity', binding)
            self.assertEqual(plan['packets'][0]['request']['payload']['sources'], sources['SYN'])

    def test_live_protocol_rejects_conflict_keeps_reply_cost_and_first_score(self):
        from biotracebench_scoring import task_grading as grading
        from model_api import Backend
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root = Path(tmp)
            fixture = f.WorkflowTests()
            fixture.fixture(root,stages=('i0','gsr'))
            write(root/'memory.json',{'SYN':{'version':VERSION,'context_aliases':[],'decisions':[],'alignments':[]}})
            args = (root/'submission',root/'gold',root/'policy.json',f.PROFILE,root/'budget.json')
            grading.prepare(*args,root/'first-plan',provisional=True,selected_conditions=['i0'],
                            scoring_revision='repair-1',consistency_path=root/'memory.json')
            grading.execute(root/'first-plan',root/'first',backend=fixture.backend([]))
            packet = read(root/'first-plan/plan.json')['packets'][0]
            path = next((root/'first/tasks').glob('*/marking.json'))
            result = read(path)['result']; prior_sha = sha(path)
            memory = extend_memory(packet,result)
            write(root/'memory.json',{'SYN':memory})
            grading.prepare(*args,root/'second-plan',provisional=True,selected_conditions=['gsr'],
                            scoring_revision='repair-1',consistency_path=root/'memory.json')
            calls = []
            def sender(endpoint,wire,headers,timeout):
                calls.append(json.loads(wire))
                payload = json.loads(calls[-1]['messages'][1]['content'][0]['text'])['payload']
                self.assertEqual(payload['consistency_memory'],memory)
                reply = f.reply_for(payload['inventory'])
                item = next(c for c in reply['cells'] if c['verdict']=='correct')
                item['verdict'] = 'incorrect'
                return 200,{},json.dumps({'model':'qwen3.8-max-0902','id':'synthetic-conflict',
                    'usage':{'prompt_tokens':100,'completion_tokens':20},
                    'choices':[{'finish_reason':'stop','message':{'content':json.dumps(reply)}}]}).encode()
            status = grading.execute(root/'second-plan',root/'second',backend=Backend(f.PROFILE,sender=sender))
            entry = status['outputs'][0]
            self.assertEqual(entry['status'],'failed_grading_response')
            self.assertIn('Inconsistent repeated',entry['reason'])
            self.assertEqual(len(calls),1)
            self.assertEqual(sha(path),prior_sha)
            self.assertTrue((root/'second/tasks'/entry['id']/'raw-grading.txt').exists())
            self.assertGreater(Decimal(read(root/'second/costs.json')['total_upper_cny']),0)


if __name__ == '__main__':
    unittest.main()
