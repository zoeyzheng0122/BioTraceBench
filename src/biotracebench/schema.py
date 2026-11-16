"""Validate the shipped contract subset, fail closed on unknown constraints."""
import math
import re
from decimal import Decimal
from .common import digest

SUPPORTED = {"$schema", "$id", "title", "description", "type", "properties", "required",
             "additionalProperties", "items", "minItems", "maxItems", "uniqueItems", "minLength",
             "maxLength", "pattern", "enum", "const", "minimum", "maximum", "examples", "default", "anyOf"}


def check_schema(schema):
    if set(schema) - SUPPORTED:
        raise ValueError("Unsupported schema keywords: " + str(sorted(set(schema) - SUPPORTED)))
    for child in schema.get("properties", {}).values():
        check_schema(child)
    if "items" in schema:
        check_schema(schema["items"])
    if "anyOf" in schema:
        if not isinstance(schema["anyOf"], list) or not schema["anyOf"]:
            raise ValueError("anyOf requires a nonempty list of schemas")
        for child in schema["anyOf"]:
            check_schema(child)


def validate(value, schema, path="$"):
    errors = []
    if "anyOf" in schema and not any(not validate(value, child, path) for child in schema["anyOf"]):
        errors.append({"path": path, "error": "anyOf"})
    types = schema.get("type", [])
    types = [types] if isinstance(types, str) else types
    matches = {"null": value is None, "boolean": type(value) is bool,
               "object": type(value) is dict, "array": type(value) is list,
               "string": type(value) is str, "integer": type(value) is int or isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value(),
               "number": type(value) is int or type(value) is float and math.isfinite(value) or isinstance(value, Decimal) and value.is_finite()}
    if types and not any(matches.get(t, False) for t in types):
        return [{"path": path, "error": "type", "expected": types}]
    if "enum" in schema and value not in schema["enum"] or "const" in schema and value != schema["const"]:
        errors.append({"path": path, "error": "enum/const"})
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append({"path": path + "." + key, "error": "missing"})
        props = schema.get("properties", {})
        for key, item in value.items():
            if key in props:
                errors.extend(validate(item, props[key], path + "." + key))
            elif schema.get("additionalProperties") is False:
                errors.append({"path": path + "." + key, "error": "extra"})
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", math.inf):
            errors.append({"path": path, "error": "array_length"})
        if schema.get("uniqueItems") and len({digest(x) for x in value}) != len(value):
            errors.append({"path": path, "error": "duplicate"})
        for i, item in enumerate(value):
            errors.extend(validate(item, schema.get("items", {}), f"{path}[{i}]"))
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", math.inf):
            errors.append({"path": path, "error": "string_length"})
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append({"path": path, "error": "pattern"})
    elif type(value) in (int, float, Decimal):
        if value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf):
            errors.append({"path": path, "error": "numeric_bound"})
    return errors


def references(database, dictionary):
    errors, ids = [], {}
    for table, spec in dictionary.items():
        key = spec.get("identifier")
        values = [r.get(key) for r in database.get(table, []) if isinstance(r, dict)] if key else []
        ids[table] = set(v for v in values if isinstance(v, str))
        if key and len(values) != len(ids[table]):
            errors.append({"table": table, "error": "duplicate_or_missing_identifier"})
    for table, spec in dictionary.items():
        for i, row in enumerate(database.get(table, [])):
            if not isinstance(row, dict):
                continue
            for key, target in spec.get("references", {}).items():
                values = row.get(key)
                values = values if isinstance(values, list) else [values]
                if any(not isinstance(v, str) or v not in ids[target] for v in values):
                    errors.append({"table": table, "row": i, "field": key, "error": "unresolved_reference"})
    return errors
