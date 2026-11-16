"""Identity-first regression cases; entirely synthetic source objects."""
import copy
import itertools
import unittest
from pathlib import Path

from biotracebench.common import read, encoded
from biotracebench_scoring.evaluation import score

ROOT = Path(__file__).resolve().parents[1]
BASIC = {
    "sample": [{"sample_id": "S1", "sample_name": "Preparation A", "biological_source": "Synthetic cells",
                "species": "human", "biological_model": "Synthetic model", "sample_material": "Extract A",
                "sample_accession": "Synthetic:S1 (sample)"}],
    "condition": [{"condition_id": "C1", "sample_id": "S1", "condition_target": "Preparation A", "experimental_factor": "dose",
                   "factor_value": 0, "factor_unit": "mg", "time": "2 h after exposure"}],
    "assay_run": [{"assay_id": "A1", "sample_ids": ["S1"], "assay_type": "RNA-seq", "platform": "Synthetic sequencer",
                   "method": "Named library A, acquisition A", "experiment_run_accession": "Synthetic:R1 (run)"}]}
CLINICAL = {
    "population": [{"population_id": "P1", "population_name": "Arm A", "population_definition": "Eligible synthetic participants assigned A",
                    "population_size": 30, "intervention": "A", "intervention_regimen": "daily", "population_time_frame": "baseline"},
                   {"population_id": "P2", "population_name": "Arm B", "population_definition": "Eligible synthetic participants assigned B",
                    "population_size": 30, "intervention": "B", "intervention_regimen": "daily", "population_time_frame": "baseline"}],
    "measure": [{"measure_id": "M1", "measure_name": "Synthetic score", "measure_definition": "Instrument A score"}],
    "result": [{"result_id": "R1", "population_id": "P1", "measure_id": "M1", "assessment_time": "week 2",
                "statistic_type": "difference", "statistical_method": "Unadjusted synthetic comparison", "result_value": 0,
                "result_unit": "points", "comparison": "P1 minus P2", "supplementary_statistics": "P=0.5; n=30"}],
    "population_relation": [{"population_a_id": "P1", "population_b_id": "P2", "relationship": "disjoint from"}]}
IDS = {"sample": "sample_id", "condition": "condition_id", "assay_run": "assay_id", "population": "population_id",
       "measure": "measure_id", "result": "result_id"}
REFS = {"condition": {"sample_id": "sample"}, "assay_run": {"sample_ids": "sample"},
        "result": {"population_id": "population", "measure_id": "measure"},
        "population_relation": {"population_a_id": "population", "population_b_id": "population"}}


def dictionary(answer):
    return {table: {"identifier": IDS.get(table), "references": REFS.get(table, {}),
                    "fields": [{"key": key} for key in rows[0]]} for table, rows in answer.items()}


class AlignmentTests(unittest.TestCase):
    def setUp(self):
        self.policy = read(ROOT/"configs/tasks/biotracebench-scoring-v2.json")
        # Generic synthetic objects have no real task-specific identity policy.
        self.policy["identity_task_rules"] = {}
        # Synthetic verification only; the distributed formal policy stays draft.
        self.policy["frozen"] = True

    def evaluate(self, prediction, reference=BASIC, policy=None, decisions=None):
        return score(prediction, reference, dictionary(reference), policy or self.policy, decisions)

    def test_shared_policy_handles_both_domains_and_all_table_orders(self):
        for reference in (BASIC, CLINICAL):
            renamed = copy.deepcopy(reference)
            mapping = {row[IDS[table]]: "RENAMED_"+row[IDS[table]] for table, rows in renamed.items() if table in IDS for row in rows}
            for table, rows in renamed.items():
                for row in rows:
                    for key in [IDS.get(table), *REFS.get(table, {})]:
                        if key in row:
                            row[key] = [mapping[v] for v in row[key]] if isinstance(row[key], list) else mapping[row[key]]
                    if table == "result":
                        row["comparison"] = "RENAMED_P1 minus RENAMED_P2"
                rows.reverse()
            for order in itertools.permutations(reference):
                with self.subTest(order=order):
                    d = dictionary(reference)
                    result = score(renamed, reference, {k:d[k] for k in order}, self.policy)
                    self.assertEqual(result["field"]["f1"], 1)
                    self.assertEqual(result["record"]["f1"], 1)
                    self.assertEqual(result["status"], "final_under_frozen_dictionary")
                    encoded(result)

    def test_equal_counts_cannot_match_different_population(self):
        prediction = copy.deepcopy(CLINICAL)
        prediction["population"][0].update(population_name="Other group", population_definition="Other eligibility")
        result = self.evaluate(prediction, CLINICAL)
        self.assertNotIn({"prediction": 0, "gold": 0}, result["pairs"]["population"])
        self.assertFalse(result["gold_field_correctness"]["population:0:population_size"])
        self.assertEqual(result["pairs"]["result"], [])

    def test_outcome_correctness_never_breaks_identity_tie(self):
        reference = copy.deepcopy(CLINICAL)
        reference["result"].append({**reference["result"][0], "result_id": "R2", "result_value": 50})
        result = self.evaluate(CLINICAL, reference)
        self.assertEqual(result["pairs"]["result"], [])
        self.assertEqual(result["alignment_audit"]["result"][0]["status"], "ambiguous_or_unmatched_identity")

    def test_missing_strong_accession_does_not_block_complete_sample_combination(self):
        prediction, reference = copy.deepcopy(BASIC), copy.deepcopy(BASIC)
        prediction["sample"][0]["sample_accession"] = reference["sample"][0]["sample_accession"] = None
        result = self.evaluate(prediction, reference)
        self.assertEqual(result["pairs"]["sample"], [{"prediction": 0, "gold": 0}])
        self.assertEqual(result["alignment_audit"]["sample"][0]["evidence"]["matched_groups"],
                         [["sample_name", "biological_source", "sample_material"]])

    def test_conflicting_object_accessions_block_fallback_description(self):
        prediction = copy.deepcopy(BASIC)
        prediction["sample"][0]["sample_accession"] = "Synthetic:OTHER (sample)"
        result = self.evaluate(prediction)
        self.assertEqual(result["pairs"]["sample"], [])
        entry = next(q for q in result["adjudication_queue"] if q["kind"] == "record_identity" and q["table"] == "sample")
        self.assertIn("sample_accession", entry["identity_evidence"][0]["conflicting_fields"])

    def test_project_or_study_accession_is_not_a_unique_acquisition(self):
        for level in ("project", "study", "dataset", "software"):
            with self.subTest(level=level):
                reference = copy.deepcopy(BASIC)
                reference["assay_run"][0]["experiment_run_accession"] = "Synthetic:X ("+level+")"
                result = self.evaluate(reference, reference)
                self.assertEqual(result["pairs"]["assay_run"], [])
                self.assertEqual(result["status"], "provisional")
        reference["assay_run"][0]["experiment_run_accession"] = "Synthetic:L (library)"
        self.assertEqual(self.evaluate(reference, reference)["pairs"]["assay_run"], [{"prediction": 0, "gold": 0}])

    def test_generic_method_platform_and_technique_are_not_enough(self):
        reference = copy.deepcopy(BASIC)
        reference["assay_run"][0]["experiment_run_accession"] = None
        result = self.evaluate(reference, reference)
        self.assertEqual(result["pairs"]["assay_run"], [])

    def test_conflicting_model_or_direction_is_not_ignored(self):
        for field, value in (("statistical_method", "Adjusted model B"), ("comparison", "P2 minus P1")):
            with self.subTest(field=field):
                prediction = copy.deepcopy(CLINICAL)
                prediction["result"][0][field] = value
                result = self.evaluate(prediction, CLINICAL)
                self.assertEqual(result["pairs"]["result"], [])
                self.assertIn(field, result["alignment_audit"]["result"][0]["evidence"][0]["conflicting_fields"])

    def test_wrong_value_still_scored_after_identity_established(self):
        prediction = copy.deepcopy(CLINICAL)
        prediction["result"][0]["result_value"] = 123
        result = self.evaluate(prediction, CLINICAL)
        self.assertEqual(result["pairs"]["result"], [{"prediction": 0, "gold": 0}])
        self.assertFalse(result["gold_field_correctness"]["result:0:result_value"])
        self.assertEqual(result["field"]["gold"]-result["field"]["tp"], 1)

    def test_reject_weak_and_outcome_identity_policies(self):
        for table, group in (("population", ["population_size"]), ("result", ["result_value"]),
                             ("assay_run", ["assay_type", "platform"]), ("condition", ["time"]),
                             ("sample", ["sample_id"])):
            with self.subTest(table=table, group=group):
                policy = copy.deepcopy(self.policy)
                policy["identity_groups"][table] = [group]
                reference = CLINICAL if table in CLINICAL else BASIC
                with self.assertRaises(ValueError):
                    self.evaluate(reference, reference, policy)

    def test_blank_or_missing_identity_cannot_be_an_anchor(self):
        reference = copy.deepcopy(CLINICAL)
        reference["measure"][0]["measure_definition"] = "   "
        result = self.evaluate(reference, reference)
        self.assertEqual(result["pairs"]["measure"], [])

    def test_human_identity_decision_is_audited_and_still_scores_errors(self):
        prediction = copy.deepcopy(CLINICAL)
        prediction["result"][0]["comparison"] = "P2 minus P1"
        result = self.evaluate(prediction, CLINICAL)
        q = next(q for q in result["adjudication_queue"] if q["kind"] == "record_identity" and q["table"] == "result")
        decision = {"prediction": q["prediction"], "reference": q["candidates"][0]["reference"], "basis": "Synthetic source confirms same target but wrong submitted direction"}
        decision["evidence"] = [{"source": "synthetic-source.txt", "locator": "Result row 1"}]
        decisions = {"contexts": {result["context_id"]: {"matches": {"result": [decision]}}}}
        resolved = self.evaluate(prediction, CLINICAL, decisions=decisions)
        self.assertEqual(resolved["alignment_audit"]["result"][0]["status"], "human_match")
        self.assertFalse(resolved["gold_field_correctness"]["result:0:comparison"])
        decisions["contexts"][result["context_id"]]["matches"]["result"].append(decision)
        with self.assertRaisesRegex(ValueError, "one-to-one"):
            self.evaluate(prediction, CLINICAL, decisions=decisions)


if __name__ == "__main__":
    unittest.main()
