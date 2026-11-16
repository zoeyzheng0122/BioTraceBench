"""Shared source selection, reversible cells, wire capacity and SSE recovery."""
import base64
import copy
import io
import json
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from biotracebench.common import Stop, read, write, sha, digest, encoded
from biotracebench.materials import prepare, Reader
from biotracebench.shared_inputs import derive, SELECTION, pack_cell, unpack_cell, compact_workbook, expand_record
from biotracebench.preflight import matrix, inspect
from biotracebench import inputs
from model_conversation import Conversation, Adapter
from model_conversation.profiles import load
from model_conversation.input_limits import check
from model_conversation.streaming import decode, Interrupted
from model_conversation.uploads import upload_image
from test_biotracebench import source_fixture, MODEL
from pdf_fixtures import pdf_bytes

ROOT = Path(__file__).resolve().parents[1]


class SharedTests(unittest.TestCase):
    def fixture(self, folder):
        dataset = folder / "dataset"; material = source_fixture(dataset)
        Image.new("RGB", (4000, 1000), "white").save(material / "figure.png")
        (material / "appendix.pdf").write_bytes(pdf_bytes([{"text": "Population and denominator"}, {"text": "Result 0"}, {"scan": True}]))
        manifest = read(material / "materials.json")
        for name in ("figure.png", "appendix.pdf"):
            manifest["files"].append({"path": name, "role": "supplement", "input_use": "model",
                                      "sha256": sha(material / name), "bytes": (material / name).stat().st_size})
        write(material / "materials.json", manifest)
        prepare(dataset, "B001", folder / "full" / "B001")
        reader = Reader(folder / "full" / "B001")
        decisions = [{"path": e["source"], "sha256": e["sha256"], "decision": "keep", "reason": "Synthetic source review", "basis": "Synthetic task scope"} for e in reader.entries.values()]
        decisions[-1].update(decision="select", pages=[1, 3])
        selection = {"protocol": SELECTION, "cases": {"B001": {"source_identity": reader.manifest["source_identity"], "files": decisions}}}
        write(folder / "selection.json", selection)
        return dataset, selection

    def test_shared_source_guard_resize_page_mapping_and_wire_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); dataset, selection = self.fixture(root)
            original = Path.open
            def guard(path, *a, **kw):
                if "gold_standard" in path.parts:
                    raise AssertionError("No reference reads")
                mode = a[0] if a else kw.get("mode", "r")
                if path.is_relative_to(dataset) and any(x in mode for x in "wa+"):
                    raise AssertionError("Original package is read-only")
                return original(path, *a, **kw)
            with patch.object(Path, "open", guard), patch.object(socket, "socket", side_effect=AssertionError("No network")):
                report = derive(root / "full/B001", root / "shared/B001", root / "selection.json")
            reader = Reader(root / "shared/B001")
            self.assertEqual(report["evidence_identity"], reader.manifest["evidence_identity"])
            page = next(e for e in reader.entries.values() if e["format"] == ".pdf")
            self.assertEqual([p["page"] for p in page["pdf"]["pages"]], [1, 3])
            turns = inputs.messages(reader)
            config = Adapter(MODEL).c
            config["max_request_bytes"] = 10000000
            result = inspect(reader, config)
            self.assertEqual(result["request_bytes"], len(encoded(Adapter(config).build(turns, []))))
            self.assertTrue(all(max(i["width"], i["height"]) <= 2000 for e in reader.entries.values() for i in e["images"]))
            mid, entry = next((mid, e) for mid, e in reader.entries.items() if e["images"])
            image = entry["images"][0]
            delivery = {"images": {image["sha256"]: {"path": str(reader.folder / mid / image["path"]),
                         "sha256": image["sha256"], "width": image["width"], "height": image["height"], "file_id": "file-synthetic"}}}
            native_turns = inputs.messages(reader, delivery=delivery)
            self.assertEqual([p["text"] for p in turns[1]["content"] if p["type"] == "text"],
                             [p["text"] for p in native_turns[1]["content"] if p["type"] == "text"])
            other = root / "different.png"; Image.new("RGB", (10, 10)).save(other)
            delivery["images"][image["sha256"]].update(path=str(other), sha256=sha(other), width=10, height=10)
            with self.assertRaises(Stop):
                inputs.messages(reader, delivery=delivery)
            self.assertIn("Result 0", (root / "full/B001" / page["id"] / "content.txt").read_text())
            self.assertNotIn("Result 0", (reader.folder / page["id"] / "content.txt").read_text())
            with self.assertRaises(Stop):
                derive(root / "full/B001", root / "shared/B001", root / "selection.json")

    def test_selection_rejects_missing_identity_main_deletion_and_bad_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, selection = self.fixture(root)
            for change in ("identity", "missing", "main", "pages"):
                value = copy.deepcopy(selection); case = value["cases"]["B001"]
                if change == "identity": case["source_identity"] = "wrong"
                if change == "missing": case["files"].pop()
                if change == "main": case["files"][0]["decision"] = "exclude"
                if change == "pages": case["files"][-1]["pages"] = [0, 4]
                write(root / "bad.json", value)
                with self.assertRaises(Stop):
                    derive(root / "full/B001", root / ("bad-"+change), root / "bad.json")

    def test_compact_cells_runs_precision_formula_and_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source, target = root / "source.txt", root / "compact.txt"
            cells = [{"cell": "A1", "raw": 0, "cached": 0, "number_format": "General", "is_formula": False},
                     {"cell": "B1", "raw": "=1/3", "cached": 0.3333333333333333, "source_numeric_lexeme": "0.33333333333333331", "number_format": "0.00", "is_formula": True},
                     {"cell": "C1", "raw": "2–4", "cached": "2–4", "number_format": "General", "is_formula": False}]
            for c in cells:
                self.assertEqual(encoded(unpack_cell(pack_cell(c))), encoded(c))
            rows = [{"sheet": "Samples", "row": n, "cells": [{**cells[0], "cell": "A"+str(n), "raw": "Pool α", "cached": "Pool α"}, {**cells[1], "cell": "B"+str(n)}]} for n in range(1, 4)]
            source.write_bytes(b"\n".join(encoded(r) for r in rows)+b"\n")
            report = compact_workbook(source, target, {"sheets": ["Samples"], "columns": {"Samples": ["A"]}})
            output = [json.loads(s) for s in target.read_text().splitlines()]
            self.assertEqual(output[1]["row_range"], [1, 3])
            self.assertEqual(output[1]["cell_columns"], [["A", "Pool α", {}]])
            self.assertEqual(report["retained_records_sha256"], report["roundtrip_sha256"])
            restored = [r for record in output for r in expand_record(record)]
            self.assertEqual(restored, [{**r, "cells": r["cells"][:1]} for r in rows])

    def test_catalog_twelve_profiles_and_matrix_share_identity(self):
        catalog = read(ROOT / "configs/models/benchmark-2026-10-28.json")
        self.assertEqual(len(catalog["models"]), 12)
        for model in catalog["models"]:
            config = load(ROOT / "configs/models" / model["profile"])
            Adapter(config)
            with self.assertRaises(Stop):
                Conversation(config).invoke([{"role": "user", "content": "JSON"}], [], Path("unused"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            derive(root / "full/B001", root / "shared/B001", root / "selection.json")
            result = matrix(root / "shared", ROOT / "configs/models/benchmark-2026-10-28.json", root / "matrix")
            self.assertEqual(result["pair_count"], 12)
            rows = read(root / "matrix/matrix.json")["rows"]
            self.assertEqual(len({r["evidence_identity"] for r in rows}), 1)
            reader = Reader(root / "shared/B001")
            turns = inputs.messages(reader)
            expected = [turns[0]["content"]] + [p["text"] for p in turns[1]["content"] if p["type"] == "text"]
            def texts(value):
                if isinstance(value, dict):
                    for key, item in value.items():
                        if key in {"text", "instructions", "system"} and isinstance(item, str):
                            yield item
                        else:
                            yield from texts(item)
                elif isinstance(value, list):
                    for item in value:
                        yield from texts(item)
            for model in catalog["models"]:
                config = load(ROOT / "configs/models" / model["profile"])
                body = Adapter(config).build(turns, [])
                if config["provider"] in {"qwen", "doubao"}:
                    self.assertEqual(body["stream_options"], {"include_usage": True})
                received = list(texts(body))
                if config["protocol"] == "chat_completions":
                    received = [m["content"] for m in body["messages"] if isinstance(m["content"], str)] + received
                if config["protocol"] == "gemini":
                    received = [received[-1]] + received[:-1]
                self.assertEqual(received, expected, model["id"])


class LimitTests(unittest.TestCase):
    def test_many_image_threshold_and_count_bytes_are_independent(self):
        image = {"width": 2001, "height": 1000, "bytes": 20, "inline": True, "encoded_bytes": 28}
        limits = {"many_image_threshold": 20, "many_image_max_dimension": 2000, "max_images": 250, "max_request_bytes": 100}
        self.assertFalse(check({"images": [image]*20}, limits))
        self.assertEqual(check({"images": [image]*21}, limits)[0]["limit"], "many_image_max_dimension")
        self.assertIn("max_images", {f["limit"] for f in check({"images": [image]*251}, limits)})
        self.assertEqual(check({"images": []}, limits, request_bytes=101)[0]["limit"], "max_request_bytes")

    def test_native_file_keeps_dimensions_and_expiration_checks(self):
        model = next(m for m in read(ROOT / "configs/models/benchmark-2026-10-28.json")["models"] if m["id"] == "claude-sonnet-5-5")
        config = load(ROOT / "configs/models" / model["profile"])
        config["estimator"] = {"kind": "fixed_upper_bound", "input_tokens": 100, "basis": "Synthetic"}
        config["file_metadata"] = {"file-synthetic": {"provider": "anthropic", "sha256": "a"*64, "bytes": 1, "width": 2001, "height": 500, "expiry_policy": "provider_persistent"}}
        messages = [{"role": "user", "content": [{"type": "file", "file_id": "file-synthetic"}]*21}]
        with self.assertRaises(Stop):
            Conversation(config).preflight(messages, [])
        config["file_metadata"]["file-synthetic"]["width"] = 1000
        body = Conversation(config).preflight(messages, [])
        self.assertEqual(body["messages"][0]["content"][0]["source"]["type"], "file")


def sse(values):
    return b"".join(b"data: "+encoded(v)+b"\n\n" for v in values)


class StreamTests(unittest.TestCase):
    def test_native_signatures_reasoning_and_terminal_required(self):
        events = [{"type": "message_start", "message": {"role": "assistant", "model": "fixture", "usage": {"input_tokens": 7}}},
                  {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}},
                  {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "native"}},
                  {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "opaque"}},
                  {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 9}}, {"type": "message_stop"}]
        result = decode(sse(events), "anthropic")
        self.assertEqual(result["content"][0]["signature"], "opaque")
        self.assertEqual(result["usage"], {"input_tokens": 7, "output_tokens": 9})
        with self.assertRaises(Stop): decode(sse(events[:-1]), "anthropic")
        response = {"model": "grok-4.7", "status": "completed", "output": [{"type": "reasoning", "encrypted_content": "opaque"}], "usage": {}}
        self.assertEqual(decode(sse([{"type": "response.completed", "response": response}]), "responses"), response)

    def test_chat_stream_recover_without_network_and_unknown_no_retry(self):
        config = Adapter(MODEL).c; config["stream"] = True
        raw = sse([{"model": "kimi-k3", "choices": [{"delta": {"reasoning_content": "native", "content": "{}"}, "finish_reason": None}]},
                   {"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 7, "completion_tokens": 2}}])
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"MOONSHOT_API_KEY": "synthetic-only"}):
            client = Conversation(config, sender=lambda *a: (200, {}, raw))
            result = client.invoke([{"role": "user", "content": "JSON"}], [], Path(tmp)/"ok")
            self.assertEqual(result["message"]["reasoning_content"], "native")
            with patch.object(socket, "socket", side_effect=AssertionError("No network")):
                self.assertEqual(client.recover([{"role": "user", "content": "JSON"}], [], Path(tmp)/"ok"), result)
            broken = Conversation(config, sender=lambda *a: (_ for _ in ()).throw(Interrupted(b"partial synthetic-only", 200, {})))
            with self.assertRaises(Stop): broken.invoke([{"role": "user", "content": "JSON"}], [], Path(tmp)/"bad")
            self.assertNotIn(b"synthetic-only", (Path(tmp)/"bad/partial-stream.bin").read_bytes())
            with self.assertRaises(Stop): broken.invoke([{"role": "user", "content": "JSON"}], [], Path(tmp)/"bad")

    def test_gemini_stream_keeps_thought_signatures_and_usage(self):
        events = [{"modelVersion": "fixture", "candidates": [{"content": {"role": "model", "parts": [{"text": "thinking", "thought": True, "thoughtSignature": "opaque"}]}}]},
                  {"candidates": [{"content": {"role": "model", "parts": [{"text": "{}"}]}, "finishReason": "STOP"}], "usageMetadata": {"promptTokenCount": 3}}]
        result = decode(sse(events), "gemini")
        self.assertEqual(result["candidates"][0]["content"]["parts"][0]["thoughtSignature"], "opaque")
        self.assertEqual(result["usageMetadata"]["promptTokenCount"], 3)


class UploadTests(unittest.TestCase):
    def test_three_native_upload_receipts_reuse_without_key_or_network(self):
        import time
        for provider, env in [("openai", "OPENAI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY"), ("gemini", "GEMINI_API_KEY")]:
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); image = root / "image.png"; Image.new("RGB", (20, 10)).save(image)
                calls = []
                def sender(endpoint, body, headers, timeout):
                    calls.append(endpoint)
                    self.assertIn(image.read_bytes(), body)
                    if provider == "gemini":
                        return 200, {}, encoded({"file": {"uri": "https://generativelanguage.googleapis.com/v1beta/files/synthetic", "sizeBytes": str(image.stat().st_size), "mimeType": "image/png", "expirationTime": "2099-01-01T00:00:00Z"}})
                    return 200, {}, encoded({"id": "file-synthetic", "bytes": image.stat().st_size, "mime_type": "image/png", "expires_at": int(time.time())+86400})
                with patch.dict(os.environ, {env: "synthetic-private"}):
                    receipt = upload_image(provider, image, root/"upload", sender=sender)
                with patch.dict(os.environ, {}, clear=True), patch.object(socket, "socket", side_effect=AssertionError("No network")):
                    self.assertEqual(upload_image(provider, image, root/"upload"), receipt)
                self.assertEqual(len(calls), 1)
                self.assertEqual(receipt["sha256"], sha(image))
                self.assertEqual((receipt["width"], receipt["height"]), (20, 10))


class IntegrationTests(unittest.TestCase):
    def test_shared_streaming_forks_ledger_and_offline_recovery(self):
        from test_biotracebench_conditions import ConditionTests
        from biotracebench.runner import freeze
        from biotracebench_analysis.coverage import compare
        fixture = ConditionTests("test_new_run_paths_forks_logs_costs_export_and_offline_replay")
        fixture.setUp()
        try:
            fixture.manifest()
            reader = Reader(fixture.root / "prepared")
            selection = {"protocol": SELECTION, "cases": {"B001": {"source_identity": reader.manifest["source_identity"],
                "files": [{"path": e["source"], "sha256": e["sha256"], "decision": "keep", "reason": "Synthetic", "basis": "Synthetic task"} for e in reader.entries.values()]}}}
            write(fixture.root / "selection.json", selection)
            derive(reader.folder, fixture.root / "shared", fixture.root / "selection.json")
            draft = read(fixture.root / "draft.json")
            draft["tasks"][0]["prepared"] = str(fixture.root / "shared")
            draft["model"]["stream"] = True
            write(fixture.root / "shared-draft.json", draft)
            fixture.frozen = fixture.root / "shared-frozen.json"
            manifest = freeze(fixture.root / "shared-draft.json", fixture.frozen)
            def sender(*args):
                status, headers, data = fixture.send(*args)
                if "estimate" in args[0]:
                    return status, headers, data
                value = json.loads(data)
                chunk = {"model": value["model"], "choices": [{"delta": value["choices"][0]["message"], "finish_reason": "stop"}], "usage": value["usage"]}
                return status, headers, sse([chunk])
            result = fixture.execute(sender)
            self.assertIsNone(result["failure"])
            self.assertEqual(result["tasks"]["B001"], dict.fromkeys(("i0", "gsr", "ssr"), "completed"))
            g = read(fixture.out / "B001/gsr/branch.json"); s = read(fixture.out / "B001/ssr/branch.json")
            self.assertEqual(g["i0_history_sha256"], s["i0_history_sha256"])
            self.assertEqual(read(fixture.out / "costs.json")["unknown_budget_calls"], 0)
            self.assertIsNone(fixture.execute(offline=True)["failure"])
            report = compare({"A": fixture.out, "B": fixture.out})
            self.assertEqual(report["common_completed_cases"]["ssr"], ["B001"])
            self.assertEqual(report["models"]["A"]["i0"]["completion_rate"], 1)
            other = fixture.root / "other"; other.mkdir()
            changed = copy.deepcopy(manifest); changed["tasks"][0]["evidence_identity"] = "different"
            write(other / "manifest.json", changed); write(other / "status.json", {"tasks": result["tasks"]})
            with self.assertRaises(Stop):
                compare({"A": fixture.out, "B": other})
        finally:
            fixture.tearDown()
