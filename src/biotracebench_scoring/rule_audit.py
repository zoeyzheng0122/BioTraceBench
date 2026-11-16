"""Read-only preparation of scoring rules; never scores or freezes a policy.

Reference observations stay in the caller's external audit directory. Material
contents, predictions, credentials and provider APIs are outside this command.
Candidates found in text are review prompts, not scientific adjudications.
"""
import collections
import csv
import hashlib
import json
import platform
import re
import zipfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from model_conversation.archive import digest, seal, write
from biotracebench.dataset_identity import task_sources
from biotracebench.material_selection import select_materials, PDF_POLICY
from biotracebench.schema import check_schema, references, validate
from .identity_alignment import accession_tokens, scoped_policy
from .reference_policy import fixed_reference, CONTRACT as REFERENCE_CONTRACT
from .scoring_items import safe

PROTOCOL = "biotracebench-rule-preparation-1"
WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TEXT_SIGNALS = {
    "source_conflict": r"\b(?:conflict\w*|contradict\w*|discrepanc\w*)\b",
    "explicit_missing_state": r"\b(?:not reported|unreported|not applicable|not estimable|not reached|unresolved)\b",
    "source_precision": r"\b(?:precision|decimal places|rounding|round\w*)\b",
    "permitted_conversion": r"\b(?:conversion|convert\w*|12 months per year)\b",
}


class Inputs:
    """Allowlisted text/document inputs, with byte identities for every read."""
    def __init__(self):
        self.files = {}

    def read(self, path):
        path = Path(path).resolve()
        if path.suffix.lower() not in {".json", ".md", ".csv", ".docx"} or "materials" in path.parts:
            raise ValueError("Rule preparation cannot open material contents or unsupported formats")
        raw = path.read_bytes()
        self.files[str(path)] = hashlib.sha256(raw).hexdigest()
        return raw

    def json(self, path):
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError("Duplicate JSON key in rule input: " + key)
                result[key] = value
            return result
        def invalid(value):
            raise ValueError("Nonfinite JSON number in rule input: " + value)
        return json.loads(self.read(path).decode("utf-8-sig"), parse_float=Decimal,
                          object_pairs_hook=pairs, parse_constant=invalid)


def paper_text(raw):
    """Accepted main-body text; deleted/moved-from text is not authority."""
    import io
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    def text(element):
        if element.tag in {WORD + "del", WORD + "moveFrom"}:
            return ""
        if element.tag == WORD + "t":
            return element.text or ""
        return "".join(text(child) for child in element)
    return "\n".join(text(p) for p in root.iter(WORD + "p") if text(p).strip())


def signals(text):
    return {name: [line.strip() for line in text.splitlines() if re.search(pattern, line, re.I)]
            for name, pattern in TEXT_SIGNALS.items() if re.search(pattern, text, re.I)}


def reference_path(root, case, domain):
    base = (root / "gold_standard" / domain / case).resolve()
    path = (base / (case + ".json")).resolve()
    if not base.is_relative_to(root / "gold_standard") or not path.is_relative_to(base):
        raise ValueError("Reference path escapes its case")
    return path


def reference_observations(gold, dictionary, schema, policy):
    """Inspect shape, states and identity candidates without matching any answer."""
    if not isinstance(gold, dict):
        raise ValueError("Reference must be a database object")
    fixed = fixed_reference(policy)
    check_schema(schema)
    errors = validate(gold, schema)
    rows_well_formed = all(isinstance(gold.get(t), list) and all(isinstance(r, dict) for r in gold[t])
                           for t in dictionary)
    links = references(gold, dictionary) if rows_well_formed else [{"error": "uncheckable_reference_shape"}]
    nulls, missing, annotations, duplicates, identity, units = [], [], [], [], {}, {}
    numeric_expressions, zero_values = [], []
    field_roles = {}
    for table, spec in dictionary.items():
        rows = gold.get(table, [])
        if not isinstance(rows, list):
            continue
        identifier = spec.get("identifier")
        known = {f["key"] for f in spec["fields"]}
        field_roles.update({table + "." + key: "identifier" if key == identifier else "scientific"
                            for key in known})
        seen = collections.defaultdict(list)
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            locator = {"table": table, "row_index": index, "record_id": row.get(identifier) if identifier else None}
            seen[digest(safe({k: v for k, v in row.items() if k != identifier}))].append(index)
            for field in spec["fields"]:
                key = field["key"]
                if key == identifier:
                    continue
                item = {**locator, "field": key}
                if key not in row:
                    missing.append(item)
                    continue
                value = row[key]
                if value is None:
                    nulls.append({**item, "state": "undetermined", "decision": None,
                                  **({'scoring_disposition':'excluded_reference_item',
                                      'count_as_field':False,'reference_contract':REFERENCE_CONTRACT,
                                      'source_state_inferred':False} if fixed else {})})
                elif type(value) is not bool and isinstance(value, (int, Decimal)) and value == 0:
                    zero_values.append(item)
                if isinstance(value, str) and (found := signals(value)):
                    annotations.append({**item, "value": value, "text_signals": sorted(found),
                                        "classification": "candidate_only"})
                if key in {"factor_value", "result_value"} and isinstance(value, str):
                    numeric_expressions.append({**item, "value": value})
                if key.endswith("_unit"):
                    units.setdefault(table + "." + key, collections.Counter())[value] += 1
        duplicates.extend({"table": table, "row_indices": indices, "status": "candidate_reference_duplicate"}
                          for indices in seen.values() if len(indices) > 1)
        # These are raw-reference discriminators, not a prediction/reference alignment.
        groups = []
        for group in policy.get("identity_groups", {}).get(table, []):
            buckets, incomplete = collections.defaultdict(list), []
            for index, row in enumerate(rows):
                if not isinstance(row, dict) or any(row.get(k) in (None, "", []) for k in group):
                    incomplete.append(index)
                    continue
                buckets[digest(safe([row[k] for k in group]))].append(index)
            groups.append({"fields": group, "incomplete_rows": incomplete,
                           "colliding_rows": [v for v in buckets.values() if len(v) > 1]})
        anchors = {}
        for key, levels in policy.get("identity_accessions", {}).get(table, {}).items():
            anchors[key] = {"object_level_rows": [i for i, row in enumerate(rows)
                             if isinstance(row, dict) and accession_tokens({"raw": row}, key, levels)],
                            "accepted_levels": levels}
        native_labels = {}
        from .native_identity import validate as validate_native, extract as extract_native
        for key, rule in policy.get('identity_native_labels', {}).get(table, {}).items():
            validate_native(rule)
            values, buckets, incomplete = [], collections.defaultdict(list), []
            for index, row in enumerate(rows):
                label = extract_native(row.get(key), rule) if isinstance(row, dict) else None
                values.append({'row_index': index, 'identity': safe(label)})
                if label is None:
                    incomplete.append(index)
                else:
                    buckets[digest(safe(label))].append(index)
            native_labels[key] = {'rule_identity': digest(rule), 'identities': values,
                                  'incomplete_rows': incomplete,
                                  'colliding_rows': [v for v in buckets.values() if len(v) > 1]}
        identity[table] = {"groups": groups, "accessions": anchors,
                           **({'native_labels': native_labels} if native_labels else {}),
                           "scientific_identity_approved": False,
                           "warning": "Raw uniqueness does not prove source identity or robust alignment"}
    return {**({'reference_contract':REFERENCE_CONTRACT} if fixed else {}),
            "record_counts": {t: len(gold[t]) if isinstance(gold.get(t), list) else 0 for t in dictionary},
            "schema_errors": errors, "reference_errors": links, "null_fields": nulls, "missing_fields": missing,
            "state_and_conflict_candidates": annotations, "duplicate_record_candidates": duplicates,
            "identity_candidates": identity, "field_roles_draft": field_roles,
            "units": {k: [{"unit": unit, "count": count} for unit, count in sorted(v.items(), key=lambda p: str(p[0]))]
                      for k, v in units.items()},
            "numeric_text": numeric_expressions, "genuine_zero_fields": zero_values}


def embedded_schemas(text):
    """Only parse explicitly fenced JSON; a malformed contract remains visible."""
    result = []
    for block in re.findall(r"```json\s*\n(.*?)\n```", text, re.S):
        try:
            value = json.loads(block)
        except ValueError:
            result.append(None)
            continue
        if isinstance(value, dict) and value.get("type") == "object" and "properties" in value:
            result.append(value)
    return result


def inspect_case(inputs, root, case, domain, policy):
    task, paths = task_sources(root, case, domain)
    inputs.json(paths["task"])
    manifest = inputs.json(paths["materials_manifest"])
    dictionary = inputs.json(paths["field_dictionary"])[domain]
    schema = inputs.json(paths["schema"])
    prompt = inputs.read(paths["prompt"]).decode("utf-8-sig") if "prompt" in paths else ""
    complete = inputs.read(paths["complete_prompt"]).decode("utf-8-sig")
    gold_path = reference_path(root, case, domain)
    gold = inputs.json(gold_path)
    observed = reference_observations(gold, dictionary, schema, scoped_policy(policy, {"case_id": case}))
    contracts = embedded_schemas(complete)
    prompt_contract_status = ("matches" if len(contracts) == 1 and contracts[0] == schema else
                              "missing" if not contracts else "different_or_ambiguous")
    declared = [x for x in manifest.get("files", []) if x.get("input_use") == "model"]
    selected, excluded = select_materials(manifest.get("files", []))
    declared_paths = {x["path"] for x in declared}
    pdfs = [x["path"] for x in excluded if x["path"] in declared_paths and Path(x["path"]).suffix.lower() == ".pdf"]
    included_pdfs = [x["path"] for x in selected if Path(x["path"]).suffix.lower() == ".pdf"]
    # Preserve every task-specific declaration, including prose outside case_specific_rules.
    declarations = {key: value for key, value in task.items() if key not in
                    {"prompt", "complete_prompt", "materials_manifest", "schema", "field_dictionary"}}
    review_sections = []
    for key in ("case_specific_rules", "case_rules", "row_granularity", "requested_items"):
        value = task.get(key)
        if value:
            review_sections.append({"source": str(paths["task"].relative_to(root)), "json_key": key, "value": value})
    text = prompt + "\n" + json.dumps(declarations, ensure_ascii=False)
    return {"case_id": case, "domain": domain, "study_id": task.get("doi"),
            "status": "review_required", "frozen": False, "source_scientific_audit": "not_performed",
            "paths": {k: str(p.relative_to(root)) for k, p in paths.items()},
            "reference_path": str(gold_path.relative_to(root)), "task_definition": declarations,
            "prompt_text": prompt, "complete_prompt_characters": len(complete),
            "embedded_schema": prompt_contract_status, "case_declarations": review_sections,
            "task_text_signals": signals(text), "observations": observed,
            "material_scope": {"declared_model_files": len(declared), "excluded_pdf_files": pdfs,
                               "included_pdf_files": included_pdfs, "selected_files": len(selected),
                               "remaining_non_pdf_files": len(selected) - len(included_pdfs),
                               "pdf_policy": PDF_POLICY, "contents_read": False,
                               "source_sufficiency": "not_established"},
            "approval": {"applicability": None, "identity": None, "information_states": None,
                         "units_and_precision": None, "semantic_review": None}}


def questions(tasks, policy=None):
    """Group specific observations; keep every answer blank for human discussion."""
    def cases(predicate):
        return [t["case_id"] for t in tasks if predicate(t)]
    specs = [
        ("R01", "Reference information states", cases(lambda t: t["observations"]["null_fields"]),
         "Null does not identify not_reported, not_applicable or unresolved. Prepare source-grounded state sidecars before final scoring; never infer state from null alone."),
        ("R02", "Allowed exact units and time conversions", cases(lambda t: t["observations"]["units"]),
         "Approve a finite field- and quantity-specific conversion list. Existing mg/microgram draft rules do not cover observed concentrations, durations and scales. Keep supplementary fields whole and verify their units too."),
        ("R03", "Reference validity and task-specific identity", cases(lambda t: t["observations"]["schema_errors"]
              or t["observations"]["reference_errors"] or t["observations"]["duplicate_record_candidates"]
              or any(g["incomplete_rows"] or g["colliding_rows"] for v in t["observations"]["identity_candidates"].values()
                     for g in v["groups"])),
         "Separate reference defects from incomplete identity candidates. Source-level identifiers or reviewed native labels establish identity; project IDs, numerical equality and row order do not."),
        ("R04", "Conflicting source versions and alternative representations", cases(lambda t:
              "source_conflict" in t["task_text_signals"] or any("source_conflict" in c["text_signals"]
              for c in t["observations"]["state_and_conflict_candidates"])),
         "Preserve existing task source precedence. Define a reviewed reference correction or acceptable-alternative record when reference content is doubtful; do not silently edit gold or penalize a supported alternative."),
        ("R05", "Source-bound precision exceptions", cases(lambda t: "source_precision" in t["task_text_signals"]),
         "Preserving printed precision is not permission to round. Exact comparison remains the confirmed default; any extra rounding needs a specific source, target and rounding method."),
        ("R06", "Qwen scope and one human check", [t["case_id"] for t in tasks],
         "The current judge handles aligned semantic/state-equivalence proposals only. Unresolved field states, object identity, conversions and reference defects remain explicit human queues. Confirm the operational review scope and an independent scoring-audit procedure before formal release."),
        ("R07", "Reference availability in selected materials", cases(lambda t: t["material_scope"]["excluded_pdf_files"] or t["material_scope"]["included_pdf_files"]),
         "Use structured article sources and complete PDF attachment representations. Inventory alone does not establish reference evidence coverage. Check required evidence and record unresolved gaps without marking them source-unreported."),
    ]
    # Some observations require evidence work, not another vote on an already
    # confirmed principle. Never turn every literal warning into a user question.
    status = {"R01": "pending_user_decision", "R02": "pending_user_decision",
              "R03": "needs_source_review", "R04": "needs_source_review",
              "R05": "confirmed_exact_default_no_new_exception",
              "R06": "pending_user_decision", "R07": "needs_source_review"}
    if fixed_reference(policy or {}):
        status['R01'] = 'determined_by_fixed_reference_contract'
        specs[0] = ('R01','Fixed-reference empty-item rule',specs[0][2],
                    'Blank reference fields are excluded by the approved fixed-reference contract; '
                    'matching blanks earn no credit and nonempty extras are FP. '
                    'No per-null source-state sidecar is required. Explicit scientific states remain evaluated; '
                    'reference defects are separate review issues, never automatic amendments.')
    return [{"id": key, "title": title, "case_ids": ids, "status": status[key],
             "requires_user_decision_now": status[key] == "pending_user_decision",
             "answer": None, "recommendation": recommendation} for key, title, ids, recommendation in specs]


def summarize(tasks):
    nulls, counts, errors = collections.Counter(), collections.Counter(), collections.Counter()
    for task in tasks:
        obs = task["observations"]
        counts.update(obs["record_counts"])
        nulls.update(x["table"] + "." + x["field"] for x in obs["null_fields"])
        for key in ("schema_errors", "reference_errors", "missing_fields", "duplicate_record_candidates"):
            errors[key] += len(obs[key])
    return {"tasks": len(tasks), "domains": dict(collections.Counter(t["domain"] for t in tasks)),
            "reference_records": sum(counts.values()), "records_by_table": dict(counts),
            "null_fields": sum(nulls.values()), "nulls_by_field": dict(sorted(nulls.items())),
            "tasks_with_nulls": sum(bool(t["observations"]["null_fields"]) for t in tasks),
            "embedded_schema_status": dict(collections.Counter(t["embedded_schema"] for t in tasks)),
            "reference_checks": dict(errors),
            "declared_model_files": sum(t["material_scope"]["declared_model_files"] for t in tasks),
            "excluded_pdf_files": sum(len(t["material_scope"]["excluded_pdf_files"]) for t in tasks),
            "included_pdf_files": sum(len(t["material_scope"]["included_pdf_files"]) for t in tasks),
            "remaining_non_pdf_files": sum(t["material_scope"]["remaining_non_pdf_files"] for t in tasks),
            "frozen": False, "scientific_audit_completed": False, "model_calls": 0}


def audit(dataset, policy_path, paper, out, expected_tasks):
    root, out = Path(dataset).resolve(), Path(out).resolve()
    source_file = Path(__file__).resolve()
    source_root = source_file.parents[2]
    if out.is_relative_to(root) or out.is_relative_to(source_root):
        raise ValueError("Write audit artifacts outside dataset and source repositories")
    if type(expected_tasks) is not int or expected_tasks < 1:
        raise ValueError("An explicit positive expected task count is required")
    inputs = Inputs()
    policy = inputs.json(policy_path)
    if policy.get("frozen") is not False:
        raise ValueError("This preparation command requires an explicitly unfrozen policy")
    raw_paper = inputs.read(paper)
    paper_hash = hashlib.sha256(raw_paper).hexdigest()
    if paper_hash != policy.get("current_authority", {}).get("sha256"):
        raise ValueError("Manuscript does not match the policy's declared authority")
    authority = paper_text(raw_paper)
    for path in sorted((root / "tasks/shared").glob("*")):
        if path.is_file() and path.suffix.lower() in {".json", ".md"}:
            inputs.read(path)
    if (root / "metadata/release.json").exists():
        inputs.json(root / "metadata/release.json")
    tasks, failures = [], []
    declarations = [(domain, p.parent.name) for domain in ("basic", "clinical")
                    for p in sorted((root / "tasks" / domain).glob("*/task.json"))]
    if len(declarations) != expected_tasks or len({c for _, c in declarations}) != expected_tasks:
        raise ValueError("Task inventory differs from the explicitly expected count")
    for domain, case in declarations:
        try:
            tasks.append(inspect_case(inputs, root, case, domain, policy))
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
            failures.append({"case_id": case, "domain": domain, "status": "blocked",
                             "error_type": type(error).__name__, "message": str(error)})
    # Failures remain in the audit and make the overall check incomplete.
    result = {"protocol": PROTOCOL, "status": "draft_review_required" if not failures else "incomplete",
              "expected_tasks": expected_tasks, "inspected_tasks": len(tasks), "failures": failures,
              "summary": summarize(tasks), "policy_unchanged": True, "reference_unchanged": True,
              "limits": ["No source-content scientific audit", "No automatic null-state decisions",
                         "No scores or model comparisons", "No policy activation or approval"]}
    for path, before in inputs.files.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != before:
            raise ValueError("An inspected input changed during the audit")
    out.mkdir(parents=True, exist_ok=False)
    write(out / "audit.json", result)
    write(out / "task-rule-drafts.json", safe(tasks))
    write(out / "confirmation-queue.json", questions(tasks, policy))
    with (out / "task-inventory.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["case_id", "domain", "status", "records", "null_fields",
                  "schema_errors", "reference_errors", "embedded_schema", "excluded_pdfs", "remaining_non_pdf_files"])
        writer.writeheader()
        for task in tasks:
            obs = task["observations"]
            writer.writerow({"case_id": task["case_id"], "domain": task["domain"], "status": task["status"],
                             "records": sum(obs["record_counts"].values()), "null_fields": len(obs["null_fields"]),
                             "schema_errors": len(obs["schema_errors"]), "reference_errors": len(obs["reference_errors"]),
                             "embedded_schema": task["embedded_schema"],
                             "excluded_pdfs": len(task["material_scope"]["excluded_pdf_files"]),
                             "remaining_non_pdf_files": task["material_scope"]["remaining_non_pdf_files"]})
        for failed in failures:
            writer.writerow({k: v for k, v in failed.items() if k in writer.fieldnames})
    write(out / "identity.json", {"protocol": PROTOCOL, "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
          "dataset": str(root), "inputs": inputs.files, "paper_sha256": paper_hash,
          "policy_frozen": False, "python": platform.python_version(),
          "implementation": {str(p.relative_to(source_root)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in (source_file, source_file.with_name("scoring_items.py"),
                                       source_file.with_name("identity_alignment.py"),
                                       source_file.with_name("native_identity.py"),
                                       source_file.with_name("reference_policy.py"),
                                       source_root / "src/biotracebench/dataset_identity.py",
                                       source_root / "src/biotracebench/material_selection.py",
                                       source_root / "src/biotracebench/schema.py")}})
    (out / "paper-accepted-text.txt").write_text(authority, encoding="utf-8")
    seal(out)
    return result
