"""Scoring-only projections. Never rewrite a submitted database or infer facts."""
import re
import math
from decimal import Decimal

from model_conversation.archive import digest
from .reference_policy import fixed_reference, blank

STATES = {"reported", "not_reported", "not_applicable", "ambiguous", "conflicting", "unresolved"}
PENDING_STATES = {"unspecified_null", "ambiguous", "conflicting", "unresolved"}
COMPOUND_ITEMS = {"confidence_interval", "confidence_level", "p_value", "standard_deviation",
                  "standard_error", "percentage", "denominator", "analysis_context"}
NUM = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
CI = re.compile(rf"(?:(?P<level>{NUM})\s*%\s*)?(?:CI|confidence interval)\s*[:=]?\s*"
                rf"[\[(]\s*(?P<lower>{NUM})\s*(?:,|\bto\b)\s*(?P<upper>{NUM})\s*[\])]", re.I)
P_VALUE = re.compile(rf"(?:P|P[- ]value)\s*(?P<operator><=|>=|<|>|=|≤|≥)\s*(?P<value>{NUM})", re.I)
DISPERSION = re.compile(rf"(?P<kind>SD|SE)\s*[:=]\s*(?P<value>{NUM})", re.I)
PERCENTAGE = re.compile(rf"(?P<value>{NUM})\s*%")
DENOMINATOR = re.compile(r"(?:(?P<kind>model|endpoint|analysis|evaluable)\s+)?(?:n|denominator)\s*"
                         r"(?:(?:[:=]\s*(?P<count>\d+))|(?P<missing>not (?:separately )?reported))", re.I)


def safe(value):
    """Lossless JSON identity representation, including Decimal-loaded numbers."""
    if isinstance(value, Decimal):
        return {"decimal_lexeme": str(value)}
    if isinstance(value, float) and not math.isfinite(value):
        return {"invalid_float": str(value)}
    if isinstance(value, dict):
        return {key: safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe(item) for item in value]
    return value


def finite(value):
    if isinstance(value, Decimal):
        return value.is_finite()
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(finite(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return all(finite(v) for v in value)
    return True


def item_value(name, value):
    """Validate human projections with the same value types as the parser."""
    def number(v):
        if isinstance(v, bool) or not isinstance(v, (str, int, float, Decimal)) or not re.fullmatch(NUM, str(v)):
            raise ValueError("Projected statistic must be a finite decimal number")
        return Decimal(str(v))
    if value is None:
        return None
    if name == "confidence_interval":
        if not isinstance(value, dict) or set(value) != {"lower", "upper"}:
            raise ValueError("Interval projection requires labelled lower/upper bounds")
        return {k: number(v) for k, v in value.items()}
    if name == "p_value":
        if not isinstance(value, dict) or set(value) != {"operator", "value"} or value["operator"] not in {"=", "<", ">", "<=", ">="}:
            raise ValueError("P-value projection requires an explicit comparator and value")
        return {"operator": value["operator"], "value": number(value["value"])}
    if name == "denominator":
        if not isinstance(value, dict) or set(value) != {"kind", "count"} or not isinstance(value["kind"], str) or not value["kind"]:
            raise ValueError("Denominator projection requires kind and count")
        count = number(value["count"]) if value["count"] is not None else None
        if count is not None and (count < 0 or count != count.to_integral_value()):
            raise ValueError("Denominator must be an exact nonnegative integer")
        return {"kind": value["kind"], "count": int(count) if count is not None else None}
    if name == "analysis_context":
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Analysis context must be nonempty source text")
        return value
    return number(value)


def field_role(table, key, spec, policy):
    declared = policy.get("field_roles", {}).get(table + "." + key)
    primary = key == spec.get("identifier")
    reference = key in spec.get("references", {})
    known = {f["key"] for f in spec["fields"]}
    role = declared or ("identifier" if primary else "scientific" if key in known else "unclassified")
    if role not in {"scientific", "identifier", "provenance", "unclassified"}:
        raise ValueError("Unknown scoring field role: " + table + "." + key)
    if primary and role != "identifier" or reference and role != "scientific":
        raise ValueError("Primary IDs and scientific references cannot change scoring roles")
    if role == "identifier" and not primary:
        raise ValueError("Only the declared primary identifier is an identifier field")
    return role


def state_for(value, exists, annotation=None):
    if annotation is None:
        return "model_unanswered" if not exists else "unspecified_null" if value is None else "reported"
    if (not isinstance(annotation, dict) or annotation.get("state") not in STATES
            or not isinstance(annotation.get("basis"), str) or not annotation["basis"].strip()):
        raise ValueError("Field-state adjudication requires a supported state and an explicit basis")
    state = annotation["state"]
    if not exists:
        raise ValueError("A missing model field cannot be filled by a state adjudication")
    if state == "reported" and value is None:
        raise ValueError("Null cannot be adjudicated as a reported value")
    if state in {"not_reported", "not_applicable"} and value is not None:
        # Non-null statements need an explicit semantic projection, not silent removal.
        raise ValueError("A non-null value cannot be hidden by a missing/inapplicable state")
    return state


def split_statistics(text):
    """Parse only labelled, unambiguous forms; retain every unsupported segment.

    One interval (both bounds) is one item; its confidence level is separate.
    No value is inferred from another field, a population total, or a reference.
    """
    items, remainder = {}, []
    if not isinstance(text, str) or not text.strip():
        return {}, [text]
    for segment in text.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        found = {}
        if match := CI.fullmatch(segment):
            found["confidence_interval"] = {"value": {"lower": Decimal(match["lower"]), "upper": Decimal(match["upper"])}}
            if match["level"] is not None:
                found["confidence_level"] = {"value": Decimal(match["level"])}
        elif match := P_VALUE.fullmatch(segment):
            found["p_value"] = {"value": {"operator": {"≤": "<=", "≥": ">="}.get(match["operator"], match["operator"]),
                                         "value": Decimal(match["value"])}}
        elif match := DISPERSION.fullmatch(segment):
            found["standard_deviation" if match["kind"].upper() == "SD" else "standard_error"] = {"value": Decimal(match["value"])}
        elif match := PERCENTAGE.fullmatch(segment):
            found["percentage"] = {"value": Decimal(match["value"])}
        elif match := DENOMINATOR.fullmatch(segment):
            found["denominator"] = {"value": {"kind": (match["kind"] or "unspecified").lower(),
                                             "count": int(match["count"]) if match["count"] else None},
                                    "state": "reported" if match["count"] else "not_reported"}
        if not found or any(key in items for key in found):
            remainder.append(segment)
            continue
        for key, value in found.items():
            items[key] = {"state": "reported", **value, "source_text": segment}
    return items, remainder


def project_row(row, side, table, index, spec, policy, context_id, decisions, canonicalize):
    """Return independently bound scoring items and observations for one row."""
    row_id = digest({"context": context_id, "side": side, "table": table, "row_index": index, "raw": safe(row)})
    result, queue, ignored, projection_fields = {}, [], [], []
    known = {field["key"] for field in spec["fields"]}
    fixed = fixed_reference(policy)
    for key in sorted(known | set(row)):
        role = field_role(table, key, spec, policy)
        if role == "unclassified":
            queue.append({"id": digest({"row": row_id, "field": key}), "kind": "content_classification",
                          "side": side, "table": table, "field": key, "row_id": row_id, "raw": safe(row[key])})
        if role != "scientific":
            if key in row:
                ignored.append({"field": key, "role": role})
            continue
        field_id = digest({"row": row_id, "field": key})
        exists, value = key in row, row.get(key)
        annotation = decisions.get("field_states", {}).get(field_id)
        if fixed and blank(value):
            if annotation is not None:
                raise ValueError('Fixed-reference blank fields cannot be promoted by state adjudication')
            state = 'reference_empty' if side == 'reference' and exists else 'model_unanswered'
        else:
            state = state_for(value, exists, annotation)
        if not finite(value):
            state = "unresolved"
        compound = table + "." + key in policy.get("compound_fields", [])
        if compound and state == "reported":
            projection_fields.append(field_id)
            parts, remainder = split_statistics(value)
            supplied = decisions.get("projections", {}).get(field_id)
            if supplied is not None:
                if (not isinstance(supplied, dict) or not supplied.get("basis") or not isinstance(supplied.get("items"), dict)
                        or not supplied["items"] or set(supplied["items"]) - COMPOUND_ITEMS):
                    raise ValueError("Compound projection requires supported items and an adjudication basis")
                parts = {}
                for name, item in supplied["items"].items():
                    if (not isinstance(item, dict) or item.get("state") not in STATES or not isinstance(item.get("source_text"), str)
                            or not item["source_text"] or not isinstance(value, str) or item["source_text"] not in value
                            or "value" not in item):
                        raise ValueError("Each projected item must retain a literal submitted source fragment and its state/value")
                    if item["state"] == "reported" and item["value"] is None:
                        raise ValueError("Reported statistic requires an explicit value")
                    if item["state"] in {"not_reported", "not_applicable"} and item["value"] is not None:
                        if not (name == "denominator" and isinstance(item["value"], dict) and item["value"].get("count") is None):
                            raise ValueError("Missing/inapplicable projection cannot hide a statistic value")
                    parts[name] = {**item, "value": item_value(name, item["value"])}
                # Human-reviewed coverage must explicitly account for the complete field.
                if supplied.get("complete") is not True:
                    raise ValueError("Compound adjudication must explicitly account for the entire submitted field")
                remainder = []
            for name, part in parts.items():
                item_key = key + "." + name
                result[item_key] = {"state": part["state"], "value": canonicalize(part["value"]),
                                    "exists": True, "raw": safe(part["value"]), "source_text": part["source_text"],
                                    "field_id": field_id, "unknown_field": key not in known}
                if part["state"] in PENDING_STATES:
                    queue.append({"id": digest({"field": field_id, "item": name}), "kind": "field_state",
                                  "side": side, "table": table, "row_id": row_id, "field": item_key,
                                  "raw": safe(part["value"]), "state": part["state"]})
            if remainder:
                result[key + ".unparsed"] = {"state": "unresolved", "value": canonicalize(remainder),
                                             "exists": True, "raw": safe(remainder), "field_id": field_id,
                                             "unknown_field": key not in known}
                queue.append({"id": field_id, "kind": "compound_projection", "side": side, "table": table,
                              "row_id": row_id, "field": key, "raw": safe(value), "unparsed": safe(remainder)})
            continue
        normalized = canonicalize(value, policy.get("field_rules", {}).get(table + "." + key, {}))
        if normalized[0] == "number" and not Decimal(normalized[1]).is_finite():
            state = "unresolved"
        result[key] = {"state": state, "value": normalized,
                       "exists": exists, "raw": safe(value), "field_id": field_id, "unknown_field": key not in known}
        if fixed:
            result[key]['count_as_field'] = bool(exists and not blank(value))
        if (state in PENDING_STATES and not (state in {"ambiguous", "conflicting"} and
                decisions.get("field_states", {}).get(field_id))) or side == "reference" and not exists:
            queue.append({"id": field_id, "kind": "field_state", "side": side, "table": table, "row_id": row_id,
                          "field": key, "raw": safe(value), "state": state})
        if key not in known:
            queue.append({"id": digest({"field": field_id, "kind": "unknown_field"}), "kind": "unknown_scientific_field",
                          "side": side, "table": table, "row_id": row_id, "field": key, "raw": safe(value)})
    return {"id": row_id, "index": index, "raw": row, "items": result, "queue": queue,
            "ignored": ignored, "projection_fields": projection_fields}
