"""Synthetic frozen text rules and blind, source-based adjudication."""
import copy
import json
import socket
import unittest
from unittest.mock import patch

from biotracebench.common import encoded, read
from biotracebench_scoring.evaluation import score
from test_biotracebench_alignment import BASIC, ROOT, dictionary


class TextScoringTests(unittest.TestCase):
    def setUp(self):
        self.reference = copy.deepcopy(BASIC)
        self.prediction = copy.deepcopy(BASIC)
        self.prediction["sample"][0]["species"] = "H. sapiens"
        self.policy = read(ROOT / "configs/scoring/scoring-policy.json")
        self.policy["identity_task_rules"] = {}  # No real task identities in this synthetic study.
        self.policy["frozen"] = True
        self.rule = {"aliases": {"H. sapiens": "human"},
                     "text_basis": "Synthetic source explicitly identifies both names as the same species."}
        self.scope = {"study_id": "synthetic-A", "materials": "synthetic-materials-1"}

    def evaluate(self, decisions=None):
        with patch.object(socket, "socket", side_effect=AssertionError("No network or model judges")):
            return score(self.prediction, self.reference, dictionary(self.reference), self.policy, decisions, context=self.scope)

    def approve(self):
        self.policy["field_rules"]["sample.species"] = self.rule

    def test_default_does_not_guess_equivalence(self):
        result = self.evaluate()
        self.assertFalse(result["gold_field_correctness"]["sample:0:species"])
        self.assertEqual(result["status"], "provisional")
        queue = next(q for q in result["adjudication_queue"] if q["kind"] == "text_equivalence")
        self.assertEqual(queue["submitted"], "H. sapiens")
        self.assertNotIn("condition", queue)
        self.assertNotIn("model", queue)

    def test_fixed_aliases_are_symmetric_and_preserve_raw_and_audit(self):
        self.approve()
        before = copy.deepcopy((self.prediction, self.reference))
        result = self.evaluate()
        self.assertEqual(result["field"]["f1"], 1)
        self.assertEqual(result["record"]["f1"], 1)
        self.assertEqual(before, (self.prediction, self.reference))
        audit = result["text_normalization_audit"]["sample"]["prediction"][0]
        self.assertEqual(audit["original"], "H. sapiens")
        self.assertEqual(audit["normalized"], ("text", "human"))
        self.assertEqual(audit["basis"], self.rule["text_basis"])
        comparison = next(x for x in result["text_comparison_audit"] if x["field"] == "species")
        self.assertEqual(comparison["rule_identity"], audit["rule_identity"])
        json.loads(encoded(result))
        self.reference, self.prediction = self.prediction, self.reference
        self.assertEqual(self.evaluate()["field"]["f1"], 1)

    def test_rules_are_field_specific_not_global_substring_replacements(self):
        self.approve()
        self.prediction["sample"][0]["biological_model"] = "H. sapiens"
        self.reference["sample"][0]["biological_model"] = "human"
        result = self.evaluate()
        self.assertTrue(result["gold_field_correctness"]["sample:0:species"])
        self.assertFalse(result["gold_field_correctness"]["sample:0:biological_model"])
        self.prediction["sample"][0]["species"] = "human and mouse"
        self.assertFalse(self.evaluate()["gold_field_correctness"]["sample:0:species"])

    def test_unlisted_text_still_requires_manual_decision(self):
        self.approve()
        self.prediction["sample"][0]["species"] = "unlisted species description"
        result = self.evaluate()
        self.assertEqual(result["status"], "provisional")
        self.assertFalse(result["gold_field_correctness"]["sample:0:species"])

    def test_human_true_and_false_both_keep_basis_and_originals(self):
        initial = self.evaluate()
        q = next(q for q in initial["adjudication_queue"] if q["kind"] == "text_equivalence")
        for equal in (True, False):
            basis = "Synthetic source decision: " + str(equal)
            decisions = {"contexts": {initial["context_id"]: {"equivalences": {q["id"]: {"equal": equal, "basis": basis}}}}}
            result = self.evaluate(decisions)
            self.assertEqual(result["gold_field_correctness"]["sample:0:species"], equal)
            self.assertEqual(result["status"], "final_under_frozen_dictionary")
            audit = next(x for x in result["text_comparison_audit"] if x.get("id") == q["id"])
            self.assertEqual(audit["status"], "human_adjudicated")
            self.assertEqual(audit["basis"], basis)
            self.assertEqual(audit["submitted"], "H. sapiens")
            self.assertEqual(audit["reference"], "human")
        self.assertEqual(initial["status"], "provisional")

    def test_manual_decisions_require_basis_and_do_not_leak_to_changed_scope(self):
        initial = self.evaluate()
        q = next(q for q in initial["adjudication_queue"] if q["kind"] == "text_equivalence")
        decisions = {"contexts": {initial["context_id"]: {"equivalences": {q["id"]: {"equal": True, "basis": " "}}}}}
        with self.assertRaises(ValueError):
            self.evaluate(decisions)
        decisions["contexts"][initial["context_id"]]["equivalences"][q["id"]]["basis"] = "source"
        self.scope["study_id"] = "synthetic-B"
        self.assertEqual(self.evaluate(decisions)["status"], "provisional")

    def test_missing_rule_basis_and_contract_are_rejected(self):
        self.approve()
        self.rule.pop("text_basis")
        with self.assertRaisesRegex(ValueError, "basis"):
            self.evaluate()
        self.rule["text_basis"] = "source"
        self.policy.pop("text_contract")
        with self.assertRaisesRegex(ValueError, "contract"):
            self.evaluate()

    def test_no_alias_chains_cycles_or_nontext_canonical_values(self):
        self.approve()
        for aliases in ({"A": "B", "B": "C"}, {"A": "B", "B": "A"}, {"A": None}, {"A": ""}, {"1": "2"}, {"NR": "NE"}):
            self.rule["aliases"] = aliases
            with self.subTest(aliases=aliases), self.assertRaises(ValueError):
                self.evaluate()

    def test_whitespace_and_case_are_only_changed_by_explicit_rules(self):
        self.prediction["sample"][0]["species"] = " HUMAN  "
        self.assertEqual(self.evaluate()["status"], "provisional")
        self.rule.update(aliases={}, normalize_space=True, casefold=True)
        self.approve()
        self.assertEqual(self.evaluate()["field"]["f1"], 1)
        self.rule["aliases"] = {"H. sapiens": "human"}
        with self.assertRaisesRegex(ValueError, "normalization"):
            self.evaluate()

    def test_aliases_cannot_replace_ids_units_counts_or_unknown_fields(self):
        for field in ("sample.sample_id", "sample.sample_accession", "sample.unknown",
                      "condition.sample_id", "condition.factor_unit"):
            with self.subTest(field=field):
                self.policy["field_rules"][field] = self.rule
                with self.assertRaisesRegex(ValueError, "cannot alter"):
                    self.evaluate()
                del self.policy["field_rules"][field]

    def test_aliases_cannot_hide_identity_ambiguity(self):
        self.approve()
        self.prediction["sample"].append(copy.deepcopy(self.prediction["sample"][0]))
        self.prediction["sample"][1]["sample_id"] = "duplicate"
        self.prediction["sample"][1]["sample_material"] = "Different submitted material"
        result = self.evaluate()
        self.assertEqual(result["pairs"]["sample"], [])
        self.assertFalse(result["gold_field_correctness"]["sample:0:species"])
        self.assertEqual(len(result["text_normalization_audit"]["sample"]["prediction"]), 2)

    def test_empty_and_missing_values_do_not_become_equal_text(self):
        self.approve()
        for value in (None, ""):
            self.prediction["sample"][0]["species"] = value
            self.assertFalse(self.evaluate()["gold_field_correctness"]["sample:0:species"])
        del self.prediction["sample"][0]["species"]
        self.assertFalse(self.evaluate()["gold_field_correctness"]["sample:0:species"])


if __name__ == "__main__":
    unittest.main()
