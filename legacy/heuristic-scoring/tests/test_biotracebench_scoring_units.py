"""Legacy one-family unit policies stay replayable with synthetic data only."""
import copy
import unittest
from decimal import Decimal, localcontext

from biotracebench.common import read, encoded
from biotracebench_scoring.evaluation import score
from test_biotracebench_alignment import BASIC, CLINICAL, ROOT, dictionary


class UnitScoringTests(unittest.TestCase):
    def setUp(self):
        self.policy = read(ROOT/"configs/scoring/scoring-policy.json")
        self.policy.pop('unit_catalog', None)
        self.policy.pop('unit_bindings', None)
        self.policy.pop('reference_contract', None)  # Historical state/itemization policy.
        # Historical compatibility belongs to this synthetic fixture, never the active policy.
        for field, unit in (('condition.factor_value','factor_unit'),('result.result_value','result_unit')):
            self.policy['field_rules'][field] = {'numeric':True,'unit_field':unit,
                'canonical_unit':'mg','unit_scales':{'mg':'1','μg':'0.001','µg':'0.001'}}
        self.policy["identity_task_rules"] = {}  # No real task identities in this synthetic study.
        self.policy["frozen"] = True
        self.reference = copy.deepcopy(BASIC)
        self.reference["condition"][0].update(factor_value=1, factor_unit="mg")

    def evaluate(self, prediction, reference=None, decisions=None):
        reference = self.reference if reference is None else reference
        return score(prediction, reference, dictionary(reference), self.policy, decisions)

    def test_predeclared_microgram_spellings_and_reverse_conversion(self):
        for unit in ("μg", "µg"):
            prediction = copy.deepcopy(self.reference)
            prediction["condition"][0].update(factor_value=1000, factor_unit=unit)
            before = copy.deepcopy(prediction)
            result = self.evaluate(prediction)
            self.assertEqual(result["field"]["f1"], 1)
            self.assertEqual(result["record"]["f1"], 1)
            self.assertEqual(prediction, before)
            self.assertEqual(self.evaluate(self.reference, prediction)["field"]["f1"], 1)
            logs = result["unit_conversion_audit"]["condition"]["prediction"][0]["conversions"]
            self.assertEqual(logs[0]["original_value"], 1000)
            self.assertEqual(logs[0]["original_unit"], unit)
            self.assertEqual(Decimal(logs[0]["normalized_value"]), 1)
            self.assertEqual(logs[0]["scale"], "0.001")
            encoded(result)

    def test_zero_is_preserved_and_no_tolerance_is_added(self):
        self.reference["condition"][0]["factor_value"] = 0
        prediction = copy.deepcopy(self.reference)
        prediction["condition"][0].update(factor_value=0, factor_unit="μg")
        self.assertEqual(self.evaluate(prediction)["field"]["f1"], 1)
        prediction["condition"][0]["factor_value"] = Decimal("0.000000001")
        result = self.evaluate(prediction)
        self.assertEqual(result["field"]["gold"]-result["field"]["tp"], 1)

    def test_exact_long_decimal_independent_of_global_context(self):
        self.reference["condition"][0]["factor_value"] = Decimal("0.123456789012345678901234567891")
        prediction = copy.deepcopy(self.reference)
        prediction["condition"][0].update(factor_value=Decimal("123.456789012345678901234567891"), factor_unit="μg")
        with localcontext() as ctx:
            ctx.prec = 6
            self.assertEqual(self.evaluate(prediction)["field"]["f1"], 1)
            prediction["condition"][0]["factor_value"] = Decimal("123.456789012345678901234567892")
            result = self.evaluate(prediction)
            self.assertEqual(result["field"]["gold"]-result["field"]["tp"], 1)
            self.assertEqual(ctx.prec, 6)

    def test_numeric_text_uses_explicit_numeric_policy(self):
        prediction = copy.deepcopy(self.reference)
        prediction["condition"][0].update(factor_value="1000.00", factor_unit="μg")
        self.assertEqual(self.evaluate(prediction)["field"]["f1"], 1)

    def test_equal_bare_numbers_with_different_undeclared_units_are_not_true_positives(self):
        prediction = copy.deepcopy(self.reference)
        prediction["condition"][0]["factor_unit"] = "g"
        result = self.evaluate(prediction)
        self.assertFalse(result["gold_field_correctness"]["condition:0:factor_value"])
        self.assertFalse(result["gold_field_correctness"]["condition:0:factor_unit"])
        self.assertEqual(result["status"], "provisional")
        self.assertEqual({q["field"] for q in result["adjudication_queue"] if q["kind"] == "unit_equivalence"}, {"factor_value", "factor_unit"})

    def test_no_global_unit_dictionary_or_dimension_inference(self):
        for unit in ("ug", "mg/kg", "mg/mL", "IU", "G"):
            with self.subTest(unit=unit):
                prediction = copy.deepcopy(self.reference)
                prediction["condition"][0].update(factor_value=1000, factor_unit=unit)
                result = self.evaluate(prediction)
                self.assertTrue(any(q["kind"] == "unit_equivalence" for q in result["adjudication_queue"]))
                self.assertEqual(result["unit_conversion_audit"]["condition"]["prediction"][0]["conversions"][0]["status"], "no_applicable_declared_unit")

    def test_identical_undeclared_units_can_be_compared_without_conversion(self):
        self.reference["condition"][0]["factor_unit"] = "mg/kg"
        self.assertEqual(self.evaluate(self.reference)["field"]["f1"], 1)

    def test_explicit_additional_scale_is_not_a_default(self):
        prediction = copy.deepcopy(self.reference)
        prediction["condition"][0].update(factor_value=Decimal("0.001"), factor_unit="g")
        self.assertEqual(self.evaluate(prediction)["status"], "provisional")
        self.policy["field_rules"]["condition.factor_value"]["unit_scales"]["g"] = "1000"
        self.assertEqual(self.evaluate(prediction)["field"]["f1"], 1)

    def test_ci_sd_se_follow_explicit_rule_but_p_level_percentage_and_n_do_not(self):
        self.legacy_compound_policy()
        reference = copy.deepcopy(CLINICAL)
        reference["result"][0].update(result_value=1, result_unit="mg",
            supplementary_statistics="95% CI [0.5, 1.5]; SD=0.2; SE=0.1; P<0.05; 25%; n=30")
        prediction = copy.deepcopy(reference)
        prediction["result"][0].update(result_value=1000, result_unit="μg",
            supplementary_statistics="95% CI [500, 1500]; SD=200; SE=100; P<0.05; 25%; n=30")
        result = self.evaluate(prediction, reference)
        self.assertEqual(result["field"]["f1"], 1)
        self.assertEqual(result["record"]["f1"], 1)
        logs = result["unit_conversion_audit"]["result"]["prediction"][0]["conversions"][0]
        self.assertEqual({x["field"] for x in logs["converted_items"]}, {"result_value", "supplementary_statistics.confidence_interval", "supplementary_statistics.standard_deviation", "supplementary_statistics.standard_error"})
        prediction["result"][0]["supplementary_statistics"] = prediction["result"][0]["supplementary_statistics"].replace("n=30", "n=30000")
        self.assertEqual(self.evaluate(prediction, reference)["field"]["tp"], result["field"]["tp"]-1)

    def test_unknown_units_also_block_equal_ci_bounds(self):
        self.legacy_compound_policy()
        reference = copy.deepcopy(CLINICAL)
        reference["result"][0].update(result_value=1, result_unit="mg", supplementary_statistics="95% CI [0.5, 1.5]")
        prediction = copy.deepcopy(reference)
        prediction["result"][0]["result_unit"] = "g"
        result = self.evaluate(prediction, reference)
        self.assertFalse(result["gold_field_correctness"]["result:0:supplementary_statistics.confidence_interval"])
        self.assertTrue(result["gold_field_correctness"]["result:0:supplementary_statistics.confidence_level"])

    def legacy_compound_policy(self):
        # Historical itemization remains replayable only through an explicit policy.
        self.policy['compound_fields'] = ['result.supplementary_statistics']
        self.policy['field_rules'].pop('result.supplementary_statistics', None)
        self.policy['field_rules']['result.result_value']['scale_companion_items'] = [
            'supplementary_statistics.confidence_interval', 'supplementary_statistics.standard_deviation',
            'supplementary_statistics.standard_error']

    def test_ranges_inequalities_and_nr_are_not_silently_rewritten(self):
        for value in ("<1000", "500–1500", "NR", "NE"):
            prediction = copy.deepcopy(self.reference)
            prediction["condition"][0].update(factor_value=value, factor_unit="μg")
            result = self.evaluate(prediction)
            item = result["scoring_items"]["condition"]["prediction"][0]["items"]["factor_value"]
            self.assertEqual(item["raw"], value)
            self.assertEqual(result["status"], "provisional")

    def test_same_raw_unit_is_retained_when_one_value_cannot_convert(self):
        self.reference["condition"][0].update(factor_value=1000, factor_unit="μg")
        prediction = copy.deepcopy(self.reference)
        prediction["condition"][0]["factor_value"] = "NR"
        result = self.evaluate(prediction)
        self.assertTrue(result["gold_field_correctness"]["condition:0:factor_unit"])
        self.assertFalse(result["gold_field_correctness"]["condition:0:factor_value"])

    def test_missing_unit_does_not_get_inferred_from_reference(self):
        prediction = copy.deepcopy(self.reference)
        prediction["condition"][0]["factor_unit"] = None
        result = self.evaluate(prediction)
        self.assertFalse(result["gold_field_correctness"]["condition:0:factor_value"])
        self.assertIsNone(result["scoring_items"]["condition"]["prediction"][0]["items"]["factor_unit"]["raw"])

    def test_invalid_scales_and_companions_fail_before_scoring(self):
        for scale in (0.001, "0", "-1", "NaN", "Infinity", "not-a-number"):
            with self.subTest(scale=scale):
                rule = self.policy["field_rules"]["condition.factor_value"]
                rule["unit_scales"]["μg"] = scale
                with self.assertRaises(ValueError):
                    self.evaluate(self.reference)
        self.setUp()
        self.policy["field_rules"]["result.result_value"]["scale_companion_items"] = ["supplementary_statistics.p_value"]
        with self.assertRaisesRegex(ValueError, "CI/SD/SE"):
            self.evaluate(CLINICAL, CLINICAL)

    def test_human_unit_decisions_are_bound_and_do_not_rewrite_submission(self):
        prediction = copy.deepcopy(self.reference)
        prediction["condition"][0].update(factor_value=Decimal("0.001"), factor_unit="g")
        result = self.evaluate(prediction)
        entries = [q for q in result["adjudication_queue"] if q["kind"] == "unit_equivalence"]
        decisions = {"contexts": {result["context_id"]: {"unit_equivalences": {q["id"]: {"equal": True, "basis": "Synthetic source independently confirms equivalent quantity"} for q in entries}}}}
        resolved = self.evaluate(prediction, decisions=decisions)
        self.assertEqual(resolved["field"]["f1"], 1)
        self.assertTrue(all(x["status"] == "human_adjudicated" and x["basis"] for x in resolved["unit_comparison_audit"]))
        self.assertEqual(prediction["condition"][0]["factor_unit"], "g")
        prediction["condition"][0]["factor_value"] = Decimal("0.002")
        self.assertFalse(self.evaluate(prediction, decisions=decisions)["adjudications_applied"])


if __name__ == "__main__":
    unittest.main()
