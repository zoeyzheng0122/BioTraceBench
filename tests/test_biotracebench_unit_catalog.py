"""Approved unit families on synthetic records; no source files or model calls."""
import copy
import unittest
from decimal import Decimal, Inexact, localcontext
from unittest.mock import patch

from biotracebench.common import read, digest, encoded
from biotracebench_scoring.evaluation import score
from test_biotracebench_alignment import BASIC, CLINICAL, ROOT, dictionary


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.policy = read(ROOT/'configs/tasks/biotracebench-scoring-v2.json')
        self.policy['identity_task_rules'] = {}
        self.policy['frozen'] = True  # Synthetic policy only; never activate real rules.
        self.policy['unit_catalog'] = read(ROOT/'configs/tasks/biotracebench-unit-catalog-draft.json')
        self.policy['unit_bindings'] = {
            'condition.factor_value': {
                'unit_field': 'factor_unit',
                'required_context': ['sample_id', 'condition_target', 'experimental_factor'],
                'context_guards': ['time'], 'whole_field_companions': [],
                'basis': 'Synthetic independently aligned factor and source sample.'},
            'result.result_value': {
                'unit_field': 'result_unit',
                'required_context': ['population_id', 'measure_id', 'assessment_time', 'statistic_type'],
                'context_guards': ['comparison', 'statistical_method'],
                'whole_field_companions': ['supplementary_statistics'],
                'basis': 'Synthetic independently aligned measure, population, time and analysis.'}}

    def evaluate(self, prediction, gold, decisions=None, **options):
        with patch('socket.socket', side_effect=AssertionError('No network')):
            return score(prediction, gold, dictionary(gold), self.policy, decisions, **options)

    def pair(self, a, u, b, v, template=BASIC):
        gold = copy.deepcopy(template)
        prediction = copy.deepcopy(gold)
        table, value, unit = ('condition', 'factor_value', 'factor_unit') if template is BASIC else ('result', 'result_value', 'result_unit')
        gold[table][0].update({value: a, unit: u})
        prediction[table][0].update({value: b, unit: v})
        return prediction, gold

    def test_eight_approved_families_in_both_directions(self):
        examples = [(1,'mg',1000,'μg'), (1,'mL',1000,'uL'), (1,'h',60,'min'),
                    (1,'kPa',1000,'Pa'), (1,'μM',1000,'nM'),
                    (1,'mg/dL',10000,'ng/mL'), (1,'h/day',60,'min/day'),
                    (3,'events/h',3,'events/hr')]
        for a,u,b,v in examples:
            for template in (BASIC, CLINICAL):
                with self.subTest(unit=u, reverse=v, clinical=template is CLINICAL):
                    p,g = self.pair(a,u,b,v,template)
                    original = copy.deepcopy((p,g,self.policy))
                    result = self.evaluate(p,g)
                    self.assertEqual(result['field']['f1'], 1)
                    self.assertEqual(result['record']['f1'], 1)
                    self.assertEqual(self.evaluate(g,p)['field']['f1'], 1)
                    self.assertEqual(original, (p,g,self.policy))
                    self.assertEqual(result['unit_catalog_identity'], digest(self.policy['unit_catalog']))
                    encoded(result)

    def test_deployed_policy_embeds_the_same_catalog_without_freezing(self):
        policy = read(ROOT/'configs/tasks/biotracebench-scoring-v2.json')
        self.assertFalse(policy['frozen'])
        self.assertEqual(policy['unit_catalog'], read(ROOT/'configs/tasks/biotracebench-unit-catalog-draft.json'))
        self.assertTrue(policy['unit_catalog']['activated'])
        self.assertFalse(policy['unit_catalog']['frozen'])

    def test_disabled_catalog_cannot_be_silently_used(self):
        self.policy['unit_catalog']['activated'] = False
        with self.assertRaisesRegex(ValueError, 'activated'):
            self.evaluate(BASIC,BASIC)

    def test_frozen_snapshot_scoring_has_no_catalog_file_lookup(self):
        p,g = self.pair(1,'mL',1000,'μL')
        with patch('pathlib.Path.read_text', side_effect=AssertionError('No mutable catalog lookup')):
            self.assertEqual(self.evaluate(p,g)['field']['f1'], 1)

    def test_original_unit_precision_rule_still_runs_after_conversion(self):
        # Explicit historical scorer fixture, not the current Qwen precision contract.
        self.policy['precision_contract']='biotracebench-source-precision-1'
        self.policy.pop('precision_policy',None)
        p,g = self.pair(Decimal('1.23'),'mg',1234,'μg',CLINICAL)
        scope = {'study_id':'synthetic-unit-study','materials':{'source.txt':'synthetic-hash'}}
        self.policy['precision_rules'] = [{'study_id':scope['study_id'],
            'materials_identity':digest(scope['materials']), 'table':'result', 'field':'result_value',
            'selector':{'assessment_time':'week 2','statistic_type':'difference'},
            'quantity_kind':'continuous','source_locator':'source.txt, synthetic table note',
            'basis':'Synthetic source explicitly specifies two decimal places, half up, in mg.',
            'decimal_places':2,'rounding':'ROUND_HALF_UP','unit':'mg'}]
        self.assertEqual(self.evaluate(p,g,context=scope)['field']['f1'], 1)

    def test_renamed_local_ids_preserve_unit_comparison(self):
        p,g = self.pair(1,'mg',1000,'μg')
        p['sample'][0]['sample_id'] = 'renamed-sample'
        p['condition'][0]['sample_id'] = 'renamed-sample'
        p['assay_run'][0]['sample_ids'] = ['renamed-sample']
        p['condition'][0]['condition_id'] = 'renamed-condition'
        self.assertEqual(self.evaluate(p,g)['field']['f1'], 1)

    def test_exact_zero_and_long_decimals_ignore_ambient_traps(self):
        for a,b in [(Decimal('0'),Decimal('0')), (Decimal('0.123456789012345678901234567891'),
                      Decimal('123.456789012345678901234567891'))]:
            p,g = self.pair(a,'mg',b,'μg')
            with localcontext() as ctx:
                ctx.prec = 5
                ctx.traps[Inexact] = True
                self.assertEqual(self.evaluate(p,g)['field']['f1'], 1)
                p['condition'][0]['factor_value'] = b + 1 if not b else Decimal('123.456789012345678901234567892')
                self.assertFalse(self.evaluate(p,g)['gold_field_correctness']['condition:0:factor_value'])
                self.assertEqual(ctx.prec, 5)

    def test_no_cross_family_unapproved_calendar_or_denominator_conversion(self):
        for u,v in [('mg','mL'),('mg','mg/kg'),('μM','mg/mL'),('month','day'),
                    ('year','day'),('% w/v','%'),('Pa','mmHg'),('events/h','events/person-year')]:
            with self.subTest(u=u,v=v):
                p,g = self.pair(1,u,1,v)
                result = self.evaluate(p,g)
                self.assertFalse(result['gold_field_correctness']['condition:0:factor_value'])
                self.assertTrue(any(q['kind']=='unit_equivalence' for q in result['adjudication_queue']))

    def test_context_mismatch_does_not_grant_automatic_conversion(self):
        p,g = self.pair(1,'mg',1000,'μg',CLINICAL)
        self.policy['identity_guards']['result'] = []  # Identity fixed; still check quantity context.
        p['result'][0]['comparison'] = 'P2 minus P1'
        result = self.evaluate(p,g)
        self.assertFalse(result['gold_field_correctness']['result:0:result_value'])
        self.assertTrue(any(q.get('reason')=='quantity_context_not_established' for q in result['adjudication_queue']))

    def test_wrong_association_is_not_fixed_by_unit_conversion(self):
        p,g = self.pair(1,'mg',1000,'μg',CLINICAL)
        p['result'][0]['population_id'] = 'P2'
        self.assertEqual(self.evaluate(p,g)['pairs']['result'], [])

    def test_legacy_unresolved_analysis_context_does_not_authorize_a_unit_change(self):
        self.policy.pop('reference_contract', None)
        p,g = self.pair(1,'mg',1000,'μg',CLINICAL)
        p['result'][0]['statistical_method'] = g['result'][0]['statistical_method'] = None
        result = self.evaluate(p,g)
        self.assertFalse(result['gold_field_correctness']['result:0:result_value'])
        self.assertTrue(any(q.get('reason')=='quantity_context_not_established' for q in result['adjudication_queue']))

    def test_whole_statistics_multiple_intervals_keep_one_scoring_item(self):
        p,g = self.pair(1,'mg',1000,'μg',CLINICAL)
        g['result'][0]['supplementary_statistics'] = '95% CI [0.5, 1.5]; 90% CI [0.6, 1.4]; SD=0.2; P<0.05; n=30'
        p['result'][0]['supplementary_statistics'] = '95% CI [500, 1500]; 90% CI [600, 1400]; SD=200; P<0.05; n=30'
        result = self.evaluate(p,g)
        self.assertEqual(result['field']['f1'], 1)
        items = result['scoring_items']['result']['prediction'][0]['items']
        self.assertIn('supplementary_statistics', items)
        self.assertFalse(any(k.startswith('supplementary_statistics.') for k in items))
        p['result'][0]['supplementary_statistics'] = p['result'][0]['supplementary_statistics'].replace('1400','1401')
        wrong = self.evaluate(p,g)
        self.assertEqual(wrong['field']['gold'] - wrong['field']['tp'], 1)
        self.assertEqual(wrong['record']['tp'], len(g['population']) + len(g['measure']) + len(g['population_relation']))

    def test_p_values_percentages_and_denominators_do_not_scale(self):
        p,g = self.pair(1,'mg',1000,'μg',CLINICAL)
        g['result'][0]['supplementary_statistics'] = '95% CI [0.5, 1.5]; P<0.05; 25%; n=30'
        p['result'][0]['supplementary_statistics'] = '95% CI [500, 1500]; P<0.05; 25%; n=30'
        self.assertEqual(self.evaluate(p,g)['field']['f1'], 1)
        for a,b in [('0.05','50'),('25%','25000%'),('n=30','n=30000')]:
            broken = copy.deepcopy(p)
            broken['result'][0]['supplementary_statistics'] = broken['result'][0]['supplementary_statistics'].replace(a,b)
            self.assertFalse(self.evaluate(broken,g)['gold_field_correctness']['result:0:supplementary_statistics'])

    def test_unsupported_companion_text_is_preserved_and_pending(self):
        p,g = self.pair(1,'mg',1000,'μg',CLINICAL)
        g['result'][0]['supplementary_statistics'] = 'Arm A: 95% CI [0.5, 1.5]; unknown qualifier'
        p['result'][0]['supplementary_statistics'] = 'Arm A: 95% CI [500, 1500]; unknown qualifier'
        result = self.evaluate(p,g)
        self.assertEqual(p['result'][0]['supplementary_statistics'], result['scoring_items']['result']['prediction'][0]['items']['supplementary_statistics']['raw'])
        self.assertTrue(any(q.get('field')=='supplementary_statistics' and q['kind']=='unit_equivalence' for q in result['adjudication_queue']))

    def test_ranges_and_missing_units_not_inferred(self):
        for value,unit in [('<1000','μg'),('500–1500','μg'),(1000,None)]:
            p,g = self.pair(1,'mg',value,unit)
            result = self.evaluate(p,g)
            self.assertFalse(result['gold_field_correctness']['condition:0:factor_value'])
            self.assertEqual(p['condition'][0]['factor_value'], value)

    def test_catalog_validation_and_binding_conflicts_fail_before_comparison(self):
        for scale in ['0','NaN','Infinity','-1',0.001]:
            with self.subTest(scale=scale):
                bad = copy.deepcopy(self.policy)
                bad['unit_catalog']['families']['mass']['scales']['μg'] = scale
                with self.assertRaises(ValueError):
                    score(BASIC,BASIC,dictionary(BASIC),bad)
        self.policy['unit_bindings']['condition.factor_value']['whole_field_companions'] = ['sample_id']
        with self.assertRaises(ValueError):
            self.evaluate(BASIC,BASIC)

    def test_policy_stays_unfrozen_and_conversion_does_not_create_identity(self):
        p,g = self.pair(1,'mg',1000,'μg')
        self.policy['frozen'] = False
        with self.assertRaises(ValueError):
            self.evaluate(p,g)
        result = self.evaluate(p,g,allow_unfrozen=True)
        self.assertEqual(result['field']['f1'], 1)
        self.assertEqual(result['status'], 'provisional')
        self.assertFalse(self.policy['frozen'])


if __name__ == '__main__':
    unittest.main()
