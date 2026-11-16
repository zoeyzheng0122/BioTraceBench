"""Public-input boundaries and exact submissions using synthetic providers."""
import copy
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from biotracebench.common import Stop, read, write, verify, sha
from biotracebench.dataset_identity import capture, task_sources, verify_prepared
from biotracebench.materials import prepare, Reader
from biotracebench.schema import validate
from biotracebench.export import database, run_report
from model_conversation import Adapter, Conversation
from model_conversation.archive import exact_json, read_exact, encoded, digest, DuplicateJSONKey
from test_biotracebench import source_fixture, ANSWER
import test_biotracebench_conditions as condition_fixtures


class TaskSourceTests(unittest.TestCase):
    def test_declared_manifest_html_and_public_hashes_without_pdf_or_gold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/"dataset"
            materials = source_fixture(root)
            manifest = read(materials/"materials.json")
            (materials/"article.html").write_text("<html><body><p>Complete synthetic main article.</p></body></html>")
            manifest["files"][0].update(role="main_html", path="article.html",
                                        bytes=(materials/"article.html").stat().st_size, sha256=sha(materials/"article.html"))
            target = root/"metadata/manifests/basic/B001.json"
            write(target, manifest)
            (materials/"materials.json").unlink()
            task_file = root/"tasks/basic/B001/task.json"
            task = read(task_file)
            task.update(materials_manifest="../../../metadata/manifests/basic/B001.json",
                        schema="../../../schemas/basic-three.schema.json",
                        field_dictionary="../../../schemas/field-dictionary.json", complete_prompt="complete-prompt.md")
            write(task_file, task)
            original = Path.open
            def guarded(path, *args, **kwargs):
                if path.suffix.lower() == ".pdf" or "gold_standard" in path.parts:
                    raise AssertionError("Forbidden input opened")
                return original(path, *args, **kwargs)
            with patch.object(Path, "open", guarded):
                report = prepare(root, "B001", Path(tmp)/"prepared")
                before = capture(root, "B001", "basic")
                self.assertEqual(report["status"], "ready_offline")
                self.assertEqual(report["manifest_path"], "metadata/manifests/basic/B001.json")
                self.assertIn("metadata/manifests/basic/B001.json", before["task_files"])
                verify_prepared(Reader(Path(tmp)/"prepared"), live_sources=True)
                manifest["description"] = "changed declaration"
                write(target, manifest)
                with self.assertRaises(Stop):
                    verify_prepared(Reader(Path(tmp)/"prepared"), live_sources=True)
                for invalid in ("../../../gold_standard/basic/B001/B001.json",
                                "../../../metadata/manifests/basic/B002.json", "missing.json", "/tmp/manifest.json"):
                    task["materials_manifest"] = invalid
                    write(task_file, task)
                    with self.assertRaises(Stop):
                        task_sources(root, "B001", "basic")


class FidelityTests(unittest.TestCase):
    def test_exact_decimal_encoding_and_duplicate_detection(self):
        text = '{"中文":[0,0.123456789012345678901,1e-400,1e400]}'
        value = exact_json(text)
        self.assertEqual(exact_json(encoded(value)), value)
        self.assertEqual(validate(value["中文"][2], {"type": "number"}), [])
        self.assertEqual(validate(value["中文"][3], {"type": "number"}), [])
        self.assertEqual(encoded({"x": 0.5, "z": None}), b'{"x":0.5,"z":null}')
        for invalid in ('{"x":1,"x":2}', '{"x":{"y":0,"y":1}}'):
            with self.assertRaises(DuplicateJSONKey):
                exact_json(invalid)
        for invalid in ('{"x":NaN}', '{"x":Infinity}'):
            with self.assertRaises(ValueError):
                exact_json(invalid)

    def execute_fixture(self, payload, inspect):
        case = condition_fixtures.ConditionTests()
        case.setUp()
        try:
            case.manifest()
            def sender(*args):
                return case.provider(*args) if "estimate" in args[0] else case.response(payload)
            result = case.execute(sender)
            inspect(case, result)
        finally:
            case.tearDown()

    def test_long_number_survives_final_forks_replay_and_exports(self):
        answer = copy.deepcopy(ANSWER)
        number = Decimal("0.123456789012345678901")
        answer["condition"][0]["factor_value"] = number
        payload = encoded({"database": answer, "annotations": []}).decode()
        def inspect(case, result):
            self.assertIsNone(result["failure"])
            for stage in ("i0", "gsr", "ssr"):
                final = case.out/"B001"/stage/"final"
                self.assertEqual((final/"raw-answer.txt").read_text(), payload)
                saved = read_exact(final/"database.json")
                self.assertEqual(saved["condition"][0]["factor_value"], number)
                self.assertEqual(read_exact(final/"snapshot.json")["database"], saved)
                database(saved, case.root/(stage+"-export"))
                self.assertIn(str(number), (case.root/(stage+"-export")/"condition.csv").read_text())
                verify(final)
            count = case.provider.completions
            case.execute(offline=True)
            self.assertEqual(case.provider.completions, count)
            run_report(case.out, case.root/"report")
            self.assertEqual(read(case.out/"B001/gsr/branch.json")["i0_history_sha256"],
                             read(case.out/"B001/ssr/branch.json")["i0_history_sha256"])
        self.execute_fixture(payload, inspect)

    def test_duplicate_field_is_archived_as_ambiguous_not_last_value(self):
        payload = json.dumps({"database": ANSWER, "annotations": []}).replace('"factor_value": 0', '"factor_value": 99, "factor_value": 0')
        def inspect(case, result):
            final = case.out/"B001/i0/final"
            self.assertIsNone(read(final/"database.json"))
            self.assertEqual((final/"raw-answer.txt").read_text(), payload)
            self.assertIn({"error": "duplicate_json_key"}, read(final/"diagnostics.json"))
            self.assertFalse(read(final/"output-assessment.json")["json_parseable"])
            self.assertFalse(read(final/"output-assessment.json")["delivery_contract_valid"])
            self.assertEqual(read(final/"output-assessment.json")["delivery_contract_errors"],
                             [{"error": "duplicate_json_key"}])
            verify(final)
        self.execute_fixture(payload, inspect)




if __name__ == "__main__":
    unittest.main()
