"""Read-only rule preparation with synthetic task packages only."""
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from model_conversation.archive import read, verify
from biotracebench_scoring.rule_audit import Inputs, audit, paper_text, reference_observations


class RuleAuditTests(unittest.TestCase):
    def fixture(self, base):
        root = base / "dataset"
        def put(path, value):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value), encoding="utf-8")
        paper = base / "paper.docx"
        with zipfile.ZipFile(paper, "w") as z:
            z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Accepted</w:t></w:r><w:del><w:r><w:t>Deleted</w:t></w:r></w:del><w:ins><w:r><w:t>Inserted</w:t></w:r></w:ins></w:p></w:body></w:document>')
        policy = base / "policy.json"
        put(policy, {"frozen": False, "current_authority": {"sha256": hashlib.sha256(paper.read_bytes()).hexdigest()},
                     "identity_groups": {"sample": [["label"]]}})
        spec = {"sample": {"identifier": "id", "fields": [{"key": "id"}, {"key": "label"}, {"key": "value"}]}}
        schema = {"type": "object", "required": ["sample"], "additionalProperties": False, "properties": {
            "sample": {"type": "array", "items": {"type": "object", "additionalProperties": False,
            "required": ["id", "label", "value"], "properties": {"id": {"type": "string"},
            "label": {"type": "string"}, "value": {"type": ["number", "null"]}}}}}}
        put(root / "schemas/basic.schema.json", schema)
        put(root / "schemas/field-dictionary.json", {"basic": spec})
        case = root / "tasks/basic/B001"
        put(case / "task.json", {"case_id": "B001", "domain": "basic", "doi": "synthetic",
             "schema": "../../../schemas/basic.schema.json", "field_dictionary": "../../../schemas/field-dictionary.json",
             "materials_manifest": "../../../metadata/manifests/basic/B001.json",
             "case_rules": "Retain conflicting source statements.", "row_granularity": "One source-defined material."})
        (case / "prompt.md").write_text("Synthetic scope. No rounding is permitted.", encoding="utf-8")
        (case / "complete-prompt.md").write_text("```json\n" + json.dumps(schema) + "\n```", encoding="utf-8")
        put(root / "metadata/manifests/basic/B001.json", {"files": [
            {"input_use": "model", "path": "a.PDF", "format": ".pdf", "role": "main_pdf"},
            {"input_use": "model", "path": "a.html", "format": ".html"}]})
        put(root / "gold_standard/basic/B001/B001.json", {"sample": [{"id": "S", "label": "Preparation", "value": None}]})
        return root, policy, paper, schema, spec

    def test_inspection_never_calls_provider_or_opens_materials_or_freezes(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root, policy, paper, _, _ = self.fixture(base)
            before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
            policy_before = policy.read_bytes()
            original = Path.open
            def guarded(path, *args, **kwargs):
                if path.suffix.lower() == ".pdf" or "materials" in path.parts:
                    raise AssertionError("Forbidden material read")
                return original(path, *args, **kwargs)
            with patch.object(Path, "open", guarded), patch("socket.socket", side_effect=AssertionError("No network")):
                result = audit(root, policy, paper, base / "audit", 1)
            self.assertEqual(result["summary"]["null_fields"], 1)
            self.assertEqual(result["summary"]["excluded_pdf_files"], 1)
            self.assertEqual(result["summary"]["embedded_schema_status"], {"matches": 1})
            self.assertFalse(result["summary"]["frozen"])
            self.assertEqual(policy.read_bytes(), policy_before)
            self.assertTrue(all(p.read_bytes() == v for p, v in before.items()))
            task = read(base / "audit/task-rule-drafts.json")[0]
            self.assertEqual(task["approval"]["identity"], None)
            self.assertIn("case_rules", {r["json_key"] for r in task["case_declarations"]})
            self.assertEqual(task["observations"]["null_fields"][0]["state"], "undetermined")
            self.assertTrue(all(q["answer"] is None for q in read(base / "audit/confirmation-queue.json")))
            verify(base / "audit")

    def test_material_inventory_includes_supplement_pdf_without_reading_it(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root, policy, paper, _, _ = self.fixture(base)
            manifest_path = root / "metadata/manifests/basic/B001.json"
            manifest = read(manifest_path)
            manifest["files"].append({"path": "supplement.pdf", "input_use": "model", "role": "supplement"})
            manifest_path.write_text(json.dumps(manifest))
            result = audit(root, policy, paper, base / "audit", 1)
            self.assertEqual(result["summary"]["included_pdf_files"], 1)
            self.assertEqual(result["summary"]["excluded_pdf_files"], 1)
            task = read(base / "audit/task-rule-drafts.json")[0]
            self.assertEqual(task["material_scope"]["included_pdf_files"], ["supplement.pdf"])
            self.assertFalse(task["material_scope"]["contents_read"])

    def test_blocked_reference_is_retained_and_audit_cannot_claim_coverage(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root, policy, paper, _, _ = self.fixture(base)
            (root / "gold_standard/basic/B001/B001.json").unlink()
            result = audit(root, policy, paper, base / "audit", 1)
            self.assertEqual(result["status"], "incomplete")
            self.assertEqual(result["failures"][0]["case_id"], "B001")
            self.assertEqual(result["inspected_tasks"], 0)

    def test_source_path_alias_preserves_canonical_implementation_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root, policy, paper, _, _ = self.fixture(base)
            source_root = Path(__file__).resolve().parents[1]
            alias = base / "source-alias"
            alias.symlink_to(source_root, target_is_directory=True)
            module_path = alias / "src/biotracebench_scoring/rule_audit.py"
            with patch("biotracebench_scoring.rule_audit.__file__", str(module_path)):
                result = audit(root, policy, paper, base / "audit", 1)
            self.assertEqual(result["inspected_tasks"], 1)
            implementation = read(base / "audit/identity.json")["implementation"]
            self.assertEqual(implementation["src/biotracebench_scoring/rule_audit.py"],
                             hashlib.sha256(module_path.read_bytes()).hexdigest())
            self.assertTrue(all(name.startswith("src/") and ".." not in Path(name).parts
                                for name in implementation))
            verify(base / "audit")

    def test_rejects_wrong_inventory_authority_and_frozen_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root, policy, paper, _, _ = self.fixture(base)
            with self.assertRaisesRegex(ValueError, "inventory"):
                audit(root, policy, paper, base / "count", 100)
            value = read(policy)
            value["current_authority"]["sha256"] = "0" * 64
            policy.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "authority"):
                audit(root, policy, paper, base / "authority", 1)
            value["frozen"] = True
            policy.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "unfrozen"):
                audit(root, policy, paper, base / "frozen", 1)

    def test_duplicate_json_and_pdf_reads_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            p = base / "input.json"
            p.write_text('{"a": 1, "a": 2}')
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                Inputs().json(p)
            with self.assertRaisesRegex(ValueError, "unsupported"):
                Inputs().read(base / "never.PDF")

    def test_zero_missing_and_null_are_distinct_and_duplicates_remain_candidates(self):
        with tempfile.TemporaryDirectory() as temp:
            _, _, _, schema, spec = self.fixture(Path(temp))
            gold = {"sample": [{"id": "A", "label": "L", "value": 0},
                               {"id": "B", "label": "L", "value": 0},
                               {"id": "C", "label": "M", "value": None},
                               {"id": "D", "label": "N"}]}
            observed = reference_observations(gold, spec, schema, {"identity_groups": {"sample": [["label"]]}})
            self.assertEqual(len(observed["genuine_zero_fields"]), 2)
            self.assertEqual(len(observed["null_fields"]), 1)
            self.assertEqual(len(observed["missing_fields"]), 1)
            self.assertEqual(observed["duplicate_record_candidates"][0]["row_indices"], [0, 1])
            self.assertEqual(observed["identity_candidates"]["sample"]["groups"][0]["colliding_rows"], [[0, 1]])

    def test_manuscript_accepts_insertions_and_excludes_deletions(self):
        with tempfile.TemporaryDirectory() as temp:
            _, _, paper, _, _ = self.fixture(Path(temp))
            self.assertEqual(paper_text(paper.read_bytes()), "AcceptedInserted")


if __name__ == "__main__":
    unittest.main()
