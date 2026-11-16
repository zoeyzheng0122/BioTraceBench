"""Approved task rule regressions using invented objects and labels, with no sources or providers."""
import copy
import socket
import unittest
from unittest.mock import patch

from biotracebench.common import read
from biotracebench_scoring.evaluation import score
from test_biotracebench_alignment import BASIC, ROOT, dictionary


# Identifier formats only; these are not labels or reference answers from the dataset.
LABELS = {
    "B902": ["ZZZ99-TEST-91.raw", "ZZZ99-TEST-92.raw"],
    "B904": ["TESTNA-1111-1-990101", "TESTNA-1111-2-990101"],
}


class TaskIdentityTests(unittest.TestCase):
    def setUp(self):
        self.policy = read(ROOT / "configs/tasks/biotracebench-scoring-v2.json")
        self.policy['identity_task_rules'] = read(ROOT/'tests/fixtures/synthetic_identity_rules.json')
        self.assertFalse(self.policy["frozen"])
        # In-memory synthetic verification; the on-disk scientific policy remains unfrozen.
        self.policy["frozen"] = True
        self.network_guard = patch.object(socket, "socket", side_effect=AssertionError("No network"))
        self.network_guard.start()
        self.addCleanup(self.network_guard.stop)

    def reference(self, case):
        reference = copy.deepcopy(BASIC)
        reference["assay_run"] = [
            {**reference["assay_run"][0], "assay_id": "A" + str(i),
             "experiment_run_accession": "Synthetic:shared (project)",
             "method": "Synthetic procedure; native identifier: " + label + ". Synthetic protocol."}
            for i, label in enumerate(LABELS[case])
        ]
        return reference

    def evaluate(self, prediction, reference, case, policy=None):
        return score(prediction, reference, dictionary(reference), policy or self.policy,
                     context={"case_id": case})

    def test_reordered_experiments_and_renamed_internal_ids_remain_correct(self):
        for case in LABELS:
            with self.subTest(case=case):
                reference = self.reference(case)
                prediction = copy.deepcopy(reference)
                prediction["assay_run"].reverse()
                prediction["sample"][0]["sample_id"] = "renamed-sample"
                prediction["condition"][0].update(condition_id="renamed-condition", sample_id="renamed-sample")
                for i, row in enumerate(prediction["assay_run"]):
                    row.update(assay_id="renamed-" + str(i), sample_ids=["renamed-sample"])
                before = copy.deepcopy((prediction, reference))
                result = self.evaluate(prediction, reference, case)
                self.assertEqual(result["pairs"]["assay_run"],
                                 [{"prediction": 0, "gold": 1}, {"prediction": 1, "gold": 0}])
                self.assertEqual(result["field"]["f1"], 1)
                self.assertEqual(result["record"]["f1"], 1)
                self.assertEqual((prediction, reference), before)

    def test_identity_does_not_hide_wrong_sample_link_or_platform(self):
        for case in LABELS:
            with self.subTest(case=case):
                reference = self.reference(case)
                prediction = copy.deepcopy(reference)
                prediction["assay_run"][0].update(sample_ids=["UNKNOWN"], platform="Wrong synthetic instrument")
                result = self.evaluate(prediction, reference, case)
                self.assertEqual(len(result["pairs"]["assay_run"]), 2)
                for field in ("sample_ids", "platform"):
                    self.assertFalse(result["gold_field_correctness"]["assay_run:0:" + field])
                self.assertEqual(result["record"]["gold"] - result["record"]["tp"], 1)

    def test_native_label_does_not_grant_partial_method_credit(self):
        for case in LABELS:
            with self.subTest(case=case):
                reference = self.reference(case)
                prediction = copy.deepcopy(reference)
                prediction["assay_run"][0]["method"] += " Contradictory synthetic procedure."
                result = self.evaluate(prediction, reference, case)
                self.assertEqual(len(result["pairs"]["assay_run"]), 2)
                self.assertFalse(result["gold_field_correctness"]["assay_run:0:method"])
                items = result["scoring_items"]["assay_run"]["prediction"][0]["items"]
                self.assertIn("method", items)
                self.assertFalse(any(key.startswith("method.") for key in items))
                self.assertEqual(result["field"]["gold"] - result["field"]["tp"], 1)

    def test_different_wording_matches_identity_and_retains_whole_field_review(self):
        for case in LABELS:
            with self.subTest(case=case):
                reference = self.reference(case)
                prediction = copy.deepcopy(reference)
                prediction["assay_run"][0]["method"] = "Other wording for synthetic protocol; " + LABELS[case][0]
                result = self.evaluate(prediction, reference, case)
                self.assertEqual(len(result["pairs"]["assay_run"]), 2)
                self.assertTrue(any(q["kind"] == "text_equivalence" and q["field"] == "method"
                                    for q in result["adjudication_queue"]))

    def test_absent_ambiguous_or_partial_labels_remain_pending(self):
        for case, labels in LABELS.items():
            for method in ("Synthetic method without a native identifier",
                           labels[0] + "; " + labels[1], labels[0] + ".backup"):
                with self.subTest(case=case, method=method):
                    reference = self.reference(case)
                    prediction = copy.deepcopy(reference)
                    prediction["assay_run"][0]["method"] = method
                    result = self.evaluate(prediction, reference, case)
                    self.assertNotIn({"prediction": 0, "gold": 0}, result["pairs"]["assay_run"])
                    self.assertTrue(any(q["kind"] == "record_identity" and q["table"] == "assay_run"
                                        for q in result["adjudication_queue"]))

    def test_rules_are_task_scoped_and_cannot_override_conflicting_object_accessions(self):
        for case in LABELS:
            with self.subTest(case=case):
                reference = self.reference(case)
                self.assertEqual(self.evaluate(reference, reference, "B001")["pairs"]["assay_run"], [])
                prediction = copy.deepcopy(reference)
                reference["assay_run"][0]["experiment_run_accession"] = "Synthetic:run-A (run)"
                prediction["assay_run"][0]["experiment_run_accession"] = "Synthetic:run-B (run)"
                result = self.evaluate(prediction, reference, case)
                self.assertNotIn({"prediction": 0, "gold": 0}, result["pairs"]["assay_run"])

    def test_case_context_and_separate_scientific_freeze_are_required(self):
        reference = self.reference("B902")
        with self.assertRaisesRegex(ValueError, "explicit case"):
            score(reference, reference, dictionary(reference), self.policy)
        draft = read(ROOT / "configs/tasks/biotracebench-scoring-v2.json")
        with self.assertRaisesRegex(ValueError, "Freeze"):
            self.evaluate(reference, reference, "B902", draft)


if __name__ == "__main__":
    unittest.main()
