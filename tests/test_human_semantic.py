"""Rubric scope, frozen evidence and counting regressions; no provider calls.

SCIENTIFIC_CASES are synthetic model-acceptance inputs. The offline tests below
validate explicit fixture judgments and never claim to establish model accuracy.
"""
import copy
import json
import unittest
from pathlib import Path

from biotracebench_scoring import human_semantic as semantic
from biotracebench_scoring.task_grading_contract import PROMPT, inventory, mark_all
from test_biotracebench_task_grading import reply_for

POLICY = {'reference_contract': 'biotracebench-fixed-reference-1', 'field_roles': {}}
DICT = {'result': {'identifier': 'id', 'fields': [
    {'key': 'id'}, {'key': 'analysis', 'description': 'The selected analysis identity.'},
    {'key': 'statistical_method', 'description': 'Analysis method and missing-data handling.'},
    {'key': 'notes', 'description': 'Optional descriptive notes.'}]}}
TASK = 'Recover the Regimen Group analysis. In statistical_method report ANCOVA and MICE imputation; do not require an effect-size formula.'
SOURCES = [{'id': 'methods', 'source': 'synthetic.txt', 'locator': 'Methods',
            'text': 'The Regimen Group analysis used ANCOVA and MICE. No effect-size formula is reported. Dose Group is a different selected analysis.'}]
BASE = {'id': 'R1', 'analysis': 'Regimen Group',
        'statistical_method': 'ANCOVA with MICE imputation; effect-size formula not separately specified.',
        'notes': None}


SCIENTIFIC_CASES = [
    {'name': 'equivalent_wording',
     'prediction': {**BASE, 'statistical_method': 'Analysis of covariance with multiple imputation by chained equations.'},
     'expected_method': 'correct', 'reason': 'Expanded names preserve both required methods.'},
    {'name': 'reference_explanation_optional',
     'prediction': {**BASE, 'statistical_method': 'ANCOVA with MICE imputation.'},
     'expected_method': 'correct', 'reason': 'The task requires the methods, without requiring a sentence about an unreported formula.'},
    {'name': 'required_imputation_omitted',
     'prediction': {**BASE, 'statistical_method': 'ANCOVA.'},
     'expected_method': 'incorrect', 'reason': 'The field omits the task-required MICE handling.'},
    {'name': 'no_cross_field_completion',
     'prediction': {**BASE, 'statistical_method': 'ANCOVA.', 'notes': 'MICE imputation was used.'},
     'expected_method': 'incorrect', 'reason': 'Notes do not supply required content within statistical_method.'},
    {'name': 'unsupported_added_formula',
     'prediction': {**BASE, 'statistical_method': 'ANCOVA with MICE imputation and a Cohen d formula.'},
     'expected_method': 'incorrect', 'reason': 'The definite extra formula lacks source support.'},
    {'name': 'different_requested_analysis',
     'prediction': {**BASE, 'analysis': 'Dose Group'},
     'expected_mapping': 'nonmatch', 'reason': 'Dose Group denotes a different requested analysis even if numbers or methods agree.'},
]


def acceptance_cases():
    """Complete cases that a real CLI pilot can send without expected labels."""
    return [{**copy.deepcopy(case), 'dictionary': copy.deepcopy(DICT),
             'policy': copy.deepcopy(POLICY), 'task_definition': TASK,
             'sources': copy.deepcopy(SOURCES),
             'reference': {'result': [copy.deepcopy(BASE)]},
             'prediction': {'result': [copy.deepcopy(case['prediction'])]}}
            for case in SCIENTIFIC_CASES]


class HumanSemanticTests(unittest.TestCase):
    def setUp(self):
        self.rubric = semantic.build_rubric(TASK, DICT, SOURCES, policy=POLICY)

    def test_opt_in_definition_matches_public_config(self):
        path = Path(__file__).resolve().parents[1] / 'configs/tasks/biotracebench-human-semantic-v1.json'
        self.assertEqual(json.loads(path.read_text()), semantic.definition())
        self.assertEqual(semantic.validate_definition(semantic.definition()), semantic.definition())
        changed = semantic.definition(); changed['field_locality'] = 'cross_field'
        with self.assertRaises(ValueError): semantic.validate_definition(changed)
        self.assertNotIn(semantic.CONTRACT, PROMPT)

    def test_every_field_retains_exact_dictionary_definition_and_role(self):
        self.assertEqual(len(self.rubric['fields']), 4)
        identifier = next(f for f in self.rubric['fields'] if f['field'] == 'id')
        self.assertEqual(identifier['declared_role'], 'identifier')
        method = next(f for f in self.rubric['fields'] if f['field'] == 'statistical_method')
        self.assertEqual(method['dictionary_definition'], DICT['result']['fields'][2])
        self.assertEqual(method['field_locality'], 'strict')
        self.assertEqual(method['source_ids'], ['methods'])

    def test_mutated_task_dictionary_or_sources_fail_before_judging(self):
        variants = []
        wrong_task = copy.deepcopy(self.rubric); wrong_task['task_definition'] += ' Changed scope.'; variants.append(wrong_task)
        wrong_field = copy.deepcopy(self.rubric); wrong_field['fields'][2]['dictionary_definition']['description'] = 'Loose method.'; variants.append(wrong_field)
        wrong_source = copy.deepcopy(self.rubric); wrong_source['fields'][2]['source_ids'] = ['invented']; variants.append(wrong_source)
        incomplete = copy.deepcopy(self.rubric); incomplete['fields'].pop(); variants.append(incomplete)
        duplicate = copy.deepcopy(self.rubric); duplicate['fields'].append(copy.deepcopy(duplicate['fields'][0])); variants.append(duplicate)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(ValueError):
                semantic.validate_rubric(value, DICT, SOURCES, policy=POLICY)

    def test_semantic_contract_does_not_change_fixed_presence_or_counts(self):
        for case in acceptance_cases():
            if case.get('expected_mapping'): continue
            with self.subTest(case=case['name']):
                inv = inventory(case['prediction'], case['reference'], DICT, POLICY)
                reply = reply_for(inv, overrides={'statistical_method': case['expected_method']})
                result = mark_all(inv, reply)
                self.assertEqual(result['field']['gold'], 2)
                self.assertEqual(result['field']['tp'], 2 if case['expected_method'] == 'correct' else 1)
                self.assertEqual(result['record']['tp'], int(case['expected_method'] == 'correct'))
                if case['name'] == 'no_cross_field_completion':
                    self.assertEqual(result['field']['predicted'], 3)

    def test_different_analysis_is_missing_and_surplus_under_shared_mapping(self):
        case = next(c for c in acceptance_cases() if c['name'] == 'different_requested_analysis')
        inv = inventory(case['prediction'], case['reference'], DICT, POLICY)
        p = next(r for r in inv['rows'] if r['side'] == 'prediction')
        g = next(r for r in inv['rows'] if r['side'] == 'reference')
        result = mark_all(inv, reply_for(inv, pairs=[(p, None), (None, g)]))
        self.assertEqual(result['field']['tp'], 0)
        self.assertEqual(result['record']['predicted'], 1)
        self.assertEqual(result['record']['gold'], 1)
        self.assertEqual(result['record']['tp'], 0)

    def test_merged_record_and_duplicate_retain_all_denominators(self):
        gold = {'result': [BASE, {**BASE, 'id': 'R2', 'analysis': 'Dose Group'}]}
        pred = {'result': [BASE]}
        inv = inventory(pred, gold, DICT, POLICY)
        sides = {s: [r for r in inv['rows'] if r['side'] == s] for s in ('prediction', 'reference')}
        pairs = [(sides['prediction'][0], sides['reference'][0]), (None, sides['reference'][1])]
        result = mark_all(inv, reply_for(inv, pairs=pairs))
        self.assertEqual((result['record']['tp'], result['record']['predicted'], result['record']['gold']), (1, 1, 2))
        inv = inventory({'result': [BASE, {**BASE, 'id': 'duplicate'}]}, {'result': [BASE]}, DICT, POLICY)
        result = mark_all(inv, reply_for(inv))
        self.assertEqual((result['record']['tp'], result['record']['predicted'], result['record']['gold']), (1, 2, 1))


if __name__ == '__main__': unittest.main()
