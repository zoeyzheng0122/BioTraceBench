"""Synthetic material, API, scoring and export regression tests."""
import copy
import hashlib
import json
import os
import socket
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from biotracebench.common import Stop, digest, encoded, read, seal, sha, verify, write
from model_conversation import Conversation
from biotracebench.materials import prepare, Reader
from biotracebench.runner import freeze, run, validate_manifest
from biotracebench_scoring.evaluation import score
from biotracebench_analysis.statistics import aggregate, compare_conditions
from biotracebench.export import database, run_report
from biotracebench.schema import validate, check_schema

MODEL = {"endpoint": "https://api.moonshot.cn/v1/chat/completions", "model": "kimi-k3",
         "reasoning_effort": "high", "timeout": 900, "retries": 0,
         "max_output_tokens": 1000, "max_request_bytes": 1000000, "context_tokens": 100000}
TARIFF = {"currency": "CNY", "version": "synthetic", "source_url": "https://example.invalid/synthetic", "retrieved_at": "2026-10-24",
          "per_million": {"input": 1, "output": 2, "cache_hit": 0.1, "cache_write": 1},
          "usage_paths": {"input": "prompt_tokens", "output": "completion_tokens", "cache_hit": "cached_tokens", "cache_write": "cache_write_tokens"}}
DICTIONARY = {
    "sample": {"identifier": "sample_id", "fields": [{"key": x} for x in ["sample_id", "sample_name", "species"]]},
    "condition": {"identifier": "condition_id", "references": {"sample_id": "sample"}, "fields": [{"key": x} for x in ["condition_id", "sample_id", "experimental_factor", "factor_value"]]},
    "assay_run": {"identifier": "assay_id", "references": {"sample_ids": "sample"}, "fields": [{"key": x} for x in ["assay_id", "sample_ids", "assay_type"]]},
}
ANSWER = {"sample": [{"sample_id": "s1", "sample_name": "细胞 A", "species": "human"}],
          "condition": [{"condition_id": "c1", "sample_id": "s1", "experimental_factor": "dose", "factor_value": 0}],
          "assay_run": [{"assay_id": "a1", "sample_ids": ["s1"], "assay_type": "LC-MS"}]}
CLINICAL_ANSWER = {"population":[{"population_id":"p1","population_name":"Synthetic population","population_size":0}],
                   "measure":[{"measure_id":"m1","measure_name":"Synthetic measure"}],
                   "result":[{"result_id":"r1","population_id":"p1","measure_id":"m1","result_value":0}],"population_relation":[]}
SCHEMA = {"type": "object", "properties": {k: {"type": "array", "items": {"type": "object"}} for k in ANSWER}, "required": list(ANSWER), "additionalProperties": False}
POLICY = {"version": "biotracebench-score-1", "frozen": True, "field_rules": {}, "identity_fields": {}}

def source_fixture(root):
    task = root/"tasks/basic/B001"
    material = root/"materials/basic/B001"
    task.mkdir(parents=True)
    material.mkdir(parents=True)
    (root/"schemas").mkdir()
    write(task/"task.json", {"case_id": "B001", "domain": "basic", "doi": "10.synthetic/1"})
    (task/"complete-prompt.md").write_text("Return JSON sample, condition, assay_run. Source count is 0. 中文。")
    write(root/"schemas/basic-three.schema.json", SCHEMA)
    write(root/"schemas/field-dictionary.json", {"basic": DICTIONARY})
    (material/"article.xml").write_text('<article><body><p>细胞 A, dose 0. Alias disease.</p><table><tr><td colspan="2">0</td></tr></table></body></article>')
    (material/"article.pdf").write_bytes(b"NEVER OPEN THIS FILE")
    (material/"notes.txt").write_text("0 中文 footnote")
    files = [{"path": name, "input_use": "model", "role": "main" if name.endswith("xml") else "main_pdf" if name.endswith("pdf") else "supplement", "bytes": (material/name).stat().st_size, "sha256": hashlib.sha256(b"NEVER OPEN THIS FILE").hexdigest() if name.endswith(".pdf") else sha(material/name)} for name in ("article.xml", "article.pdf", "notes.txt")]
    write(material/"materials.json", {"case": {"case_id": "B001"}, "files": files})
    return material


class SyntheticProvider:
    def __init__(self):
        self.completions = self.estimates = 0
    def __call__(self, endpoint, body, headers, timeout):
        request = json.loads(body)
        if "estimate" in endpoint:
            self.estimates += 1
            return 200, {}, encoded({"data": {"total_tokens": 200}})
        self.completions += 1
        if request.get("tools"):
            raise AssertionError("The task runner must not expose model tools")
        clinical = "SYNTHETIC_CLINICAL" in json.dumps(request["messages"])
        text = json.dumps({"database": CLINICAL_ANSWER if clinical else ANSWER, "annotations": []}, ensure_ascii=False)
        return 200, {}, encoded({"model": "kimi-k3", "choices": [{"message": {"role": "assistant", "content": text,
            "reasoning_content": "synthetic returned reasoning"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 200, "completion_tokens": 20, "cached_tokens": 0, "cache_write_tokens": 0}})


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def prepared(self):
        dataset = self.root/"dataset"
        source_fixture(dataset)
        prepare(dataset, "B001", self.root/"prepared")
        return Reader(self.root/"prepared")

    def test_pdf_never_opened_and_gold_unread(self):
        source_fixture(self.root/"dataset")
        (self.root/"dataset/gold_standard").mkdir()
        original = Path.open
        def guarded(path, *args, **kwargs):
            if path.suffix == ".pdf" or "gold_standard" in path.parts:
                raise AssertionError("Forbidden source opened")
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", guarded):
            report = prepare(self.root/"dataset", "B001", self.root/"prepared")
        self.assertEqual(report["status"], "ready_offline")
        self.assertEqual(len(report["materials"]), 2)
        self.assertEqual(report["excluded"][0]["reason"], "main_article_pdf")

    def test_tamper_and_task_escape(self):
        reader = self.prepared()
        with self.assertRaises(ValueError):
            reader.text("../gold_standard", 0, 10)
        (reader.folder/"m0001/content.txt").write_text("modified")
        with self.assertRaises(Stop):
            Reader(reader.folder)

    def test_conversation_recovery_no_key_no_network_and_tamper(self):
        provider = SyntheticProvider()
        backend = Conversation(MODEL, sender=provider)
        messages = [{"role": "user", "content": "JSON synthetic"}]
        folder = self.root/"attempt"
        with patch.dict(os.environ, {"MOONSHOT_API_KEY": "synthetic-key"}):
            result = backend.invoke(messages, [], folder)
            with self.assertRaises(Stop):
                backend.invoke(messages, [], folder)
        with patch.dict(os.environ, {}, clear=True), patch.object(socket, "socket", side_effect=AssertionError("network")):
            self.assertEqual(backend.recover(messages, [], folder), result)
        self.assertIn("reasoning_content", result["message"])
        write(folder/"http.json", {"status": 200})
        with self.assertRaises(Stop):
            backend.recover(messages, [], folder)

    def test_secret_redacted_even_in_error(self):
        key = "synthetic-private-secret"
        backend = Conversation(MODEL, sender=lambda *a: (401, {"x-request-id": key}, encoded({"error": {"message": key}})))
        with patch.dict(os.environ, {"MOONSHOT_API_KEY": key}), self.assertRaises(Stop):
            backend.invoke([{"role": "user", "content": "JSON"}], [], self.root/"error")
        for file in (self.root/"error").rglob("*"):
            if file.is_file():
                self.assertNotIn(key.encode(), file.read_bytes())

    def test_timeout_never_retries(self):
        def timeout(*args):
            raise TimeoutError()
        backend = Conversation(MODEL, sender=timeout)
        messages = [{"role": "user", "content": "JSON"}]
        with patch.dict(os.environ, {"MOONSHOT_API_KEY": "synthetic"}), self.assertRaises(Stop):
            backend.invoke(messages, [], self.root/"attempt")
        with self.assertRaises(Stop) as exc:
            backend.recover(messages, [], self.root/"attempt")
        self.assertEqual(exc.exception.status, "paused_unknown")

    def test_http_failures_truncation_empty(self):
        for status, expected in [(400,"paused_configuration"),(401,"paused_account"),(403,"paused_account"),(429,"paused_rate_limit"),(500,"paused_unknown")]:
            backend = Conversation(MODEL, sender=lambda *a, code=status: (code, {}, b'{}'))
            with patch.dict(os.environ, {"MOONSHOT_API_KEY": "synthetic"}), self.assertRaises(Stop) as exc:
                backend.invoke([{"role":"user","content":"JSON"}], [], self.root/str(status))
            self.assertEqual(exc.exception.status, expected)
        for finish, content, expected in [("length","{}","paused_truncated"),("stop","","failed_response")]:
            raw = {"model":"kimi-k3","choices":[{"message":{"role":"assistant","content":content},"finish_reason":finish}]}
            backend = Conversation(MODEL, sender=lambda *a, raw=raw: (200, {}, encoded(raw)))
            with patch.dict(os.environ, {"MOONSHOT_API_KEY": "synthetic"}):
                result = backend.invoke([{"role":"user","content":"JSON"}], [], self.root/expected)
            self.assertEqual(result["status"], expected)







    def test_budget_policy_is_opt_in_and_rejects_bad_usage(self):
        from biotracebench.cost import budget_cost
        usage={'prompt_tokens':200,'completion_tokens':20,'cache_write_tokens':0}
        self.assertIsNone(budget_cost(usage,TARIFF)['budget_upper'])
        bounded=budget_cost(usage,TARIFF,'known_totals_upper_bound')
        self.assertIsNone(bounded['amount']);self.assertEqual(bounded['budget_upper'],'0.00024')
        for bad in ({'completion_tokens':20},{**usage,'total_tokens':221},{**usage,'cached_tokens':-1},
                    {**usage,'cache_write_tokens':201},{**usage,'cached_tokens':None}):
            self.assertIsNone(budget_cost(bad,TARIFF,'known_totals_upper_bound')['budget_upper'])


    def test_scoring_reorder_rename_zero_wrong_relation_duplicates(self):
        answer = copy.deepcopy(ANSWER)
        answer["sample"].append({"sample_id":"s2","sample_name":"细胞 B","species":"human"})
        renamed = copy.deepcopy(answer)
        renamed["sample"][0]["sample_id"] = "z"
        renamed["sample"][1]["sample_id"] = "a"
        renamed["sample"].reverse()
        renamed["condition"][0]["condition_id"] = "newcondition"
        renamed["condition"][0]["sample_id"] = "z"
        renamed["assay_run"][0]["assay_id"] = "newassay"
        renamed["assay_run"][0]["sample_ids"] = ["z"]
        correct = score(renamed, answer, DICTIONARY, POLICY)
        self.assertEqual(correct["field"]["f1"], 1)
        self.assertEqual(correct["record"]["f1"], 1)
        renamed["condition"][0]["sample_id"] = "a"
        wrong = score(renamed, answer, DICTIONARY, POLICY)
        self.assertLess(wrong["field"]["f1"], 1)
        self.assertEqual(wrong["field"]["tp"], correct["field"]["tp"]-1)
        self.assertEqual(compare_conditions(correct, wrong)["regressed"], 1)
        duplicate = copy.deepcopy(ANSWER)
        duplicate["condition"].append(copy.deepcopy(duplicate["condition"][0]))
        self.assertLess(score(duplicate, ANSWER, DICTIONARY, POLICY)["record"]["precision"], 1)
        empty = score(None, ANSWER, DICTIONARY, POLICY)
        for key in ("field","record"):
            self.assertEqual([empty[key][s] for s in ("precision","recall","f1")], [0,0,0])

    def test_scoring_ambiguous_text_provisional(self):
        answer = copy.deepcopy(ANSWER)
        answer["sample"][0]["species"] = "Homo sapiens"
        result = score(answer, ANSWER, DICTIONARY, POLICY)
        self.assertEqual(result["status"], "provisional")
        self.assertTrue(result["adjudication_queue"])
        decisions = {"equivalences": {x["id"]:True for x in result["adjudication_queue"]}, "matches":{}}
        self.assertEqual(score(answer, ANSWER, DICTIONARY, POLICY, decisions)["field"]["f1"], 1)

    def test_schema_null_zero_and_unknown_constraint(self):
        self.assertEqual(validate(0, {"type":"number"}), [])
        self.assertTrue(validate(None, {"type":"number"}))
        with self.assertRaises(ValueError):
            check_schema({"type":"object","unevaluatedProperties":False})

    def test_export_safe_chinese_zero(self):
        database(ANSWER, self.root/"tables", DICTIONARY)
        self.assertIn("细胞 A", (self.root/"tables/index.html").read_text())
        self.assertIn(",0", (self.root/"tables/condition.csv").read_text())
        with zipfile.ZipFile(self.root/"tables/tables.xlsx") as z:
            self.assertIn("xl/workbook.xml", z.namelist())

    def test_all_non_pdf_readers_except_external_xls_converter(self):
        try:
            from PIL import Image
            import openpyxl
        except ImportError:
            self.skipTest("Optional parser libraries are not installed in this interpreter")
        material = source_fixture(self.root/"dataset")
        manifest = read(material/"materials.json")
        names = []
        for suffix, content in [("json",'{"零":0}'),("csv",'name,value\n"中文,表头",0\n'),("tsv",'name\tvalue\n中文\t0\n'),("md",'# 中文\n0'),("html",'<table><tr><td rowspan="2">0</td></tr></table>')]:
            name = "data."+suffix
            (material/name).write_text(content)
            names.append(name)
        a,b = Image.new("RGB",(20,20),"white"),Image.new("RGB",(20,20),"blue")
        for suffix, fmt in [("jpg","JPEG"),("png","PNG"),("webp","WEBP"),("gif","GIF"),("tif","TIFF")]:
            name = "image."+suffix
            if suffix in {"gif","tif"}:
                a.save(material/name, format=fmt, save_all=True, append_images=[b])
            else:
                a.save(material/name, format=fmt)
            names.append(name)
        for suffix, member, content in [
            ("docx","word/document.xml",'<w:document xmlns:w="urn:w"><w:body><w:p><w:r><w:t>中文 0</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p><w:r><w:t>merged 0</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'),
            ("pptx","ppt/slides/slide1.xml",'<p:sld xmlns:p="urn:p" xmlns:a="urn:a"><a:p><a:r><a:t>Slide 中文 0</a:t></a:r></a:p></p:sld>')]:
            name = "document."+suffix
            with zipfile.ZipFile(material/name,"w") as z:
                z.writestr(member,content)
                z.writestr(("word" if suffix=="docx" else "ppt")+"/media/image1.png",(material/"image.png").read_bytes())
            names.append(name)
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.title = "中文"
        sheet["A1"],sheet["A2"],sheet["B2"] = "header",0,"=1+1"
        sheet["A2"].number_format = "0.00"
        sheet.merge_cells("A1:B1")
        book.save(material/"data.xlsx")
        names.append("data.xlsx")
        for name in names:
            manifest["files"].append({"path":name,"input_use":"model","role":"supplement","sha256":sha(material/name),"bytes":(material/name).stat().st_size})
        write(material/"materials.json",manifest)
        report = prepare(self.root/"dataset","B001",self.root/"prepared")
        self.assertEqual(report["status"],"ready_offline",report["errors"])
        self.assertEqual(len({m["format"] for m in report["materials"]}),15)
        reader = Reader(self.root/"prepared")
        workbook = next(m for m in report["materials"] if m["format"]==".xlsx")
        cells = reader.cells(workbook["id"],"中文",2,2,1,2,10)
        self.assertEqual(cells[0]["raw"],0)
        self.assertEqual(cells[0]["number_format"],"0.00")
        self.assertTrue(cells[1]["is_formula"])
        self.assertIn("A1:B1",(reader.folder/workbook["id"]/"content.txt").read_text())
        doc = next(m for m in report["materials"] if m["format"]==".docx")
        self.assertIn("gridSpan",(reader.folder/doc["id"]/"content.txt").read_text())
        self.assertIn("中文",reader.office_part(doc["id"],"word/document.xml",0,10000)["text"])
        for suffix in (".tif",".gif"):
            item = next(m for m in report["materials"] if m["format"]==suffix)
            self.assertEqual(len(item["images"]),2)


    def test_numeric_identity_not_inferred_from_same_value(self):
        from biotracebench_scoring.evaluation import canonical
        from decimal import Decimal
        self.assertNotEqual(canonical(0),canonical(None))
        self.assertNotEqual(canonical("NR"),canonical("NE"))
        self.assertNotEqual(canonical("<0.2"),canonical(Decimal("0.2")))
        self.assertEqual(canonical(Decimal("0.100000000000000000001")),("number","0.100000000000000000001"))
        other = copy.deepcopy(ANSWER)
        other["sample"][0]["sample_name"] = "unrelated source"
        other["sample"][0]["species"] = "mouse"
        result = score(other,ANSWER,DICTIONARY,POLICY)
        self.assertFalse(result["pairs"]["sample"])

    def test_bootstrap_paired_study_and_failure_retention(self):
        perfect = score(ANSWER,ANSWER,DICTIONARY,POLICY)
        failed = score(None,ANSWER,DICTIONARY,POLICY)
        studies = [{"study_id":"study1","domain":"basic","conditions":{"initial":failed,"ordinary_review":perfect,"integrated_review":perfect}},
                   {"study_id":"study2","domain":"clinical","conditions":{"initial":perfect,"ordinary_review":perfect,"integrated_review":perfect}}]
        result = aggregate(studies)
        self.assertEqual(result["means"]["overall"]["initial"]["field"]["f1"],0.5)
        self.assertEqual(result["paired_differences"]["overall:field:ordinary_review-initial"]["mean"],0.5)
        self.assertEqual(result,aggregate(studies))

    def test_clinical_four_tables_direction_and_id_renaming(self):
        tables = {
            "population": {"identifier":"population_id","fields":[{"key":k} for k in ["population_id","population_name","population_size"]]},
            "measure": {"identifier":"measure_id","fields":[{"key":k} for k in ["measure_id","measure_name"]]},
            "result": {"identifier":"result_id","references":{"population_id":"population","measure_id":"measure"},"fields":[{"key":k} for k in ["result_id","population_id","measure_id","statistic_type","result_value","comparison"]]},
            "population_relation": {"references":{"population_a_id":"population","population_b_id":"population"},"fields":[{"key":k} for k in ["population_a_id","relationship","population_b_id"]]}}
        gold = {"population":[{"population_id":"P1","population_name":"trial","population_size":10},{"population_id":"P2","population_name":"subset","population_size":5}],
                "measure":[{"measure_id":"M1","measure_name":"DFS"}],
                "result":[{"result_id":"R1","population_id":"P1","measure_id":"M1","statistic_type":"HR","result_value":0,"comparison":"P1 versus P2"}],
                "population_relation":[{"population_a_id":"P2","relationship":"subset of","population_b_id":"P1"}]}
        predicted = json.loads(json.dumps(gold).replace('P1','GROUP_B').replace('P2','GROUP_A').replace('M1','ENDPOINT').replace('R1','STATISTIC'))
        predicted["population"].reverse()
        result = score(predicted,gold,tables,POLICY)
        self.assertEqual(result["field"]["f1"],1)
        self.assertEqual(result["record"]["f1"],1)
        relation = predicted["population_relation"][0]
        relation["population_a_id"],relation["population_b_id"] = relation["population_b_id"],relation["population_a_id"]
        wrong = score(predicted,gold,tables,POLICY)
        self.assertLess(wrong["field"]["f1"],1)
        gold["population_relation"][0]["relationship"] = relation["relationship"] = "disjoint from"
        self.assertEqual(score(predicted,gold,tables,POLICY)["field"]["f1"],1)

    def test_missing_usage_remains_unknown_and_unit_rules_explicit(self):
        from biotracebench.cost import calculate
        self.assertIsNone(calculate({"prompt_tokens":1},TARIFF)["amount"])
        gold = copy.deepcopy(ANSWER)
        gold["condition"][0].update(factor_value=0.001,factor_unit="g")
        predicted = copy.deepcopy(gold)
        predicted["condition"][0].update(factor_value=1,factor_unit="mg")
        dictionary=copy.deepcopy(DICTIONARY)
        dictionary["condition"]["fields"].append({"key":"factor_unit"})
        policy=copy.deepcopy(POLICY)
        policy["field_rules"]["condition.factor_value"]={"unit_field":"factor_unit","canonical_unit":"g","unit_scales":{"g":"1","mg":"0.001"}}
        self.assertEqual(score(predicted,gold,dictionary,policy)["field"]["f1"],1)
        self.assertLess(score(predicted,gold,dictionary,POLICY)["field"]["f1"],1)

    def test_worker_notifies_only_on_error(self):
        from biotracebench.worker import main
        argv=["worker","--manifest","synthetic.json","--out",str(self.root),"--execute"]
        with patch('sys.argv',argv),patch('biotracebench.worker.run',return_value={"failure":{"status":"paused_unknown"}}),patch('biotracebench.worker.notify_error') as notification:
            self.assertEqual(main(),1)
            notification.assert_called_once_with(str(self.root))
        with patch('sys.argv',argv),patch('biotracebench.worker.run',return_value={"failure":None}),patch('biotracebench.worker.notify_error') as notification:
            self.assertEqual(main(),0)
            notification.assert_not_called()

    def test_desktop_notification_does_not_poll(self):
        from biotracebench.worker import notify_error
        with patch('biotracebench.worker.sys.platform','darwin'),patch('biotracebench.worker.subprocess.run') as process:
            process.return_value.returncode=0
            notify_error(self.root)
            self.assertEqual(process.call_count,1)
        self.assertEqual(read(self.root/'notification.json')['status'],'submitted_to_os')
