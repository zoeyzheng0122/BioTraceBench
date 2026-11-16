"""External-package verification uses only generated scientific and review fixtures."""
from collections import Counter
from pathlib import Path
from zipfile import ZipFile
import gzip
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest

from biotracebench_analysis.publication.verification import (
    MANIFEST, NAVIGATION, digest, verify_file_manifest, verify_materials,
)

ROOT = Path(__file__).resolve().parents[1]

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n")

def seal(root):
    files = [{"path": str(path.relative_to(root)), "size": path.stat().st_size,
              "sha256": digest(path)}
             for path in sorted(root.rglob("*")) if path.is_file()
             and str(path.relative_to(root)) not in {MANIFEST, "SHA256SUMS"}]
    write(root / MANIFEST, {"files": files, "stages": ["i0"]})
    (root / "SHA256SUMS").write_text(digest(root / MANIFEST) + "  " + MANIFEST + "\n")

def fixture(root):
    repro = root / "04_Reproducibility"
    materials = root / "03_Benchmark_Data/01_Task_Materials"
    inventory = {"rows": [{"id": "p0", "side": "prediction", "table": "object", "row_index": 0}],
                 "cells": [{"row": "p0", "side": "prediction", "present": True,
                            "field": "value", "value_json": "2"}]}
    positions = []
    for model, case, status in [
        ("synthetic-alpha", "B001", "parseable_database"),
        ("synthetic-alpha", "C001", "parseable_database"),
        ("synthetic-beta", "B001", "partial_raw_text"),
        ("synthetic-beta", "C001", "terminal_zero"),
    ]:
        positions.append({"model": model, "case": case, "stage": "i0", "status": status})
        if status == "terminal_zero":
            continue
        folder = root / "03_Benchmark_Data/02_Model_Outputs" / model / case
        folder.mkdir(parents=True)
        (folder / "raw-answer.txt").write_text("Synthetic original answer.\n")
        write(folder / "database.json", {"object": [{"value": 2}]} if status == "parseable_database" else None)
        packet = repro / "02_Published_Evaluation/projection/judgments" / model / "i0" / (case + ".json.gz")
        packet.parent.mkdir(parents=True, exist_ok=True)
        packet.write_bytes(gzip.compress(json.dumps({"inventory": inventory}).encode()))
    for case in ("B001", "C001"):
        domain = "basic" if case.startswith("B") else "clinical"
        reference = {"object": [{"value": 2}]}
        write(repro / "02_Published_Evaluation/projection/references" / (case + ".json"), reference)
        write(materials / "gold_standard" / domain / case / (case + ".json"), reference)
        write(materials / "tasks" / domain / case / "task.json", {"case": case, "synthetic": True})
    (materials / "source.txt").write_text("Synthetic source evidence.\n")
    write(materials / "metadata/sources.json",
          {"files": [{"path": "source.txt", "sha256": digest(materials / "source.txt")}]})
    review = repro / "04_Human_Review"
    for name in ("reviewer_A.json", "reviewer_B.json"):
        write(review / name, {"answers": [{"answer_id": "SYNTHETIC", "review": "correct"}]})
    write(review / "01_Analysis/analysis_parameters.json", {"outputs": 1})
    write(repro / "06_Verification/version_binding.json",
          {"stage": "i0", "positions": 4, "models": 2, "tasks": 2})
    write(root / "03_Benchmark_Data/03_Evaluation_Results/output_status.json", {"positions": positions})
    write(root / "release_manifest.json", {
        "stages": ["i0"], "positions_per_stage": 4,
        "raw_outputs": dict(Counter(item["status"] for item in positions)),
        "output_status": "03_Benchmark_Data/03_Evaluation_Results/output_status.json",
        "task_materials": "03_Benchmark_Data/01_Task_Materials",
    })
    manuscript = root / "01_Manuscript/Synthetic.docx"
    manuscript.parent.mkdir(parents=True)
    with ZipFile(manuscript, "w") as archive:
        archive.writestr("word/document.xml", "<synthetic/>")
    for name in NAVIGATION:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<p>Synthetic navigation</p>" if path.suffix == ".html" else "# Synthetic navigation\n")
    seal(root)

class MaterialVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "materials with spaces λ"
        self.root.mkdir()
        fixture(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def edit_json(self, name, update):
        path = self.root / name
        value = json.loads(path.read_text())
        update(value)
        write(path, value)
        seal(self.root)

    def test_package_without_supplement_passes(self):
        result = verify_materials(self.root)
        self.assertEqual(result["positions"], 4)
        self.assertEqual(result["parseable_databases"], 2)
        self.assertEqual(result["partial_raw_texts"], 1)
        self.assertEqual(result["terminal_zeros"], 1)
        self.assertEqual(result["prediction_cells_reconciled"], 2)

    def test_explicitly_required_supplement_is_not_silently_ignored(self):
        path = self.root / "01_Manuscript/Supplementary_Material.docx"
        path.write_bytes(b"synthetic")
        seal(self.root)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "Required file missing"):
            verify_materials(self.root)

    def test_changed_hash_fails(self):
        path = self.root / "03_Benchmark_Data/02_Model_Outputs/synthetic-alpha/B001/database.json"
        path.write_text(path.read_text().replace("2", "3"))
        with self.assertRaisesRegex(ValueError, "File hash differs"):
            verify_materials(self.root)

    def test_missing_required_file_fails(self):
        (self.root / "03_Benchmark_Data/01_Task_Materials/source.txt").unlink()
        with self.assertRaisesRegex(ValueError, "Required file missing"):
            verify_materials(self.root)

    def test_checksum_anchor_fails(self):
        (self.root / "SHA256SUMS").write_text("0" * 64 + "  " + MANIFEST + "\n")
        with self.assertRaisesRegex(ValueError, "Checksum anchor differs"):
            verify_materials(self.root)

    def test_incomplete_grid_fails_even_after_resealing(self):
        self.edit_json("03_Benchmark_Data/03_Evaluation_Results/output_status.json",
                       lambda value: value["positions"].pop())
        with self.assertRaisesRegex(ValueError, "position coverage differs"):
            verify_materials(self.root)

    def test_duplicate_position_fails_even_after_resealing(self):
        def duplicate(value):
            value["positions"][1] = value["positions"][0]
        self.edit_json("03_Benchmark_Data/03_Evaluation_Results/output_status.json", duplicate)
        with self.assertRaisesRegex(ValueError, "Duplicate model-output"):
            verify_materials(self.root)

    def test_database_inventory_mismatch_fails_after_resealing(self):
        self.edit_json("03_Benchmark_Data/02_Model_Outputs/synthetic-alpha/B001/database.json",
                       lambda value: value["object"][0].update(value=3))
        with self.assertRaisesRegex(ValueError, "Database value differs"):
            verify_materials(self.root)

    def test_source_identity_is_independently_checked(self):
        self.edit_json("03_Benchmark_Data/01_Task_Materials/metadata/sources.json",
                       lambda value: value["files"][0].update(sha256="0" * 64))
        with self.assertRaisesRegex(ValueError, "Scientific source hash differs"):
            verify_materials(self.root)

    def test_reference_versions_must_match(self):
        self.edit_json("03_Benchmark_Data/01_Task_Materials/gold_standard/basic/B001/B001.json",
                       lambda value: value["object"][0].update(value=3))
        with self.assertRaisesRegex(ValueError, "Reference versions differ"):
            verify_materials(self.root)

    def test_review_sample_coverage_checked(self):
        self.edit_json("04_Reproducibility/04_Human_Review/reviewer_A.json",
                       lambda value: value.update(answers=[]))
        with self.assertRaisesRegex(ValueError, "Human-review sample coverage"):
            verify_materials(self.root)

    def test_broken_navigation_checked(self):
        (self.root / "README.md").write_text("[Missing](missing.md)")
        seal(self.root)
        with self.assertRaisesRegex(ValueError, "Broken material link"):
            verify_materials(self.root)

    def test_manifest_cannot_leave_material_directory(self):
        with self.assertRaisesRegex(ValueError, "Invalid material path"):
            verify_file_manifest(self.root, {"files": [{"path": "../private", "size": 0, "sha256": "0" * 64}]})

    def test_cli_handles_relocated_materials(self):
        raw = subprocess.check_output(
            [sys.executable, "-B", str(ROOT / "scripts/verify_materials.py"),
             "--artifact-root", str(self.root)], text=True, cwd=self.temporary.name)
        self.assertEqual(json.loads(raw)["status"], "passed")

if __name__ == "__main__":
    unittest.main()
