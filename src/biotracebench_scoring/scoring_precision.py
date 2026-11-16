"""Source-bound decimal-place comparisons, after independent object alignment.

The policy declares continuous quantities; the scorer never infers source
precision from an answer's spelling. Submitted and projected values stay intact.
"""
import decimal

from model_conversation.archive import digest
from .scoring_items import field_role

CONTRACT = "biotracebench-source-precision-1"
MODES = {name: getattr(decimal, name) for name in (
    "ROUND_HALF_EVEN", "ROUND_HALF_UP", "ROUND_HALF_DOWN", "ROUND_DOWN",
    "ROUND_UP", "ROUND_CEILING", "ROUND_FLOOR", "ROUND_05UP")}
TARGETS = {"condition": {"factor_value"}, "result": {
    "result_value", "supplementary_statistics.confidence_interval",
    "supplementary_statistics.standard_deviation", "supplementary_statistics.standard_error"}}
UNIT_FIELDS = {"condition": "factor_unit", "result": "result_unit"}
COUNT_TYPES = {"n", "count", "counts", "number", "frequency", "人数", "例数", "计数", "分母"}


def prepare_rules(policy, dictionary, reference, scope):
    """Select unique reference objects without looking at model answers/values."""
    rules = policy.get("precision_rules", [])
    if not isinstance(rules, list) or rules and policy.get("precision_contract") != CONTRACT:
        raise ValueError("Source precision requires the versioned rule list")
    selected = {}
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("Source precision rule must be an object")
        required = {"study_id", "materials_identity", "table", "field", "selector", "quantity_kind",
                    "source_locator", "basis", "decimal_places", "rounding", "unit"}
        if set(rule) != required:
            raise ValueError("Source precision requires explicit scope, source, selector, unit and rounding")
        for key in ("study_id", "materials_identity", "source_locator", "basis", "unit"):
            if not isinstance(rule[key], str) or not rule[key].strip():
                raise ValueError("Source precision requires a nonempty " + key)
        places = rule["decimal_places"]
        if (type(places) is not int or not 0 <= places <= 1000 or rule["rounding"] not in MODES
                or rule["quantity_kind"] != "continuous"):
            raise ValueError("Only source-declared continuous precision with explicit rounding is supported")
        table, field = rule["table"], rule["field"]
        if table not in TARGETS or field not in TARGETS[table]:
            raise ValueError("Counts, denominators, identifiers and unsupported items cannot be rounded")
        # A collection can hold other studies' rules, but missing scope never
        # silently disables a supplied source-precision policy.
        if not isinstance(scope, dict) or not scope.get("study_id") or "materials" not in scope:
            raise ValueError("Source precision requires study and frozen materials context")
        if rule["study_id"] != scope["study_id"]:
            continue
        if rule["materials_identity"] != digest(scope["materials"]):
            raise ValueError("Source precision materials identity is stale")
        if table not in dictionary:
            raise ValueError("Source precision target table is absent")
        spec = dictionary[table]
        known = {f["key"]: f for f in spec["fields"]}
        parent = field.split(".")[0]
        if (parent not in known or field_role(table, parent, spec, policy) != "scientific"
                or known[parent].get("type") == "integer"):
            raise ValueError("Source precision requires a continuous scientific field")
        if "." in field and table + "." + parent not in policy.get("compound_fields", []):
            raise ValueError("Source precision requires declared compound itemization")
        selector = rule["selector"]
        if not isinstance(selector, dict) or not selector:
            raise ValueError("Source precision requires an unambiguous reference selector")
        for key, value in selector.items():
            if (key not in known or key == spec.get("identifier") or key in spec.get("references", {})
                    or key in {parent, UNIT_FIELDS[table], "result_value", "factor_value", "supplementary_statistics"}
                    or field_role(table, key, spec, policy) != "scientific"
                    or not isinstance(value, str) or not value.strip()):
                raise ValueError("Precision selectors use source descriptions, not IDs or measured values")
        matches = [i for i, row in enumerate(reference.get(table, []))
                   if isinstance(row, dict) and all(row.get(k) == v for k, v in selector.items())]
        if len(matches) != 1:
            raise ValueError("Source precision selector must identify exactly one reference object")
        index = matches[0]
        row = reference[table][index]
        if (str(row.get("statistic_type", "")).strip().casefold() in COUNT_TYPES
                or str(row.get(UNIT_FIELDS[table], "")).strip().casefold() in COUNT_TYPES):
            raise ValueError("Counts remain exact even when supplied with a rounding rule")
        key = (table, index, field)
        if key in selected:
            raise ValueError("Overlapping source precision rules")
        selected[key] = rule
    return selected


def _rounded(value, rule):
    if value[0] == "number":
        number = decimal.Decimal(value[1])
        if not number.is_finite():
            return None
        places = rule["decimal_places"]
        quantum = decimal.Decimal((0, (1,), -places))
        # Construct a fresh context: caller precision, rounding and traps must
        # not affect an explicit source rule, including very large integers.
        with decimal.localcontext(decimal.Context(
                prec=max(1, len(number.as_tuple().digits), number.adjusted() + places + 2),
                Emax=decimal.MAX_EMAX, Emin=decimal.MIN_EMIN)):
            rounded = number.quantize(quantum, rounding=MODES[rule["rounding"]])
        return ("number", str(rounded.copy_abs() if rounded.is_zero() else rounded))
    if value[0] == "object":
        bounds = dict(value[1])
        if set(bounds) == {"lower", "upper"} and all(v[0] == "number" for v in bounds.values()):
            values = [(k, _rounded(v, rule)) for k, v in sorted(bounds.items())]
            if all(v is not None for _, v in values):
                return ("object", tuple(values))
    return None


def compare_precision(left, right, table, index, field, rule, unit_overrides):
    log = {"table": table, "reference_index": index, "field": field,
           "prediction_row": left["id"], "reference_row": right["id"],
           "rule_identity": digest(rule), "rule": rule}
    a, b = left["items"].get(field), right["items"].get(field)
    if not all(item and item["exists"] and item["state"] == "reported" and not item["unknown_field"] for item in (a, b)):
        return None, {**log, "status": "not_reported_numeric_pair"}
    log.update(submitted_original=a["raw"], reference_original=b["raw"],
               submitted_before=a["value"], reference_before=b["value"])
    if field in unit_overrides:
        return None, {**log, "status": "unit_comparison_takes_precedence"}

    def unit(row):
        for context in row.get("unit_context", {}).values():
            if field in context["converted"]:
                return context["unit"]
        return row["raw"].get(UNIT_FIELDS[table])

    if unit(right) != rule["unit"]:
        raise ValueError("Source precision unit must match the reference item's effective unit")
    if unit(left) != rule["unit"]:
        return False, {**log, "status": "incompatible_units"}
    x, y = _rounded(a["value"], rule), _rounded(b["value"], rule)
    if x is None or y is None:
        return None, {**log, "status": "unsupported_expression_preserved"}
    return x == y, {**log, "status": "source_rounding", "submitted_rounded": x,
                    "reference_rounded": y, "equal": x == y}
