"""Frozen field-specific text equivalence and auditable manual decisions."""
from decimal import Decimal, InvalidOperation

from model_conversation.archive import digest
from .scoring_items import field_role, safe

CONTRACT = "biotracebench-text-equivalence-1"
TEXT_KEYS = {"aliases", "normalize_space", "casefold", "normalize_comparators"}


def normalize_text(value, rule):
    """Apply only explicitly declared, meaning-preserving text operations."""
    if rule.get("normalize_comparators"):
        value = value.translate(str.maketrans({"＜": "<", "＞": ">", "＝": "=", "≤": "<=", "≥": ">="}))
    return _normalize(value, rule)


def _normalize(value, rule):
    if rule.get("normalize_space"):
        value = " ".join(value.split())
    return value.casefold() if rule.get("casefold") else value


def _numeric(value):
    try:
        Decimal(value)
        return True
    except InvalidOperation:
        return False


def validate_rules(dictionary, policy):
    for declared, keys in policy.get("semantic_context_fields", {}).items():
        table, separator, field = declared.partition(".")
        if not separator or not isinstance(keys, list) or not keys or any(not isinstance(k, str) for k in keys):
            raise ValueError("Semantic context requires a field and explicit context field names")
        if table in dictionary:
            known = {f["key"] for f in dictionary[table]["fields"]}
            if field not in known or set(keys) - known:
                raise ValueError("Semantic context must use declared fields")
    for declared, rule in policy.get("field_rules", {}).items():
        if not isinstance(rule, dict):
            raise ValueError("Field rules must be objects")
        if not TEXT_KEYS.intersection(rule):
            continue
        if policy.get("text_contract") != CONTRACT:
            raise ValueError("Text equivalence requires a versioned contract")
        if not isinstance(rule.get("text_basis"), str) or not rule["text_basis"].strip():
            raise ValueError("Text equivalence requires a predeclared written basis")
        for flag in ("normalize_space", "casefold", "normalize_comparators"):
            if flag in rule and type(rule[flag]) is not bool:
                raise ValueError("Text normalization switches must be explicit booleans")
        aliases = rule.get("aliases", {})
        if not isinstance(aliases, dict):
            raise ValueError("Aliases must map exact strings to canonical strings")
        for original, canonical in aliases.items():
            if (not isinstance(original, str) or not isinstance(canonical, str)
                    or not original.strip() or not canonical.strip()):
                raise ValueError("Aliases cannot introduce missing, empty or non-text values")
            if _numeric(original) or _numeric(canonical):
                raise ValueError("Text aliases cannot rewrite numeric values")
            if normalize_text(original, rule) != original or normalize_text(canonical, rule) != canonical:
                raise ValueError("Alias keys and values must already use the declared text normalization")
            if aliases.get(canonical, canonical) != canonical:
                raise ValueError("Alias chains and cycles are not allowed; use a single canonical form")
            if original.upper() in {"NR", "NE"} and canonical.upper() != original.upper():
                raise ValueError("NR and NE cannot be collapsed by text aliases")
        table, _, key = declared.partition(".")
        if table not in dictionary:
            continue  # Shared domain policy; table-name validation is upstream.
        spec = dictionary[table]
        known = {f["key"]: f for f in spec["fields"]}
        unit_fields = {r["unit_field"] for f, r in policy.get("field_rules", {}).items()
                       if f.startswith(table + ".") and isinstance(r, dict) and "unit_field" in r}
        if (key not in known or field_role(table, key, spec, policy) != "scientific"
                or key in spec.get("references", {}) or key.endswith("_accession")
                or key in unit_fields | {"result_unit", "factor_unit", "relationship", "population_size"}
                or known[key].get("type") in ("integer", "number")
                or declared in policy.get("compound_fields", [])):
            raise ValueError("Text rules cannot alter IDs, units, counts, relations or compound/numeric fields")


def normalization_audit(row, table, policy):
    audit = []
    for key, item in row["items"].items():
        rule = policy.get("field_rules", {}).get(table + "." + key, {})
        if TEXT_KEYS.intersection(rule) and isinstance(item["raw"], str):
            audit.append({"row_id": row["id"], "field": key, "original": item["raw"],
                          "normalized": item["value"], "state": item["state"],
                          "rule_identity": digest(rule), "basis": rule["text_basis"]})
    return audit


def compare_text(left, right, table, field, context, decisions, policy):
    a, b = left["items"][field], right["items"][field]
    rule = policy.get("field_rules", {}).get(table + "." + field, {})
    log = {"table": table, "field": field, "prediction_row": left["id"], "reference_row": right["id"],
           "submitted": a["raw"], "reference": b["raw"],
           "submitted_normalized": a["value"], "reference_normalized": b["value"]}
    context_keys = policy.get("semantic_context_fields", {}).get(table + "." + field, [])
    context_equal = all(right['items'].get(k, {}).get('count_as_field') is False
                        or left["raw"].get(k) == right["raw"].get(k) for k in context_keys)
    if a["value"] == b["value"] and context_equal:
        log.update(status="canonical_text_equal", equal=True)
        if TEXT_KEYS.intersection(rule):
            log.update(rule_identity=digest(rule), basis=rule["text_basis"])
        return True, None, None, log
    qid = digest({"context": context, "prediction": left["id"], "reference": right["id"], "item": field})
    log["id"] = qid
    decision = decisions.get("equivalences", {}).get(qid)
    if decision is not None:
        if (not isinstance(decision, dict) or type(decision.get("equal")) is not bool
                or not isinstance(decision.get("basis"), str) or not decision["basis"].strip()):
            raise ValueError("Text equivalence decision requires a boolean and written basis")
        log.update(status="human_adjudicated", equal=decision["equal"], basis=decision["basis"],
                   adjudication=safe(decision))
        return decision["equal"], None, qid, log
    queue = {"id": qid, "kind": "text_equivalence", "table": table, "field": field,
             "comparison_unit": "whole_field", "context_fields": context_keys,
             "submitted": a["raw"], "reference": b["raw"],
             "submitted_record": safe(left["raw"]),
             "reference_record": safe(right["raw"])}
    log.update(status="pending_adjudication", equal=None)
    return False, queue, qid, log
