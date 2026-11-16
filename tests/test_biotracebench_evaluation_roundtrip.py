"""Synthetic scoring invariants, including the actual prepare/save/read path."""
import copy
import itertools
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from biotracebench.common import read, sha, write
from biotracebench_scoring.evaluation import score
from biotracebench.materials import prepare


POLICY = {"version": "biotracebench-score-1", "frozen": True,
          "field_rules": {}, "identity_fields": {}}


def table(identifier, fields, references=None):
    return {"identifier": identifier, "fields": [{"key": key} for key in fields],
            "references": references or {}}


BASIC = {
    "sample": table("sample_id", ["sample_id", "sample_name", "species"]),
    "condition": table("condition_id", ["condition_id", "sample_id", "experimental_factor", "factor_value"],
                       {"sample_id": "sample"}),
    "assay_run": table("assay_id", ["assay_id", "sample_ids", "assay_type"], {"sample_ids": "sample"}),
}
BASIC_ANSWER = {
    "sample": [{"sample_id": "s1", "sample_name": "细胞 A", "species": "human"},
               {"sample_id": "s2", "sample_name": "细胞 B", "species": "mouse"}],
    "condition": [{"condition_id": "c1", "sample_id": "s1", "experimental_factor": "dose", "factor_value": 0}],
    "assay_run": [{"assay_id": "a1", "sample_ids": ["s1", "s2"], "assay_type": "RNA-seq"}],
}
CLINICAL = {
    "population": table("population_id", ["population_id", "population_name", "population_size"]),
    "measure": table("measure_id", ["measure_id", "measure_name"]),
    "result": table("result_id", ["result_id", "population_id", "measure_id", "result_value", "comparison"],
                    {"population_id": "population", "measure_id": "measure"}),
    "population_relation": table(None, ["population_a_id", "population_b_id", "relationship"],
                                 {"population_a_id": "population", "population_b_id": "population"}),
}
CLINICAL_ANSWER = {
    "population": [{"population_id": "p1", "population_name": "Treatment", "population_size": 0},
                   {"population_id": "p2", "population_name": "Control", "population_size": 10}],
    "measure": [{"measure_id": "m1", "measure_name": "Outcome A"},
                {"measure_id": "m2", "measure_name": "Outcome B"}],
    "result": [{"result_id": "r1", "population_id": "p1", "measure_id": "m1", "result_value": 0,
                "comparison": "p1 vs p2"},
               {"result_id": "r2", "population_id": "p2", "measure_id": "m2", "result_value": 10,
                "comparison": "p2 vs p1"}],
    "population_relation": [{"population_a_id": "p1", "population_b_id": "p2", "relationship": "disjoint from"}],
}


class ScoringRoundtripTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="biotracebench-score-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.network = patch.object(socket, "create_connection", side_effect=AssertionError("Offline tests only"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def prepared_dictionary(self, domain, dictionary, answer):
        case = "B001" if domain == "basic" else "C001"
        source = self.root / domain
        task = source / "tasks" / domain / case
        material = source / "materials" / domain / case
        task.mkdir(parents=True)
        material.mkdir(parents=True)
        (source / "schemas").mkdir()
        write(task / "task.json", {"case_id": case, "domain": domain, "doi": "10.synthetic/s01-" + domain})
        (task / "complete-prompt.md").write_text("Synthetic scoring fixture; count is 0. 中文。", encoding="utf-8")
        text = material / "article.xml"
        text.write_text("<article>Synthetic material only; count is 0. 中文。</article>", encoding="utf-8")
        write(material / "materials.json", {"case": {"case_id": case}, "files": [
            {"path": text.name, "input_use": "model", "role": "main", "bytes": text.stat().st_size, "sha256": sha(text)}]})
        schema_name = "basic-three.schema.json" if domain == "basic" else "clinical-four-compact.schema.json"
        write(source / "schemas" / schema_name, {"type": "object", "required": list(answer),
              "properties": {name: {"type": "array", "items": {"type": "object"}} for name in answer},
              "additionalProperties": False})
        # Keep insertion order at the input; prepare uses the real sorted archive writer.
        (source / "schemas/field-dictionary.json").write_text(json.dumps({domain: dictionary}), encoding="utf-8")
        source_bytes = {p: p.read_bytes() for p in source.rglob("*") if p.is_file()}
        output = self.root / (domain + "-prepared")
        prepare(source, case, output)
        self.assertEqual(source_bytes, {p: p.read_bytes() for p in source_bytes})
        saved = read(output / "dictionary.json")
        self.assertEqual(list(saved), sorted(dictionary))
        return saved

    def assert_full_credit(self, result):
        for level in ("field", "record"):
            for metric in ("precision", "recall", "f1"):
                self.assertEqual(result[level][metric], 1.0, (level, metric, result))

    def test_prepare_roundtrip_basic(self):
        dictionary = self.prepared_dictionary("basic", BASIC, BASIC_ANSWER)
        inputs = copy.deepcopy((BASIC_ANSWER, dictionary, POLICY))
        self.assert_full_credit(score(BASIC_ANSWER, BASIC_ANSWER, dictionary, POLICY))
        self.assertEqual((BASIC_ANSWER, dictionary, POLICY), inputs)

    def test_prepare_roundtrip_clinical(self):
        dictionary = self.prepared_dictionary("clinical", CLINICAL, CLINICAL_ANSWER)
        self.assert_full_credit(score(CLINICAL_ANSWER, CLINICAL_ANSWER, dictionary, POLICY))

    def test_basic_table_and_row_order_and_ids(self):
        renamed = {
            "sample": [{"sample_id": "z", "sample_name": "细胞 B", "species": "mouse"},
                       {"sample_id": "x", "sample_name": "细胞 A", "species": "human"}],
            "condition": [{"condition_id": "q", "sample_id": "x", "experimental_factor": "dose", "factor_value": 0}],
            "assay_run": [{"assay_id": "t", "sample_ids": ["z", "x"], "assay_type": "RNA-seq"}],
        }
        for order in itertools.permutations(BASIC):
            with self.subTest(order=order):
                self.assert_full_credit(score(renamed, BASIC_ANSWER, {key: BASIC[key] for key in order}, POLICY))

    def test_clinical_table_and_row_order_and_ids(self):
        renamed = {
            "population": [{"population_id": "y", "population_name": "Control", "population_size": 10},
                           {"population_id": "x", "population_name": "Treatment", "population_size": 0}],
            "measure": [{"measure_id": "b", "measure_name": "Outcome B"},
                        {"measure_id": "a", "measure_name": "Outcome A"}],
            "result": [{"result_id": "v", "population_id": "y", "measure_id": "b", "result_value": 10,
                        "comparison": "y vs x"},
                       {"result_id": "u", "population_id": "x", "measure_id": "a", "result_value": 0,
                        "comparison": "x vs y"}],
            "population_relation": [{"population_a_id": "y", "population_b_id": "x", "relationship": "disjoint from"}],
        }
        for order in itertools.permutations(CLINICAL):
            with self.subTest(order=order):
                self.assert_full_credit(score(renamed, CLINICAL_ANSWER, {key: CLINICAL[key] for key in order}, POLICY))

    def test_transitive_dependency(self):
        dictionary, answer = copy.deepcopy(BASIC), copy.deepcopy(BASIC_ANSWER)
        dictionary["assay_run"]["fields"].append({"key": "condition_id"})
        dictionary["assay_run"]["references"]["condition_id"] = "condition"
        answer["assay_run"][0]["condition_id"] = "c1"
        dictionary = self.prepared_dictionary("basic", dictionary, answer)
        self.assert_full_credit(score(answer, answer, dictionary, POLICY))

    def test_wrong_and_dangling_relationships_still_lose_credit(self):
        for dictionary, answer, table_name, field, wrong_ids in (
            (BASIC, BASIC_ANSWER, "condition", "sample_id", ("s2", "not-present")),
            (CLINICAL, CLINICAL_ANSWER, "result", "population_id", ("p2", "not-present")),
        ):
            dictionary = json.loads(json.dumps(dictionary, sort_keys=True))
            baseline = score(answer, answer, dictionary, POLICY)
            for target in wrong_ids:
                with self.subTest(table=table_name, target=target):
                    wrong = copy.deepcopy(answer)
                    wrong[table_name][0][field] = target
                    result = score(wrong, answer, dictionary, POLICY)
                    self.assertEqual(result["field"]["tp"], baseline["field"]["tp"] - 1)
                    self.assertEqual(result["record"]["tp"], baseline["record"]["tp"] - 1)

    def test_duplicates_and_missing_rows_not_hidden(self):
        dictionary = json.loads(json.dumps(BASIC, sort_keys=True))
        duplicate = copy.deepcopy(BASIC_ANSWER)
        duplicate["condition"].append(copy.deepcopy(duplicate["condition"][0]))
        result = score(duplicate, BASIC_ANSWER, dictionary, POLICY)
        self.assertLess(result["field"]["precision"], 1)
        self.assertLess(result["record"]["precision"], 1)
        missing = copy.deepcopy(BASIC_ANSWER)
        missing["condition"] = []
        result = score(missing, BASIC_ANSWER, dictionary, POLICY)
        self.assertLess(result["field"]["recall"], 1)
        self.assertLess(result["record"]["recall"], 1)

    def test_identity_ambiguity_remains_provisional(self):
        answer = {"sample": [{"sample_id": "s1", "sample_name": "same"},
                             {"sample_id": "s2", "sample_name": "same"}]}
        prediction = {"sample": [{"sample_id": "x", "sample_name": "same"}]}
        result = score(prediction, answer, {"sample": BASIC["sample"]}, POLICY)
        self.assertEqual(result["status"], "provisional")
        self.assertTrue(any(row["kind"] == "record_identity" for row in result["adjudication_queue"]))

    def test_missing_reference_table_rejected(self):
        dictionary = copy.deepcopy(BASIC)
        del dictionary["sample"]
        with self.assertRaisesRegex(ValueError, "Unknown reference target.*sample"):
            score({}, {}, dictionary, POLICY)

    def test_reference_target_without_identifier_rejected(self):
        dictionary = copy.deepcopy(BASIC)
        dictionary["sample"]["identifier"] = None
        with self.assertRaisesRegex(ValueError, "Reference target.*sample.*identifier"):
            score({}, {}, dictionary, POLICY)

    def test_cyclic_dependencies_require_explicit_alignment(self):
        for target in ("sample", "condition"):
            with self.subTest(target=target):
                dictionary = copy.deepcopy(BASIC)
                dictionary["sample"]["references"]["parent_id"] = target
                with self.assertRaisesRegex(ValueError, "Cyclic table references.*explicit.*alignment"):
                    score({}, {}, dictionary, POLICY)


if __name__ == "__main__":
    unittest.main()
