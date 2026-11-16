"""Current experiment requests preserve source text and independent review starts."""
import copy
import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

import test_biotracebench_conditions as fixtures
from test_biotracebench import ANSWER
from biotracebench import prompts
from biotracebench.cli import main
from biotracebench.common import Stop, digest, read, sha, write
from biotracebench.materials import prepare
from biotracebench.runner import validate_binding

GSR = "Check and revise the initial database against the original task requirements, using the supplied study materials as needed. Return the complete revised database using the same submission format."
SSR = "Review the initial database against the original task requirements. First reread the supplied task instructions and study materials, revisiting relevant passages where needed without treating the initial answer as evidence. Next check experimental object identities, roles, association targets, and relationship directions. Then check dependent values, conditions, times, units, omissions, duplicates, and information states. For basic research, check sample–condition–assay associations. For clinical research, check population–measure–result associations and relationships between populations. Base revisions on the supplied materials and record conflicts or unresolved questions without inventing facts. Return the complete revised database using the same submission format, even if no changes are needed."


class CleanupTests(unittest.TestCase):
    setUp = fixtures.ConditionTests.setUp
    tearDown = fixtures.ConditionTests.tearDown
    manifest = fixtures.ConditionTests.manifest
    execute = fixtures.ConditionTests.execute
    send = fixtures.ConditionTests.send
    response = fixtures.ConditionTests.response

    def test_review_prompts_are_delivered_verbatim_on_independent_native_histories(self):
        frozen = self.manifest()
        self.assertEqual(prompts.GSR, GSR)
        self.assertEqual(prompts.SSR, SSR)
        unique = "GSR-specific output must not enter SSR"

        def sender(*args):
            if "estimate" in args[0]:
                return self.provider(*args)
            self.wire.append(json.loads(args[1]))
            database = copy.deepcopy(ANSWER)
            if self.provider.completions == 1:
                database["sample"][0]["sample_name"] = unique
            return self.response(json.dumps({"database": database, "annotations": []}))

        self.assertIsNone(self.execute(sender)["failure"])
        first, gsr, ssr = [request["messages"] for request in self.wire]
        self.assertEqual(first[0]["content"], prompts.INITIAL)
        self.assertEqual(gsr[-1], {"role": "user", "content": GSR})
        self.assertEqual(ssr[-1], {"role": "user", "content": SSR})
        self.assertEqual(gsr[:-1], ssr[:-1])
        self.assertNotIn(unique, json.dumps(ssr))
        self.assertIn("reasoning_content", gsr[-2])
        for request in self.wire:
            self.assertFalse(request.get("tools"))
        for key in ("i0", "gsr", "ssr"):
            self.assertEqual(frozen["prompt_hashes"][key], digest(getattr(prompts, "INITIAL" if key == "i0" else key.upper())))
        self.assertIsNone(self.execute(offline=True)["failure"])
        self.assertEqual(self.provider.completions, 3)

    def test_scientific_ontology_text_is_preserved_without_program_added_tools(self):
        source = self.root / "dataset/materials/basic/B001"
        scientific = "Gene Ontology enrichment was measured in the supplied study."
        (source / "notes.txt").write_text(scientific)
        manifest = read(source / "materials.json")
        entry = next(x for x in manifest["files"] if x["path"] == "notes.txt")
        entry.update(bytes=(source / "notes.txt").stat().st_size, sha256=sha(source / "notes.txt"))
        write(source / "materials.json", manifest)
        shutil.rmtree(self.root / "prepared")
        prepare(self.root / "dataset", "B001", self.root / "prepared")
        self.manifest()
        self.assertIsNone(self.execute()["failure"])
        for request in self.wire:
            initial_parts = request["messages"][1]["content"]
            self.assertTrue(any(scientific in x.get("text", "") for x in initial_parts))
            self.assertFalse(request.get("tools"))
        program_text = prompts.INITIAL + GSR
        for term in ("ontology", "terminology", "synonym", "relationship graph"):
            self.assertNotIn(term, program_text.lower())

    def test_unexpected_tool_call_is_archived_and_never_executed(self):
        self.manifest()
        def sender(*args):
            if "estimate" in args[0]:
                return self.provider(*args)
            return self.response(tool="query_terms")
        result = self.execute(sender)
        self.assertEqual(result["failure"]["status"], "failed_response")
        self.assertEqual(self.provider.completions, 1)
        self.assertTrue((self.out / "B001/i0/calls/00000/completion/response.bin").is_file())
        self.assertFalse((self.out / "B001/gsr/final").exists())

    def test_draft_has_no_implicit_model_and_requires_explicit_profile(self):
        root = Path(__file__).resolve().parents[1]
        template = read(root / "configs/models/biotracebench-run-template.json")
        self.assertIsNone(template["model"])
        self.assertNotIn("ontology_mode", template)
        with patch("sys.stderr"), self.assertRaises(SystemExit) as error:
            main(["draft", "--prepared", str(self.root), "--template", "template.json", "--out", "draft.json"])
        self.assertEqual(error.exception.code, 2)

    def test_changed_prompt_identity_cannot_relabel_a_frozen_run(self):
        frozen = self.manifest()
        frozen["prompt_hashes"]["gsr"] = "historical-prompt"
        with self.assertRaises(Stop) as error:
            validate_binding(frozen)
        self.assertEqual(error.exception.status, "tampered")


if __name__ == "__main__":
    unittest.main()
