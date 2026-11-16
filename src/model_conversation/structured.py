"""Conservative local schema checks; not a substitute for provider acceptance."""
import copy
import re

KEYWORDS = {"$schema", "$id", "title", "description", "type", "properties", "required",
            "additionalProperties", "items", "minItems", "maxItems", "minLength",
            "maxLength", "enum", "minimum", "maximum", "anyOf", "pattern", "uniqueItems", "const", "examples", "default"}
TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}


def check_schema(schema):
    if not isinstance(schema, dict) or set(schema) - KEYWORDS:
        raise ValueError("Unsupported native output schema; no constraint is silently dropped")
    if "pattern" in schema:
        if not isinstance(schema["pattern"], str):
            raise ValueError("Schema pattern must be a string")
        re.compile(schema["pattern"])
    if "uniqueItems" in schema and type(schema["uniqueItems"]) is not bool:
        raise ValueError("Schema uniqueItems must be boolean")
    if "anyOf" in schema:
        if set(schema) != {"anyOf"} or not isinstance(schema["anyOf"], list) or not schema["anyOf"]:
            raise ValueError("Native anyOf schemas require a nonempty list of complete alternatives")
        for child in schema["anyOf"]:
            check_schema(child)
        return
    types = schema.get("type")
    types = [types] if isinstance(types, str) else types
    if not isinstance(types, list) or not types or any(t not in TYPES for t in types):
        raise ValueError("Explicit schema types are required")
    if "object" in types:
        props = schema.get("properties")
        required = schema.get("required")
        if (not isinstance(props, dict) or not isinstance(required, list)
                or len(required) != len(set(required)) or set(required) != set(props)
                or schema.get("additionalProperties") is not False):
            raise ValueError("Native object schemas require explicit closed properties and required fields")
        for child in props.values():
            check_schema(child)
    if "array" in types:
        check_schema(schema.get("items"))


def format_schema(value):
    if (not isinstance(value, dict) or set(value) != {"name", "schema"}
            or not isinstance(value["name"], str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value["name"])):
        raise ValueError("Output schema requires a stable name and schema")
    check_schema(value["schema"])
    if value["schema"].get("type") != "object":
        raise ValueError("Final output schema must describe an object")
    return {"type": "json_schema", "json_schema": {"name": value["name"],
            "strict": True, "schema": copy.deepcopy(value["schema"])}}
