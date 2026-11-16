"""Exact scoring of finite numbers; no scientific data or provider requests."""
import copy
import json
import unittest
from decimal import Decimal, localcontext

from biotracebench_scoring.evaluation import canonical, score
from test_biotracebench import ANSWER, DICTIONARY, POLICY


class ExactScoringNumbersTests(unittest.TestCase):
    def test_distinct_large_counts_remain_distinct(self):
        left = 1234567890123456789012345678901
        right = 1234567890123456789012345678902
        self.assertNotEqual(canonical(left), canonical(right))
        self.assertEqual(canonical(left), ("number", str(left)))

    def test_long_decimal_and_explicit_numeric_text_preserve_all_digits(self):
        text = "0.123456789012345678901234567890123456789"
        expected = ("number", text)
        self.assertEqual(canonical(Decimal(text)), expected)
        self.assertEqual(canonical(text, {"numeric": True}), expected)
        self.assertNotEqual(canonical(text), expected)

    def test_decimal_context_does_not_change_scores(self):
        number = Decimal("0.123456789012345678901234567891")
        other = Decimal("0.123456789012345678901234567892")
        for precision in (6, 28, 60):
            with self.subTest(precision=precision), localcontext() as context:
                context.prec = precision
                self.assertEqual(canonical(number), ("number", str(number)))
                self.assertNotEqual(canonical(number), canonical(other))
                self.assertEqual(context.prec, precision)

    def test_equivalent_numeric_notation_and_zero(self):
        for value in (100, Decimal("100.00"), Decimal("1E2")):
            self.assertEqual(canonical(value), canonical(100))
        for value in (0, -0.0, Decimal("-0.000"), Decimal("0E-20")):
            self.assertEqual(canonical(value), ("number", "0"))
        self.assertNotEqual(canonical(0), canonical(None))
        self.assertNotEqual(canonical(0), canonical(False))
        self.assertNotEqual(canonical("NR"), canonical("NE"))
        self.assertNotEqual(canonical("<0.2"), canonical(Decimal("0.2")))

    def test_json_decimal_loading_does_not_lose_precision_during_scoring(self):
        predicted = copy.deepcopy(ANSWER)
        gold = copy.deepcopy(ANSWER)
        gold["condition"][0]["factor_value"] = json.loads("0.123456789012345678901234567891", parse_float=Decimal)
        predicted["condition"][0]["factor_value"] = json.loads("0.123456789012345678901234567892", parse_float=Decimal)
        result = score(predicted, gold, DICTIONARY, POLICY)
        self.assertEqual(result["field"]["tp"], result["field"]["gold"] - 1)
        self.assertEqual(result["record"]["tp"], result["record"]["gold"] - 1)

    def test_declared_unit_conversion_is_exact_without_global_precision_change(self):
        gold = copy.deepcopy(ANSWER)
        predicted = copy.deepcopy(ANSWER)
        gold["condition"][0].update(factor_value=Decimal("0.123456789012345678901234567891"), factor_unit="g")
        predicted["condition"][0].update(factor_value=Decimal("123.456789012345678901234567891"), factor_unit="mg")
        dictionary = copy.deepcopy(DICTIONARY)
        dictionary["condition"]["fields"].append({"key": "factor_unit"})
        policy = copy.deepcopy(POLICY)
        policy["field_rules"]["condition.factor_value"] = {
            "unit_field": "factor_unit", "canonical_unit": "g", "unit_scales": {"g": "1", "mg": "0.001"}}
        with localcontext() as context:
            context.prec = 6
            result = score(predicted, gold, dictionary, policy)
            self.assertEqual(result["field"]["f1"], 1)
            self.assertEqual(result["record"]["f1"], 1)
            predicted["condition"][0]["factor_value"] = Decimal("123.456789012345678901234567892")
            wrong = score(predicted, gold, dictionary, policy)
            self.assertEqual(wrong["field"]["tp"], result["field"]["tp"] - 1)
            self.assertEqual(context.prec, 6)
        predicted["condition"][0]["factor_value"] = Decimal("123.456789012345678901234567891")
        self.assertLess(score(predicted, gold, dictionary, POLICY)["field"]["f1"], 1)


if __name__ == "__main__":
    unittest.main()
