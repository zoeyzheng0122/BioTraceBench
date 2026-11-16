"""Historical source-bound scorer regressions; current Qwen grading has a shared rule."""
import copy
import json
import unittest
from decimal import Decimal, Inexact, localcontext

from biotracebench.common import digest, encoded, read
from biotracebench_scoring.evaluation import score
from test_biotracebench_alignment import CLINICAL, ROOT, dictionary


class PrecisionTests(unittest.TestCase):
    def setUp(self):
        self.reference = copy.deepcopy(CLINICAL)
        self.reference["result"][0]["result_value"] = Decimal("1.23")
        self.prediction = copy.deepcopy(self.reference)
        self.prediction["result"][0]["result_value"] = Decimal("1.234")
        self.scope = {"study_id": "synthetic-study", "materials": {"synthetic.txt": "synthetic-hash"}}
        self.policy = read(ROOT / "configs/tasks/biotracebench-scoring-v2.json")
        self.policy['precision_contract'] = 'biotracebench-source-precision-1'
        self.policy.pop('precision_policy',None)
        self.policy.pop('unit_catalog', None)
        self.policy.pop('unit_bindings', None)
        self.policy.pop('reference_contract', None)  # Historical itemized precision policy.
        self.policy["identity_task_rules"] = {}  # No real task identities in this synthetic study.
        # Preserve the original itemized precision regression policy explicitly.
        # Current whole-field behavior has separate semantic-review tests.
        self.policy['compound_fields'] = ['result.supplementary_statistics']
        self.policy['semantic_context_fields'] = {}
        self.policy['field_rules'].pop('result.supplementary_statistics', None)
        self.policy['field_rules']['result.result_value'] = {
            'numeric':True,'unit_field':'result_unit','canonical_unit':'mg',
            'unit_scales':{'mg':'1','μg':'0.001','µg':'0.001'}}
        self.policy['field_rules']['result.result_value']['scale_companion_items'] = [
            'supplementary_statistics.confidence_interval', 'supplementary_statistics.standard_deviation',
            'supplementary_statistics.standard_error']
        self.policy["frozen"] = True
        self.rule = {"study_id": self.scope["study_id"], "materials_identity": digest(self.scope["materials"]),
                     "table": "result", "field": "result_value", "selector": {"assessment_time": "week 2", "statistic_type": "difference"},
                     "quantity_kind": "continuous", "source_locator": "synthetic.txt, table A note",
                     "basis": "Synthetic source explicitly states two decimal places, half up, in points.",
                     "decimal_places": 2, "rounding": "ROUND_HALF_UP", "unit": "points"}

    def run_score(self, rounding=True, decisions=None):
        self.policy["precision_rules"] = [self.rule] if rounding else []
        return score(self.prediction, self.reference, dictionary(self.reference), self.policy, decisions, context=self.scope)

    def test_exact_is_default_and_submission_precision_does_not_set_tolerance(self):
        result = self.run_score(False)
        self.assertFalse(result["gold_field_correctness"]["result:0:result_value"])
        self.assertEqual(result["precision_comparison_audit"], [])
        self.reference["result"][0]["result_value"] = Decimal("1.234")
        self.prediction["result"][0]["result_value"] = Decimal("1.23")
        self.assertFalse(self.run_score(False)["gold_field_correctness"]["result:0:result_value"])

    def test_approved_rounding_preserves_raw_and_logs_both_values(self):
        before = copy.deepcopy((self.reference, self.prediction))
        result = self.run_score()
        self.assertEqual(result["field"]["f1"], 1)
        self.assertEqual(result["record"]["f1"], 1)
        self.assertEqual(before, (self.reference, self.prediction))
        audit = result["precision_comparison_audit"][0]
        self.assertEqual(audit["submitted_before"], ("number", "1.234"))
        self.assertEqual(audit["submitted_rounded"], ("number", "1.23"))
        self.assertEqual(audit["rule_identity"], digest(self.rule))
        restored = json.loads(encoded(result))
        self.assertEqual(restored["precision_comparison_audit"][0]["rule"]["source_locator"], self.rule["source_locator"])

    def test_ties_and_negative_values_obey_the_declared_mode(self):
        for value, reference, mode, expected in (
            ("1.225", "1.22", "ROUND_HALF_EVEN", True), ("1.225", "1.22", "ROUND_HALF_UP", False),
            ("-1.225", "-1.23", "ROUND_HALF_UP", True), ("1.235", "1.23", "ROUND_HALF_UP", False),
            ("-0.000", "0", "ROUND_HALF_UP", True)):
            with self.subTest(value=value, mode=mode):
                self.prediction["result"][0]["result_value"] = Decimal(value)
                self.reference["result"][0]["result_value"] = Decimal(reference)
                self.rule["rounding"] = mode
                self.assertEqual(self.run_score()["gold_field_correctness"]["result:0:result_value"], expected)

    def test_large_values_ignore_ambient_decimal_precision_and_traps(self):
        self.reference["result"][0]["result_value"] = Decimal("123456789012345678901234567890.12")
        self.prediction["result"][0]["result_value"] = Decimal("123456789012345678901234567890.124")
        with localcontext() as ctx:
            ctx.prec = 5
            ctx.traps[Inexact] = True
            self.assertEqual(self.run_score()["field"]["f1"], 1)
            self.assertEqual(ctx.prec, 5)
            self.assertTrue(ctx.traps[Inexact])

    def test_source_scope_is_required_and_changed_materials_rejected(self):
        self.scope["materials"] = {"synthetic.txt": "changed"}
        with self.assertRaisesRegex(ValueError, "stale"):
            self.run_score()
        self.scope = None
        with self.assertRaisesRegex(ValueError, "context"):
            self.run_score()

    def test_other_study_rule_cannot_relax_this_study(self):
        self.scope["study_id"] = "different-study"
        result = self.run_score()
        self.assertFalse(result["gold_field_correctness"]["result:0:result_value"])
        self.assertEqual(result["precision_comparison_audit"], [])

    def test_missing_source_mode_or_precision_is_rejected(self):
        for key in ("basis", "source_locator", "rounding", "decimal_places", "quantity_kind", "unit"):
            with self.subTest(key=key):
                old = self.rule.pop(key)
                with self.assertRaises(ValueError):
                    self.run_score()
                self.rule[key] = old
        for places in (True, -1, 1.2):
            self.rule["decimal_places"] = places
            with self.assertRaises(ValueError):
                self.run_score()

    def test_counts_and_denominators_never_inherit_rounding(self):
        self.prediction["population"][0]["population_size"] = 31
        self.prediction["result"][0]["supplementary_statistics"] = "P=0.5; n=31"
        result = self.run_score()
        self.assertFalse(result["gold_field_correctness"]["population:0:population_size"])
        self.assertFalse(result["gold_field_correctness"]["result:0:supplementary_statistics.denominator"])
        for table, field in (("population", "population_size"), ("result", "supplementary_statistics.denominator")):
            self.rule.update(table=table, field=field)
            with self.assertRaisesRegex(ValueError, "cannot be rounded"):
                self.run_score()

    def test_count_typed_result_value_is_rejected(self):
        self.reference["result"][0]["statistic_type"] = "count"
        self.rule["selector"]["statistic_type"] = "count"
        with self.assertRaisesRegex(ValueError, "Counts remain exact"):
            self.run_score()

    def test_selectors_require_unique_reference_and_no_numeric_or_id_selection(self):
        for selector in ({"result_value": "1.23"}, {"result_id": "R1"}, {"assessment_time": "missing"}):
            self.rule["selector"] = selector
            with self.assertRaises(ValueError):
                self.run_score()
        self.rule["selector"] = {"assessment_time": "week 2"}
        self.reference["result"].append(copy.deepcopy(self.reference["result"][0]))
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.run_score()

    def test_rounding_never_resolves_object_identity_ambiguity(self):
        self.prediction["result"].append(copy.deepcopy(self.prediction["result"][0]))
        self.prediction["result"][1]["result_id"] = "R2"
        self.prediction["result"][1]["result_value"] = 999  # Competing content, not an exact surplus copy.
        result = self.run_score()
        self.assertEqual(result["pairs"]["result"], [])
        self.assertEqual(result["precision_comparison_audit"], [])
        self.assertEqual(result["status"], "provisional")

    def test_rule_is_independent_of_row_order_and_internal_ids(self):
        other = copy.deepcopy(self.reference["result"][0])
        other.update(result_id="R2", assessment_time="week 4", result_value=7)
        self.reference["result"].append(other)
        self.prediction["result"].append(copy.deepcopy(other))
        self.reference["result"].reverse()
        self.prediction["result"][0]["result_id"] = "RENAMED"
        self.assertEqual(self.run_score()["field"]["f1"], 1)

    def test_convert_to_declared_unit_before_rounding(self):
        self.reference["result"][0]["result_unit"] = "mg"
        self.prediction["result"][0].update(result_unit="μg", result_value=1234)
        self.rule["unit"] = "mg"
        self.assertEqual(self.run_score()["field"]["f1"], 1)
        self.rule["unit"] = "μg"
        with self.assertRaisesRegex(ValueError, "effective unit"):
            self.run_score()

    def test_undeclared_unit_and_manual_unit_decisions_take_precedence(self):
        self.prediction["result"][0]["result_unit"] = "unknown"
        result = self.run_score()
        self.assertFalse(result["gold_field_correctness"]["result:0:result_value"])
        self.assertEqual(result["precision_comparison_audit"][0]["status"], "unit_comparison_takes_precedence")
        choices = {q["id"]: {"equal": False, "basis": "Synthetic incompatible units"}
                   for q in result["adjudication_queue"] if q["kind"] == "unit_equivalence"}
        decided = self.run_score(decisions={"contexts": {result["context_id"]: {"unit_equivalences": choices}}})
        self.assertFalse(decided["gold_field_correctness"]["result:0:result_value"])

    def test_intervals_require_their_own_rule_not_main_value_precision(self):
        self.reference["result"][0]["supplementary_statistics"] = "CI [1.23, 2.34]; P=0.5; n=30"
        self.prediction["result"][0]["supplementary_statistics"] = "CI [1.234, 2.344]; P=0.5; n=30"
        result = self.run_score()
        key = "result:0:supplementary_statistics.confidence_interval"
        self.assertFalse(result["gold_field_correctness"][key])
        self.rule["field"] = "supplementary_statistics.confidence_interval"
        self.assertTrue(self.run_score()["gold_field_correctness"][key])

    def test_inequalities_missing_and_unparsed_values_are_not_rounded(self):
        for value in (None, ">1.234", "NR", "1.23–1.24"):
            with self.subTest(value=value):
                self.prediction["result"][0]["result_value"] = value
                result = self.run_score()
                self.assertFalse(result["gold_field_correctness"]["result:0:result_value"])
                self.assertNotEqual(result["precision_comparison_audit"][0]["status"], "source_rounding")


if __name__ == "__main__":
    unittest.main()
