"""Declared material selection and complete page delivery; no live API or gold."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import test_biotracebench_conditions as fixtures
from pdf_fixtures import pdf_bytes, encrypted_pdf_bytes
from biotracebench.common import Stop, digest, read, seal, sha, write
from biotracebench.material_selection import PDF_POLICY, select_materials
from biotracebench.pdf_material import RENDERING, prepare_pdf
from biotracebench.materials import prepare, Reader
from biotracebench import dataset_identity, inputs


def item(path, role="supplement", **kwargs):
    return {"path": path, "role": role, "input_use": "model", **kwargs}


class SelectionTests(unittest.TestCase):
    def test_main_xml_then_html_and_publisher_pdf_exclusion(self):
        files = [item("article.pdf", "main_pdf"), item("article.xml", "main"),
                 item("article.html", "main_html"), item("publisher.pdf", "source_version"),
                 item("supplement.pdf")]
        selected, excluded = select_materials(files)
        self.assertEqual([f["path"] for f in selected], ["article.xml", "supplement.pdf"])
        self.assertEqual({f["path"]: f["reason"] for f in excluded}, {
            "article.pdf": "main_article_pdf", "article.html": "preferred_representation", "publisher.pdf": "main_article_pdf"})
        selected, _ = select_materials([f for f in files if f["path"] != "article.xml"])
        self.assertEqual([f["path"] for f in selected], ["article.html", "supplement.pdf"])

    def test_explicit_complete_representations_only_and_nonmodel_filter(self):
        files = [item("a.pdf"), item("a.html", representation_of="a.pdf"),
                 item("a.xml", representation_of="a.html"), item("b.pdf"), item("b.xml"),
                 item("private.pdf", input_use="provenance")]
        selected, excluded = select_materials(files)
        self.assertEqual([f["path"] for f in selected], ["a.xml", "b.pdf", "b.xml"])
        self.assertEqual(next(f for f in excluded if f["path"] == "a.pdf")["selected_path"], "a.xml")
        self.assertEqual(next(f for f in excluded if f["path"] == "private.pdf")["reason"], "not_model")

    def test_cross_task_missing_and_cyclic_links_are_rejected(self):
        for files in ([item("a.pdf"), item("a.xml", representation_of="../B002/a.pdf")],
                      [item("a.xml", representation_of="missing.pdf")],
                      [item("a.xml", representation_of="a.html"), item("a.html", representation_of="a.xml")],
                      [item("a.xml"), item("a.xml")]):
            with self.subTest(files=files), self.assertRaises(Stop):
                select_materials(files)


class PdfReaderTests(unittest.TestCase):
    def test_all_text_scanned_chart_rotated_and_blank_pages_survive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "supplement.pdf"
            source.write_bytes(pdf_bytes([{"text": "Result 0", "chart": True}, {"scan": True},
                                          {"text": "Rotated", "rotation": 90}, {}]))
            folder = root / "prepared"; folder.mkdir()
            result = prepare_pdf(source, folder, source.name)
            self.assertEqual(result["pdf"]["page_count"], 4)
            self.assertEqual(result["pdf"]["rendering"], RENDERING)
            self.assertEqual(result["pdf"]["parser_version"], __import__("importlib.metadata", fromlist=["version"]).version("pypdfium2"))
            self.assertEqual(len(result["images"]), 4)
            pages = result["pdf"]["pages"]
            self.assertEqual(pages[1]["text_characters"], 0)
            self.assertEqual(pages[3]["text_characters"], 0)
            self.assertEqual(pages[2]["rotation"], 90)
            self.assertGreater(result["images"][2]["width"], result["images"][2]["height"])
            for image in result["images"]:
                self.assertEqual(image["sha256"], sha(folder / image["path"]))
                with Image.open(folder / image["path"]) as bitmap:
                    self.assertEqual(bitmap.mode, "RGB")
                    self.assertEqual(bitmap.size, (image["width"], image["height"]))
            with Image.open(folder / result["images"][0]["path"]) as bitmap:
                self.assertTrue(any(r > 200 and b < 50 for count, (r, g, b) in bitmap.getcolors(bitmap.width * bitmap.height)))
            with Image.open(folder / result["images"][1]["path"]) as bitmap:
                self.assertGreater(len(bitmap.getcolors(bitmap.width * bitmap.height)), 1)

    def test_corrupt_pdf_and_page_failure_block_instead_of_omitting_pages(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / "bad.pdf"; source.write_bytes(b"%PDF-broken")
            with self.assertRaises(Stop):
                prepare_pdf(source, root, source.name)
            source.write_bytes(pdf_bytes([{"text": "one"}, {"text": "two"}]))
            import pypdfium2
            with patch.object(pypdfium2.PdfPage, "render", side_effect=RuntimeError("page failure")), self.assertRaises(Stop):
                prepare_pdf(source, root, source.name)

    def test_encrypted_pdf_with_empty_user_password_is_still_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / "encrypted.pdf"
            source.write_bytes(encrypted_pdf_bytes())
            with self.assertRaises(Stop) as error:
                prepare_pdf(source, root, source.name)
            self.assertEqual(error.exception.status, "blocked_pdf")
            self.assertIn("Encrypted", str(error.exception))


class PdfExecutionTests(unittest.TestCase):
    setUp = fixtures.ConditionTests.setUp
    tearDown = fixtures.ConditionTests.tearDown
    manifest = fixtures.ConditionTests.manifest
    execute = fixtures.ConditionTests.execute
    send = fixtures.ConditionTests.send
    response = fixtures.ConditionTests.response

    def test_main_pdf_exclusions_precede_open_stat_hash_and_copy(self):
        material = self.root / "dataset/materials/basic/B001"
        manifest = read(material / "materials.json")
        manifest["files"].append(item("publisher.pdf", "source_version", bytes=9, sha256="unused"))
        write(material / "materials.json", manifest)
        original_open, original_stat = Path.open, Path.stat
        def opened(path, *args, **kwargs):
            if path.name in {"article.pdf", "publisher.pdf"}:
                self.fail("Excluded article PDF was opened")
            return original_open(path, *args, **kwargs)
        def stated(path, *args, **kwargs):
            if path.name in {"article.pdf", "publisher.pdf"}:
                self.fail("Excluded article PDF was statted")
            return original_stat(path, *args, **kwargs)
        with patch.object(Path, "open", opened), patch.object(Path, "stat", stated):
            report = prepare(self.root / "dataset", "B001", self.root / "excluded-main")
        self.assertEqual(report["status"], "ready_offline")
        self.assertEqual({e["path"] for e in report["excluded"]}, {"article.pdf", "publisher.pdf"})

    def add_pdf(self):
        material = self.root / "dataset/materials/basic/B001"
        source = material / "supplement.pdf"
        source.write_bytes(pdf_bytes([{"text": "SUPPLEMENT-ONLY-FACT 0", "chart": True}, {"scan": True}]))
        manifest = read(material / "materials.json")
        manifest["files"].append(item(source.name, bytes=source.stat().st_size, sha256=sha(source)))
        write(material / "materials.json", manifest)
        shutil.rmtree(self.root / "prepared")
        report = prepare(self.root / "dataset", "B001", self.root / "prepared")
        self.assertEqual(report["status"], "ready_offline")
        return report

    def test_complete_request_and_independent_review_replay(self):
        report = self.add_pdf()
        self.assertEqual(report["protocol"], "biotracebench-materials-4")
        self.assertEqual(report["pdf_policy"], PDF_POLICY)
        pdf = next(e for e in report["materials"] if e["format"] == ".pdf")
        reader = Reader(self.root / "prepared")
        body = inputs.messages(reader)
        self.assertEqual(sum(p["type"] == "image_url" for p in body[1]["content"]), 2)
        self.assertIn("SUPPLEMENT-ONLY-FACT 0", json.dumps(body))
        self.manifest()
        self.assertIsNone(self.execute()["failure"])
        for request in self.wire:
            wire = json.dumps(request)
            self.assertIn("SUPPLEMENT-ONLY-FACT 0", wire)
            self.assertIn("PDF page 2", wire)
            self.assertNotIn("application/pdf", wire)
            self.assertNotIn("JVBERi0", wire)
            self.assertFalse(request.get("tools"))
        self.assertEqual(self.wire[1]["messages"][:-1], self.wire[2]["messages"][:-1])
        self.assertIsNone(self.execute(offline=True)["failure"])
        self.assertEqual(self.provider.completions, 3)
        self.assertEqual(sha(reader.folder / pdf["id"] / "source.pdf"), pdf["sha256"])

    def test_missing_page_and_old_policy_cannot_be_relabelled(self):
        report = self.add_pdf()
        pdf = next(e for e in report["materials"] if e["format"] == ".pdf")
        path = self.root / "prepared/materials.json"
        pdf["pdf"]["pages"].pop()
        write(path, report); seal(path.parent)
        with self.assertRaises(Stop):
            Reader(path.parent)
        report["pdf_policy"] = "never_read_or_transmit"
        write(path, report); seal(path.parent)
        with self.assertRaises(Stop) as caught:
            Reader(path.parent)
        self.assertEqual(caught.exception.status, "stale_preparation")

    def test_page_character_offsets_preserve_extracted_crlf(self):
        material = self.root / "dataset/materials/basic/B001"
        source = material / "lines.pdf"
        source.write_bytes(pdf_bytes([{"text": "First line\nSecond line"}, {"text": "Last page"}]))
        manifest = read(material / "materials.json")
        manifest["files"].append(item(source.name, bytes=source.stat().st_size, sha256=sha(source)))
        write(material / "materials.json", manifest)
        output = self.root / "line-preparation"
        report = prepare(self.root / "dataset", "B001", output)
        self.assertEqual(report["status"], "ready_offline")
        reader = Reader(output)
        entry = next(e for e in reader.entries.values() if e["format"] == ".pdf")
        with (output / entry["id"] / "content.txt").open(newline="") as stream:
            content = stream.read()
        self.assertIn("\r\n", content)
        self.assertEqual(entry["text_characters"], len(content))
        parts = inputs.messages(reader)[1]["content"]
        for page in entry["pdf"]["pages"]:
            expected = content[page["text_start"]:page["text_end"]]
            actual = reader.text(entry["id"], page["text_start"], page["text_characters"])["text"]
            self.assertEqual(actual, expected)
            self.assertTrue(any(p.get("text", "").endswith(expected) for p in parts))

    def test_text_only_model_and_insufficient_bytes_fail_before_calls(self):
        self.add_pdf(); self.manifest(); self.frozen.unlink()
        from biotracebench.runner import freeze
        draft = read(self.root / "draft.json")
        draft["model"]["capabilities"]["vision"] = False
        write(self.root / "draft.json", draft)
        with self.assertRaisesRegex(ValueError, "vision"):
            freeze(self.root / "draft.json", self.frozen)
        draft["model"]["capabilities"]["vision"] = True
        draft["model"]["max_request_bytes"] = 20
        draft["capacity_policy"] = "defer_and_continue"
        write(self.root / "draft.json", draft)
        freeze(self.root / "draft.json", self.frozen)
        result = self.execute(sender=lambda *args: self.fail("Oversized input must not issue a request"))
        self.assertIsNone(result["failure"])
        self.assertEqual(result["tasks"]["B001"]["i0"], "paused_capacity")


if __name__ == "__main__":
    unittest.main()
