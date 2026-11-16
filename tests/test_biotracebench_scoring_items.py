"""S02 uses synthetic databases only; no papers, provider calls or real gold."""
import copy
import json
import socket
import tempfile
import unittest
from decimal import Decimal, localcontext
from pathlib import Path
from unittest.mock import patch

from biotracebench.common import encoded, write, read, seal
from biotracebench_scoring.evaluation import canonical, score
from biotracebench_scoring.scoring_items import split_statistics
from test_biotracebench import ANSWER, DICTIONARY

DICT = {"result": {"identifier": "result_id", "fields": [{"key": k} for k in
        ("result_id", "synthetic_object", "result_value", "supplementary_statistics")]}}
POLICY = {"version": "biotracebench-score-2", "item_policy": "biotracebench-scoring-items-1", "frozen": True,
          "identity_groups": {"result": [["synthetic_object"]]}, "field_rules": {}, "field_roles": {},
          "compound_fields": ["result.supplementary_statistics"]}
GOLD = {"result": [{"result_id": "r1", "synthetic_object": "Synthetic endpoint A", "result_value": 0,
                    "supplementary_statistics": "95% CI [0, 2]; P < 0.05; 0%; denominator = 30"}]}


class ScoringItemTests(unittest.TestCase):
    def evaluate(self, prediction=None, gold=None, policy=None, decisions=None):
        return score(copy.deepcopy(prediction if prediction is not None else GOLD),
                     copy.deepcopy(gold if gold is not None else GOLD), DICT, policy or POLICY, decisions)

    def annotate(self, result, state, field="result_value", side=None):
        annotations = {}
        for entry in result["adjudication_queue"]:
            if entry["kind"] == "field_state" and entry["field"] == field and (side is None or entry["side"] == side):
                annotations[entry["id"]] = {"state": state, "basis": "synthetic source explicitly supports this state"}
        self.assertTrue(annotations)
        return {"contexts": {result["context_id"]: {"field_states": annotations}}}

    def test_compound_is_atomic_and_does_not_change_submission(self):
        submitted = copy.deepcopy(GOLD)
        with patch.object(socket, "socket", side_effect=AssertionError("Network forbidden")):
            result = self.evaluate(submitted)
        self.assertEqual(submitted, GOLD)
        # object, value, CI bounds, level, P/comparator, percentage, denominator
        self.assertEqual(result["field"]["tp"], 7)
        self.assertEqual(result["record"]["tp"], 1)
        self.assertEqual(result["status"], "final_under_frozen_dictionary")
        self.assertEqual(json.loads(encoded(result))["field"]["tp"], 7)

    def test_correct_p_incorrect_denominator_scores_separately(self):
        submitted = copy.deepcopy(GOLD)
        submitted["result"][0]["supplementary_statistics"] = GOLD["result"][0]["supplementary_statistics"].replace("30", "31")
        result = self.evaluate(submitted)
        self.assertEqual((result["field"]["tp"], result["field"]["predicted"], result["field"]["gold"]), (6, 7, 7))
        self.assertEqual(result["record"]["tp"], 0)
        self.assertTrue(result["gold_field_correctness"]["result:0:supplementary_statistics.p_value"])
        self.assertFalse(result["gold_field_correctness"]["result:0:supplementary_statistics.denominator"])

    def test_item_order_not_significant_but_comparator_and_interval_direction_are(self):
        submitted = copy.deepcopy(GOLD)
        submitted["result"][0]["supplementary_statistics"] = "denominator=30; 0%; P < 5e-2; 95% CI [0.0, 2.00]"
        self.assertEqual(self.evaluate(submitted)["field"]["f1"], 1)
        submitted["result"][0]["supplementary_statistics"] = "denominator=30; 0%; P = 0.05; 95% CI [2, 0]"
        self.assertEqual(self.evaluate(submitted)["field"]["tp"], 5)

    def test_unsupported_and_duplicate_segments_are_not_dropped_or_inferred(self):
        parts, rest = split_statistics("P < 0.05; n=0; P = 0.01; adjusted analysis; 2/10")
        self.assertEqual(parts["denominator"]["value"]["count"], 0)
        self.assertEqual(rest, ["P = 0.01", "adjusted analysis", "2/10"])
        gold = copy.deepcopy(GOLD)
        gold["result"][0]["supplementary_statistics"] += "; adjusted analysis"
        result = self.evaluate(gold, gold)
        self.assertEqual(result["status"], "provisional")
        self.assertEqual(result["field"]["tp"], 7)
        self.assertEqual(result["field"]["gold"], 8)
        self.assertEqual(len([q for q in result["adjudication_queue"] if q["kind"] == "compound_projection"]), 2)

    def test_bare_null_never_means_unreported_automatically(self):
        gold = copy.deepcopy(GOLD)
        gold["result"][0]["result_value"] = None
        result = self.evaluate(gold, gold)
        self.assertEqual(result["field"]["tp"], 6)
        self.assertEqual(result["record"]["tp"], 0)
        self.assertEqual({q["state"] for q in result["adjudication_queue"]}, {"unspecified_null"})
        decisions = self.annotate(result, "not_reported")
        resolved = self.evaluate(gold, gold, decisions=decisions)
        self.assertEqual(resolved["field"]["tp"], 7)
        self.assertEqual(resolved["status"], "final_under_frozen_dictionary")

    def test_not_applicable_does_not_reward_empty_slots(self):
        gold = copy.deepcopy(GOLD)
        gold["result"][0]["result_value"] = None
        result = self.evaluate(gold, gold)
        resolved = self.evaluate(gold, gold, decisions=self.annotate(result, "not_applicable"))
        self.assertEqual((resolved["field"]["tp"], resolved["field"]["predicted"], resolved["field"]["gold"]), (6, 6, 6))
        self.assertEqual(resolved["record"]["tp"], 1)

    def test_unresolved_conflicting_and_ambiguous_stay_provisional(self):
        gold = copy.deepcopy(GOLD)
        gold["result"][0]["result_value"] = None
        result = self.evaluate(gold, gold)
        for state in ("unresolved", "conflicting", "ambiguous"):
            with self.subTest(state=state):
                resolved = self.evaluate(gold, gold, decisions=self.annotate(result, state))
                self.assertEqual(resolved["field"]["tp"], 6)
                self.assertEqual(resolved["status"], "provisional")

    def test_missing_prediction_stays_unanswered_and_is_not_filled(self):
        submitted = copy.deepcopy(GOLD)
        del submitted["result"][0]["result_value"]
        result = self.evaluate(submitted)
        self.assertEqual((result["field"]["tp"], result["field"]["predicted"], result["field"]["gold"]), (6, 6, 7))
        item = result["scoring_items"]["result"]["prediction"][0]["items"]["result_value"]
        self.assertEqual(item["state"], "model_unanswered")
        decisions = {"contexts": {result["context_id"]: {"field_states": {item["field_id"]: {"state": "not_reported", "basis": "incorrect"}}}}}
        with self.assertRaisesRegex(ValueError, "missing model field"):
            self.evaluate(submitted, decisions=decisions)

    def test_zero_nr_ne_and_nonfinite_are_distinct(self):
        for token in ("NR", "NE", "<0", None):
            with self.subTest(token=token):
                submitted = copy.deepcopy(GOLD)
                submitted["result"][0]["result_value"] = token
                self.assertEqual(self.evaluate(submitted)["field"]["tp"], 6)
        for value in (float("nan"), Decimal("Infinity")):
            gold = copy.deepcopy(GOLD)
            gold["result"][0]["result_value"] = value
            result = self.evaluate(gold, gold)
            self.assertEqual(result["field"]["tp"], 6)
            self.assertEqual(result["status"], "provisional")
            encoded(result)

    def test_human_projection_is_bound_to_literal_submitted_content(self):
        gold = copy.deepcopy(GOLD)
        submitted = copy.deepcopy(GOLD)
        submitted["result"][0]["supplementary_statistics"] = "confidence 95 percent; interval zero to two; p below .05; zero percent; n thirty"
        result = self.evaluate(submitted, gold)
        entry = next(q for q in result["adjudication_queue"] if q["kind"] == "compound_projection")
        parts, _ = split_statistics(gold["result"][0]["supplementary_statistics"])
        source = submitted["result"][0]["supplementary_statistics"]
        # Human interpretation is explicit; source fragments are never taken from gold.
        for part in parts.values():
            part["source_text"] = source
        decision = {"basis": "synthetic human interpretation", "complete": True, "items": parts}
        decisions = {"contexts": {result["context_id"]: {"projections": {entry["id"]: decision}}}}
        self.assertEqual(self.evaluate(submitted, gold, decisions=decisions)["field"]["tp"], 7)
        decision["items"]["denominator"]["source_text"] = "not present in submitted text"
        with self.assertRaisesRegex(ValueError, "literal submitted"):
            self.evaluate(submitted, gold, decisions=decisions)

    def test_manual_projection_survives_json_and_preserves_decimal_precision(self):
        parts, _ = split_statistics("P=0.1234567890123456789012345678901; n=1234567890123456789012345678901")
        self.assertEqual(parts["p_value"]["value"]["value"], Decimal("0.1234567890123456789012345678901"))
        from biotracebench_scoring.scoring_items import item_value
        self.assertEqual(item_value("p_value", {"operator": "=", "value": "0.1234567890123456789012345678901"}), parts["p_value"]["value"])
        with self.assertRaises(ValueError):
            item_value("denominator", {"kind": "analysis", "count": "2.5"})
        with self.assertRaises(ValueError):
            item_value("p_value", {"operator": "?", "value": 0})

    def test_long_counts_remain_exact_in_split_fields(self):
        gold = copy.deepcopy(GOLD)
        gold["result"][0]["supplementary_statistics"] = "n=1234567890123456789012345678901"
        submitted = copy.deepcopy(gold)
        submitted["result"][0]["supplementary_statistics"] = "n=1234567890123456789012345678902"
        with localcontext() as context:
            context.prec = 6
            result = self.evaluate(submitted, gold)
        self.assertEqual(result["field"]["tp"], 2)

    def test_unknown_science_penalized_and_only_explicit_provenance_excluded(self):
        submitted = copy.deepcopy(GOLD)
        submitted["result"][0].update({"invented_claim": "wrong", "source_locator": "table A"})
        policy = copy.deepcopy(POLICY)
        policy["field_roles"]["result.source_locator"] = "provenance"
        policy["field_roles"]["result.invented_claim"] = "scientific"
        result = self.evaluate(submitted, policy=policy)
        self.assertEqual((result["field"]["tp"], result["field"]["predicted"]), (7, 8))
        self.assertEqual(result["record"]["tp"], 0)
        self.assertEqual(result["adjudication_queue"][0]["field"], "invented_claim")

    def test_empty_prediction_has_six_zero_metrics(self):
        result = self.evaluate({})
        self.assertEqual([result[m][k] for m in ("field", "record") for k in ("precision", "recall", "f1")], [0] * 6)

    def test_scientific_values_do_not_break_identity_ties(self):
        gold = copy.deepcopy(GOLD)
        second = copy.deepcopy(gold["result"][0])
        second.update(result_id="r2", result_value=1)
        gold["result"].append(second)
        result = self.evaluate(GOLD, gold)
        self.assertEqual(result["pairs"]["result"], [])
        self.assertEqual(result["field"]["tp"], 0)
        q = next(q for q in result["adjudication_queue"] if q["kind"] == "record_identity")
        decisions = {"contexts": {result["context_id"]: {"matches": {"result": [
            {"prediction": q["prediction"], "reference": q["candidates"][0]["reference"], "basis": "synthetic independent source identity"}]}}}}
        resolved = self.evaluate(GOLD, gold, decisions=decisions)
        self.assertEqual(resolved["field"]["tp"], 7)
        self.assertEqual(resolved["record"]["gold"], 2)

    def test_no_identity_rule_no_automatic_attribute_credit(self):
        policy = copy.deepcopy(POLICY)
        policy["identity_groups"] = {}
        result = self.evaluate(policy=policy)
        self.assertEqual(result["field"]["tp"], 0)
        self.assertEqual(result["adjudication_queue"][0]["reason"], "no_identity_policy")

    def test_consistent_id_renaming_and_dictionary_roundtrip(self):
        policy = copy.deepcopy(POLICY)
        policy.update(compound_fields=[], identity_groups={"sample": [["sample_name"]],
            "condition": [["sample_id", "experimental_factor"]], "assay_run": [["sample_ids", "assay_type"]]})
        submitted = copy.deepcopy(ANSWER)
        submitted["sample"][0]["sample_id"] = "new-s"
        submitted["condition"][0].update(condition_id="new-c", sample_id="new-s")
        submitted["assay_run"][0].update(assay_id="new-a", sample_ids=["new-s"])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"dictionary.json"
            write(path, DICTIONARY)
            result = score(submitted, ANSWER, read(path), policy)
        self.assertEqual(result["field"]["f1"], 1)
        self.assertEqual(result["record"]["f1"], 1)
        submitted["condition"][0]["sample_id"] = "dangling"
        self.assertEqual(score(submitted, ANSWER, DICTIONARY, policy)["status"], "provisional")

    def test_manual_decision_does_not_transfer_to_changed_input(self):
        gold = copy.deepcopy(GOLD)
        gold["result"][0]["result_value"] = None
        result = self.evaluate(gold, gold)
        decisions = self.annotate(result, "not_reported")
        changed = copy.deepcopy(gold)
        changed["result"][0]["result_id"] = "different-raw-id"
        new = self.evaluate(changed, gold, decisions=decisions)
        self.assertFalse(new["adjudications_applied"])
        self.assertEqual(new["status"], "provisional")
        with self.assertRaisesRegex(ValueError, "Stale"):
            self.evaluate(gold, gold, decisions={"contexts": {result["context_id"]: {"field_states": {"wrong-id": {"state": "not_reported", "basis": "x"}}}}})

    def test_invalid_annotation_cannot_hide_reported_value(self):
        result = self.evaluate()
        item = result["scoring_items"]["result"]["prediction"][0]["items"]["result_value"]
        decisions = {"contexts": {result["context_id"]: {"field_states": {item["field_id"]: {"state": "not_applicable", "basis": "not allowed"}}}}}
        with self.assertRaisesRegex(ValueError, "non-null"):
            self.evaluate(decisions=decisions)

    def test_shipped_policy_is_draft_until_scientific_rules_reviewed(self):
        policy = read(Path(__file__).resolve().parents[1]/"configs/tasks/biotracebench-scoring-v2.json")
        self.assertFalse(policy["frozen"])
        with self.assertRaisesRegex(ValueError, "Freeze"):
            self.evaluate(policy=policy)

    def test_numeric_string_nonfinite_is_not_a_correct_value(self):
        gold = copy.deepcopy(GOLD)
        gold["result"][0]["result_value"] = "NaN"
        policy = copy.deepcopy(POLICY)
        policy["field_rules"]["result.result_value"] = {"numeric": True}
        result = self.evaluate(gold, gold, policy)
        self.assertEqual(result["field"]["tp"], 6)
        self.assertEqual(result["status"], "provisional")

    def test_duplicate_predictions_and_extra_tables_do_not_disappear(self):
        submitted = copy.deepcopy(GOLD)
        submitted["result"].append({**submitted["result"][0], "result_id": "r2"})
        result = self.evaluate(submitted)
        self.assertEqual(result["record"]["predicted"], 2)
        self.assertEqual(result["field"]["predicted"], 14)
        self.assertEqual(result["status"], "provisional")
        submitted = copy.deepcopy(GOLD)
        submitted["invented_table"] = [{"false_claim": "x"}]
        result = self.evaluate(submitted)
        self.assertEqual(result["record"]["predicted"], 1)
        self.assertEqual(result["field"]["predicted"], 7)
        self.assertTrue(any(q["kind"] == "content_classification" for q in result["adjudication_queue"]))
        self.assertEqual(result["status"], "provisional")

    def test_adjudication_is_bound_to_study_and_material_scope(self):
        a = score(GOLD, GOLD, DICT, POLICY, context={"study": "A", "materials": "hashA"})
        b = score(GOLD, GOLD, DICT, POLICY, context={"study": "B", "materials": "hashB"})
        self.assertNotEqual(a["context_id"], b["context_id"])

    def test_manual_rejection_and_text_equivalence_are_explicit(self):
        submitted = copy.deepcopy(GOLD)
        submitted["result"][0]["synthetic_object"] = "different object"
        result = self.evaluate(submitted)
        q = next(q for q in result["adjudication_queue"] if q["kind"] == "record_identity")
        decisions = {"contexts": {result["context_id"]: {"matches": {"result": [{
            "prediction": q["prediction"], "reference": None, "basis": "different source objects"}]}}}}
        rejected = self.evaluate(submitted, decisions=decisions)
        self.assertEqual(rejected["field"]["tp"], 0)
        self.assertEqual(rejected["status"], "final_under_frozen_dictionary")
        gold = copy.deepcopy(GOLD)
        gold["result"][0]["result_value"] = "NE"
        submitted = copy.deepcopy(gold)
        submitted["result"][0]["result_value"] = "not estimable"
        result = self.evaluate(submitted, gold)
        q = next(q for q in result["adjudication_queue"] if q["kind"] == "text_equivalence")
        decisions = {"contexts": {result["context_id"]: {"equivalences": {q["id"]: {"equal": True, "basis": "same meaning in synthetic source"}}}}}
        self.assertEqual(self.evaluate(submitted, gold, decisions=decisions)["field"]["f1"], 1)

    def test_symmetric_and_directed_relationships(self):
        dictionary = {"population": {"identifier": "population_id", "fields": [{"key": k} for k in ("population_id", "population_name")]},
                      "population_relation": {"references": {"population_a_id": "population", "population_b_id": "population"},
                        "fields": [{"key": k} for k in ("population_a_id", "population_b_id", "relationship")]}}
        gold = {"population": [{"population_id": "p1", "population_name": "A"}, {"population_id": "p2", "population_name": "B"}],
                "population_relation": [{"population_a_id": "p1", "population_b_id": "p2", "relationship": "subset of"}]}
        policy = copy.deepcopy(POLICY)
        policy.update(compound_fields=[], identity_groups={"population": [["population_name"]],
            "population_relation": [["population_a_id", "population_b_id", "relationship"]]})
        submitted = json.loads(json.dumps(gold).replace('p1', 'newA').replace('p2', 'newB'))
        submitted["population"].reverse()
        relation = submitted["population_relation"][0]
        relation["population_a_id"], relation["population_b_id"] = relation["population_b_id"], relation["population_a_id"]
        self.assertLess(score(submitted, gold, dictionary, policy)["field"]["f1"], 1)
        gold["population_relation"][0]["relationship"] = relation["relationship"] = "disjoint from"
        self.assertEqual(score(submitted, gold, dictionary, policy)["field"]["f1"], 1)

    def test_cli_saves_items_and_blind_queue_without_generation(self):
        from biotracebench_scoring.__main__ import main
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prepared, run, reference, out = root/"prepared", root/"run", root/"reference", root/"scores"
            write(prepared/"dictionary.json", DICT)
            write(prepared/"materials.json", {"domain": "clinical", "study_id": "synthetic-study"})
            receipt = seal(prepared)
            stages = ["initial", "ordinary_review", "integrated_review"]
            write(run/"manifest.json", {"protocol": "biotracebench-run-1", "tasks": [{"case_id": "SYN001", "prepared": str(prepared), "material_identity": receipt}], "stages": stages})
            for stage in stages:
                write(run/"SYN001"/stage/"final"/"database.json", GOLD)
                seal(run/"SYN001"/stage/"final")
            write(reference/"clinical"/"SYN001"/"SYN001.json", GOLD)
            policy = {**POLICY, "bootstrap_seed": 20261024, "bootstrap_resamples": 10000}
            write(root/"policy.json", policy)
            with patch.object(socket, "socket", side_effect=AssertionError("network forbidden")):
                main(["score", "--run", str(run), "--gold-root", str(reference), "--policy", str(root/"policy.json"), "--out", str(out)])
            scores = read(out/"study-scores.json")
            self.assertEqual(scores[0]["conditions"]["initial"]["field"]["tp"], 7)
            self.assertTrue(scores[0]["conditions"]["initial"]["scoring_items"])
            self.assertEqual(read(out/"blind-adjudication-queue.json"), [])
            self.assertTrue((out/"identity.json").exists())


if __name__ == "__main__":
    unittest.main()
