"""Evidence-contract regressions with explicit scientific correspondences."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from model_conversation.archive import digest, write, read
from biotracebench_scoring import efe_protocol as efe
from biotracebench_scoring.task_grading_contract import inventory, mark_all
from test_biotracebench_task_grading import reply_for

SPEC = {'population': {'identifier': 'id', 'fields': [
    {'key': k} for k in ('id', 'population_name', 'population_definition', 'population_size')]}}
POLICY = {'reference_contract': 'biotracebench-fixed-reference-1', 'field_roles': {}}
PROTOCOL = {'contract': efe.CONTRACT, 'rules': efe.RULES,
            'association_semantics': 'Use the source-supported result-producing population.'}
GOLD = {'population': [{'id': 'P1', 'population_name': 'Arm A',
                        'population_definition': 'Response-evaluable Arm A', 'population_size': 49}]}
SOURCES = [{'id': 's1', 'source': 'synthetic.txt', 'locator': 'paragraph 1',
            'text': 'Arm A has 49 response-evaluable participants.'}]


def enriched(inv, pairs=None):
    reply = reply_for(inv, pairs=pairs)
    for r in reply['records']:
        v = r['verdict']
        support = [c['id'] for c in inv['cells'] if c['row'] in {
            r['prediction_row'], r['reference_row']} and c['field'] == 'population_definition']
        r['identity_basis'] = {
            'rule_id': 'context_identity' if v == 'matched' else 'merged_or_missing' if v == 'missing' else 'surplus_or_nonmatch',
            'resolution': {'matched': 'same_object', 'missing': 'not_submitted', 'extra': 'surplus_prediction'}[v],
            'supporting_cells': support if v == 'matched' else [], 'source_evidence': [], 'conflicts': []}
    return reply


class EFEProtocolTests(unittest.TestCase):
    def fixture(self, pred=None, gold=None):
        inv = inventory(pred or GOLD, gold or GOLD, SPEC, POLICY)
        return inv, enriched(inv)

    def test_new_evidence_preserves_explicit_counts(self):
        inv, reply = self.fixture()
        result = efe.mark(inv, reply, PROTOCOL, SOURCES)
        self.assertEqual(result['field']['tp'], 3)
        self.assertEqual(result['record']['tp'], 1)
        self.assertEqual(result['alignment_protocol'], efe.CONTRACT)
        self.assertEqual(result['alignment_binding']['inventory_identity'], digest(inv))
        self.assertNotIn('identity_basis', result['records'][0])
        self.assertEqual(result['alignment_audit'][0]['rule_id'], 'context_identity')

    def test_old_reply_remains_valid_only_under_old_contract(self):
        inv, _ = self.fixture()
        reply = reply_for(inv)
        self.assertEqual(mark_all(inv, reply)['field']['tp'], 3)
        with self.assertRaisesRegex(ValueError, 'identity basis'):
            efe.mark(inv, reply, PROTOCOL, SOURCES)

    def test_support_cannot_use_local_ids_outcomes_or_other_rows(self):
        inv, original = self.fixture()
        for field in ['id', 'population_size']:
            reply = copy.deepcopy(original)
            reply['records'][0]['identity_basis']['supporting_cells'] = [
                c['id'] for c in inv['cells'] if c['field'] == field]
            with self.assertRaisesRegex(ValueError, 'non-outcome scientific'):
                efe.mark(inv, reply, PROTOCOL, SOURCES)
        reply = copy.deepcopy(original)
        reply['records'][0]['identity_basis']['supporting_cells'] = ['not-a-cell']
        with self.assertRaises(ValueError): efe.mark(inv, reply, PROTOCOL, SOURCES)

    def test_one_sided_evidence_cannot_establish_a_match(self):
        inv, reply = self.fixture()
        reply['records'][0]['identity_basis']['supporting_cells'].pop()
        with self.assertRaisesRegex(ValueError, 'both rows'):
            efe.mark(inv, reply, PROTOCOL, SOURCES)

    def test_attribute_error_keeps_identity_and_costs_field_and_record(self):
        pred = copy.deepcopy(GOLD); pred['population'][0]['population_size'] = 60
        inv, reply = self.fixture(pred)
        basis = reply['records'][0]['identity_basis']
        basis.update(rule_id='attribute_error', source_evidence=['s1'], conflicts=[{
            'field': 'population_size', 'handling': 'attribute_error',
            'reason': 'The independently identified evaluable arm has an incorrect count.'}])
        result = efe.mark(inv, reply, PROTOCOL, SOURCES)
        self.assertEqual(result['field']['tp'], 2)
        self.assertEqual(result['record']['tp'], 0)
        basis['conflicts'][0]['handling'] = 'identity_conflict'
        with self.assertRaisesRegex(ValueError, 'identity conflict'):
            efe.mark(inv, reply, PROTOCOL, SOURCES)

    def test_source_conflict_and_equivalent_objects_need_supplied_evidence(self):
        inv, reply = self.fixture()
        b = reply['records'][0]['identity_basis']
        b.update(rule_id='equivalent_objects', resolution='equivalent_objects')
        with self.assertRaisesRegex(ValueError, 'source evidence'):
            efe.mark(inv, reply, PROTOCOL, SOURCES)
        b['source_evidence'] = ['invented']
        with self.assertRaisesRegex(ValueError, 'supplied frozen'):
            efe.mark(inv, reply, PROTOCOL, SOURCES)
        b['source_evidence'] = ['s1']
        self.assertEqual(efe.mark(inv, reply, PROTOCOL, SOURCES)['record']['tp'], 1)

    def test_merged_record_cannot_match_two_references(self):
        gold = copy.deepcopy(GOLD); gold['population'].append({**gold['population'][0], 'id': 'P2',
            'population_name': 'Arm B', 'population_definition': 'Response-evaluable Arm B'})
        inv = inventory(GOLD, gold, SPEC, POLICY)
        sides = {s: [r for r in inv['rows'] if r['side'] == s] for s in ['prediction', 'reference']}
        reply = enriched(inv, [(sides['prediction'][0], sides['reference'][0]), (None, sides['reference'][1])])
        result = efe.mark(inv, reply, PROTOCOL, SOURCES)
        self.assertEqual((result['record']['predicted'], result['record']['gold'], result['record']['tp']), (1, 2, 1))
        reply['records'][1]['prediction_row'] = sides['prediction'][0]['id']
        reply['records'][1]['verdict'] = 'matched'
        reply['records'][1]['identity_basis'] = copy.deepcopy(reply['records'][0]['identity_basis'])
        with self.assertRaises(ValueError): efe.mark(inv, reply, PROTOCOL, SOURCES)

    def test_unresolved_identity_retains_denominators_and_no_match_credit(self):
        inv, reply = self.fixture()
        r = reply['records'][0]; r['verdict'] = 'uncertain'
        r['identity_basis'].update(rule_id='unresolved', resolution='unresolved')
        for c in reply['cells']:
            if c['category'] == 'scientific': c['verdict'] = 'uncertain'
        result = efe.mark(inv, reply, PROTOCOL, SOURCES)
        self.assertEqual(result['field']['gold'], 3)
        self.assertEqual(result['field']['predicted'], 3)
        self.assertEqual(result['field']['tp'], 0)
        self.assertEqual(result['score_basis'], 'lower_bound_unresolved')

    def test_terminal_empty_answer_needs_no_judge_or_identity_invention(self):
        inv = inventory(None, GOLD, SPEC, POLICY)
        result = efe.terminal(inv, PROTOCOL, SOURCES)
        self.assertEqual(result['field']['tp'], 0)
        self.assertEqual(result['field']['gold'], 3)
        self.assertEqual(result['score_basis'], 'terminal_no_usable_output')

    def test_review_binds_prior_and_preserves_original(self):
        inv, reply = self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'inputs').mkdir()
            bundle = {'inventory': inv, 'alignment_definition': PROTOCOL, 'sources': SOURCES, 'reply': reply}
            write(root/'inputs/bundle.json', bundle)
            revision = {'prior_bundle_identity': digest(bundle), 'reviewer': 'Synthetic reviewer',
                        'reviewer_type': 'human', 'basis': 'Synthetic source check.', 'reply': reply}
            write(root/'inputs/review.json', revision)
            result = efe.review(root/'inputs/bundle.json', root/'inputs/review.json', root/'out')
            self.assertEqual(result['unresolved_items'], 0)
            self.assertEqual(read(root/'out/prior.json'), bundle)
            revision['prior_bundle_identity'] = 'wrong'
            write(root/'inputs/review.json', revision)
            with self.assertRaisesRegex(ValueError, 'bind the original'):
                efe.review(root/'inputs/bundle.json', root/'inputs/review.json', root/'other')

    def test_declared_attribute_error_cannot_receive_correct_credit(self):
        inv, reply = self.fixture()
        reply['records'][0]['identity_basis'].update(source_evidence=['s1'], conflicts=[{
            'field': 'population_size', 'handling': 'attribute_error', 'reason': 'Synthetic discrepancy.'}])
        with self.assertRaisesRegex(ValueError, 'correct field credit'):
            efe.mark(inv, reply, PROTOCOL, SOURCES)

    def test_new_preparation_execution_export_and_offline_review(self):
        from test_biotracebench_task_grading import WorkflowTests, PROFILE
        from biotracebench_scoring import task_grading as grading
        from model_api import Backend
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'DASHSCOPE_API_KEY': 'synthetic-secret'}):
            root = Path(tmp); WorkflowTests().fixture(root)
            write(root/'alignment.json', PROTOCOL)
            grading.prepare(root/'submission', root/'gold', root/'policy.json', PROFILE,
                            root/'budget.json', root/'new-plan', provisional=True,
                            alignment_path=root/'alignment.json')
            packet = read(root/'new-plan/plan.json')['packets'][0]
            self.assertEqual(packet['request']['payload']['alignment_definition'], PROTOCOL)
            self.assertIn('identity_basis', packet['request']['response_schema']['properties']['records']['items']['required'])
            calls = []
            def sender(endpoint, body, headers, timeout):
                calls.append(json.loads(body))
                inv = json.loads(calls[-1]['messages'][1]['content'][0]['text'])['payload']['inventory']
                reply = reply_for(inv)
                for r in reply['records']:
                    r['identity_basis'] = {'rule_id': 'context_identity', 'resolution': 'same_object',
                        'supporting_cells': [c['id'] for c in inv['cells'] if c['field'] == 'label'],
                        'source_evidence': [], 'conflicts': []}
                response = {'model': 'qwen3.8-max-0902', 'id': 'synthetic-request',
                    'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(reply)}}],
                    'usage': {'prompt_tokens': 100, 'completion_tokens': 20}}
                return 200, {}, json.dumps(response).encode()
            state = grading.execute(root/'new-plan', root/'run', backend=Backend(PROFILE, sender=sender))
            self.assertEqual(state['graded_outputs'], 1)
            folder = root/'run/tasks'/state['outputs'][0]['id']
            bundle = read(folder/'protocol-bundle.json')
            replay = efe.mark(bundle['inventory'], bundle['reply'], bundle['alignment_definition'], bundle['sources'])
            self.assertEqual(replay['field']['tp'], 2)
            self.assertEqual(replay['record']['tp'], 1)
            self.assertIn('EFE identity evidence', (folder/'review.html').read_text())
            recovered = grading.execute(root/'new-plan', root/'run', offline=True)
            self.assertEqual(recovered['graded_outputs'], 1)
            self.assertEqual(len(calls), 1)


if __name__ == '__main__': unittest.main()
