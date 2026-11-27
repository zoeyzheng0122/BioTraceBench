"""Shared database and annotation transport; scientific tables are unchanged."""
import copy
import re
from .common import digest
from model_conversation.archive import exact_json

LEGACY_PROTOCOL = "biotracebench-database-annotations-1"
PROTOCOL = "biotracebench-database-annotations-2"
RELATION_KEY_FIELDS = ("population_a_id", "relationship", "population_b_id")


def evaluable_json(text):
    """Read an exact object or its intact prefix followed by one surplus brace.

    This preserves submitted values and rejects duplicate keys in the prefix.
    Format validity remains a separate observation from evaluable content.
    """
    try:
        return exact_json(text), {"mode": "exact_json", "strict_json_valid": True}
    except ValueError as original:
        import json
        start = len(text) - len(text.lstrip())
        try:
            # raw_decode locates a boundary only. exact_json is authoritative
            # for duplicate keys, decimal precision and nonfinite numbers.
            candidate, end = json.JSONDecoder().raw_decode(text, start)
            if not isinstance(candidate, dict) or text[end:].strip() != "}":
                raise original
            value = exact_json(text[start:end])
        except (ValueError, TypeError):
            raise original
        return value, {"mode": "complete_object_one_trailing_brace",
                       "strict_json_valid": False, "error": "invalid_final_json",
                       "character_start": start, "character_end": end,
                       "trailing_text": text[end:], "scientific_values_rewritten": False}

def schema(database_schema, protocol=PROTOCOL):
    if protocol not in {PROTOCOL, LEGACY_PROTOCOL}:
        raise ValueError("Unknown submission protocol")
    annotation = {"type": "object", "additionalProperties": False, "properties": {
        "table": {"type": "string"}, "record_id": {"type": "string"},
        "field": {"type": ["string", "null"]}, "kind": {"type": "string", "enum": ["evidence", "note", "state"]},
        "source": {"type": ["string", "null"]}, "locator": {"type": ["string", "null"]}, "text": {"type": "string"}}}
    annotation["required"] = list(annotation["properties"])
    if protocol == PROTOCOL:
        primary = copy.deepcopy(annotation)
        primary["properties"]["record_id"]["minLength"] = 1
        primary["properties"]["record_key"] = {"type": "null"}
        primary["required"].append("record_key")
        relation = copy.deepcopy(primary)
        relation["properties"]["table"] = {"type": "string", "enum": ["population_relation"]}
        relation["properties"]["record_id"] = {"type": "null"}
        relation["properties"]["record_key"] = {
            "type": "object", "additionalProperties": False, "required": list(RELATION_KEY_FIELDS),
            "properties": {key: {"type": "string", "minLength": 1} for key in RELATION_KEY_FIELDS}}
        names = database_schema.get("properties", {})
        identifiers = sorted(set(names) - {"population_relation"})
        if identifiers:
            primary["properties"]["table"]["enum"] = identifiers
        alternatives = ([primary] if identifiers or not names else []) + ([relation] if "population_relation" in names or not names else [])
        annotation = {"anyOf": alternatives}
    return {"type": "object", "additionalProperties": False, "required": ["database", "annotations"],
            "properties": {"database": copy.deepcopy(database_schema), "annotations": {"type": "array", "items": annotation}}}


def extract(value):
    """Preserve direct/legacy submissions diagnostically; never repair their rows."""
    if isinstance(value, dict) and "database" in value:
        return value["database"], value.get("annotations"), "paired" if set(value) == {"database", "annotations"} else "unexpected_transport"
    return value, None, "direct_database_without_annotations"


def annotation_record(raw, database, dictionary, reader, *, case, stage, raw_hash, database_hash, transport, protocol=PROTOCOL):
    from .schema import validate
    issues = []
    if transport != "paired":
        issues.append({"error": transport, "retained_in_raw_answer": True})
    items = raw if isinstance(raw, list) else []
    if not isinstance(raw, list):
        issues.append({"error": "missing_or_invalid_annotations", "raw_retained": True})
    shape = schema({}, protocol)["properties"]["annotations"]["items"]
    for index, item in enumerate(items):
        errors = validate(item, shape)
        if errors:
            issues.append({"annotation": index, "error": "annotation_structure", "details": errors})
            continue
        table = item["table"]
        rows = database.get(table, []) if isinstance(database, dict) else []
        spec = dictionary.get(table, {})
        identifier = spec.get("identifier")
        matching = []
        if isinstance(rows, list):
            if identifier and item["record_id"] is not None and item.get("record_key") is None:
                matching = [row for row in rows if isinstance(row, dict) and row.get(identifier) == item["record_id"]]
            elif protocol == PROTOCOL and table == "population_relation" and item["record_id"] is None:
                key = item["record_key"]
                matching = [row for row in rows if isinstance(row, dict)
                            and all(row.get(field) == key[field] for field in RELATION_KEY_FIELDS)]
        if not spec or len(matching) != 1:
            issues.append({"annotation": index, "error": "ambiguous_record_binding" if len(matching) > 1 else "unresolved_record_binding"})
        if item["field"] is not None and item["field"] not in {f["key"] for f in spec.get("fields", [])}:
            issues.append({"annotation": index, "error": "unknown_field"})
        if item["source"] is not None and item["source"] not in reader.entries:
            issue = {"annotation": index, "error": "unknown_material"}
            material_ids = re.split(r"\s*[;,]\s*", item["source"].strip())
            if len(material_ids) > 1 and all(mid in reader.entries for mid in material_ids):
                issue.update(reason="multiple_material_ids_in_single_source", material_ids=material_ids)
            issues.append(issue)
        if item["kind"] == "evidence" and (not item["source"] or not item["locator"]):
            issues.append({"annotation": index, "error": "missing_evidence_location"})
    return {"protocol": protocol, "case_id": case, "stage": stage,
            "database_file": "database.json", "database_sha256": database_hash,
            "raw_answer_sha256": raw_hash, "material_identity": reader.identity,
            "dataset_identity": reader.manifest.get("dataset_identity"),
            "received": raw is not None, "annotations": raw, "diagnostics": issues,
            "scientific_support": "not_evaluated", "identity": digest({"raw": raw, "database_sha256": database_hash, "material_identity": reader.identity})}
