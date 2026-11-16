"""Identical submission constraints for I0, GSR and SSR."""
from model_conversation.structured import format_schema
from .conditions import canonical
from .submission import PROTOCOL, schema
POLICIES = {"json_object", "json_schema_strict"}

def output_schema(database_schema, stage, submission_protocol=None):
    stage = canonical(stage)
    value = {"name": "biotracebench_" + stage, "schema": schema(database_schema, submission_protocol or PROTOCOL)}
    format_schema(value)
    return value
