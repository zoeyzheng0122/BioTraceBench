"""Explicit, exact scoring-unit conversions; never edit a submitted answer."""
from decimal import Decimal, InvalidOperation

from model_conversation.archive import digest
from .scoring_items import field_role, safe
from .reference_policy import counted

COMPANIONS = {"confidence_interval", "standard_deviation", "standard_error"}


def rules_for(table, spec, policy, catalog_rules=None):
    known = {field["key"] for field in spec["fields"]}
    rules, seen_units = {}, set()
    for field, rule in policy.get("field_rules", {}).items():
        prefix, _, key = field.partition(".")
        if key in (catalog_rules or {}) and prefix == table:
            continue  # Explicit quantity bindings supersede legacy one-family rules.
        if prefix != table or not any(k in rule for k in ("unit_field", "canonical_unit", "unit_scales")):
            continue
        unit = rule.get("unit_field")
        scales = rule.get("unit_scales")
        canonical = rule.get("canonical_unit")
        if (key not in known or unit not in known or key == unit or unit in seen_units
                or field_role(table, key, spec, policy) != "scientific" or field_role(table, unit, spec, policy) != "scientific"
                or key in spec.get("references", {}) or unit in spec.get("references", {})
                or not isinstance(scales, dict) or not scales or canonical not in scales):
            raise ValueError("Unit rule requires declared value/unit fields and an explicit canonical scale: " + field)
        for name, factor in scales.items():
            if not isinstance(name, str) or not name.strip() or not isinstance(factor, str):
                raise ValueError("Unit names and exact decimal factors must be strings")
            try:
                number = Decimal(factor)
            except InvalidOperation:
                raise ValueError("Invalid exact unit scale") from None
            if not number.is_finite() or number <= 0:
                raise ValueError("Unit scale must be positive and finite")
        if Decimal(scales[canonical]) != 1:
            raise ValueError("Canonical unit must have scale 1")
        companions = rule.get("scale_companion_items", [])
        if not isinstance(companions, list) or len(set(companions)) != len(companions):
            raise ValueError("Unit companion list must be unique")
        for companion in companions:
            parent, separator, name = companion.partition(".")
            if (not separator or name not in COMPANIONS or parent not in known
                    or table + "." + parent not in policy.get("compound_fields", [])):
                raise ValueError("Only declared own CI/SD/SE items may follow a value's unit")
        seen_units.add(unit)
        rules[key] = rule
    rules.update(catalog_rules or {})
    return rules


def _number(item):
    return bool(item and item["exists"] and item["state"] == "reported" and item["value"][0] == "number"
                and Decimal(item["value"][1]).is_finite())


def convert_row(row, rules, canonicalize, multiply):
    logs, units = [], {}
    for key, rule in rules.items():
        unit_key = rule["unit_field"]
        raw_unit = row["raw"].get(unit_key)
        if 'catalog_families' in rule:
            from copy import deepcopy
            rule = deepcopy(rule)
            selected = [(name, f) for name,f in rule['catalog_families'].items()
                        if isinstance(raw_unit, str) and raw_unit in f['scales']]
            name, family = selected[0] if selected else (None, {'canonical': None, 'scales': {}})
            rule.update(canonical_unit=family['canonical'], unit_scales=family['scales'], family=name)
        unit_item, value_item = row["items"].get(unit_key), row["items"].get(key)
        log = {"value_field": key, "unit_field": unit_key, "original_value": safe(row["raw"].get(key)),
               "original_unit": safe(raw_unit), "rule_identity": digest(rule), "converted_items": []}
        units[key] = {"unit": raw_unit, "rule": rule, "converted": set(), "independent": set(),
                      'original_values': {k:item['value'] for k,item in row['items'].items()}}
        if 'catalog_identity' in rule:
            log.update(catalog_identity=rule['catalog_identity'], family=rule['family'])
            from .unit_whole_field import normalize
            for companion in rule['whole_field_companions']:
                item = row['items'].get(companion)
                if not item or not item['exists'] or item['state'] != 'reported':
                    continue
                factor = rule['unit_scales'].get(raw_unit) if isinstance(raw_unit,str) else None
                source_text = item['value'][1] if item['value'][0] == 'text' else item['raw']
                normalized = normalize(source_text, factor, canonicalize, multiply)
                if normalized is not None:
                    text, dimensional = normalized
                    item['value'] = canonicalize(text)
                    units[key]['converted'].add(companion)
                    if not dimensional:
                        units[key]['independent'].add(companion)
                    log['converted_items'].append({'field': companion, 'comparison_unit': 'whole_field',
                                                   'dimension_dependent': dimensional, 'normalized_value': text})
        if (not unit_item or unit_item["state"] != "reported" or not isinstance(raw_unit, str)
                or raw_unit not in rule["unit_scales"]):
            log["status"] = "no_applicable_declared_unit"
            logs.append(log)
            continue
        if not _number(value_item):
            log["status"] = "value_not_a_reported_finite_scalar"
            logs.append(log)
            continue
        factor = rule["unit_scales"][raw_unit]
        scaled = multiply(value_item["value"][1], factor)
        value_item["value"] = canonicalize(scaled)
        unit_item["value"] = canonicalize(rule["canonical_unit"])
        units[key]["unit"] = rule["canonical_unit"]
        units[key]["converted"].update((key, unit_key))
        log.update(status="exact_conversion", scale=factor, canonical_unit=rule["canonical_unit"], normalized_value=str(scaled))
        log["converted_items"].append({"field": key, "normalized_value": str(scaled)})
        for companion in rule.get("scale_companion_items", []):
            item = row["items"].get(companion)
            if not item or item["state"] != "reported" or not item["exists"]:
                continue
            kind = companion.rsplit(".", 1)[1]
            if kind == "confidence_interval" and item["value"][0] == "object":
                bounds = dict(item["value"][1])
                if set(bounds) != {"lower", "upper"} or any(v[0] != "number" for v in bounds.values()):
                    continue
                normalized = {k: multiply(v[1], factor) for k, v in bounds.items()}
            elif _number(item):
                normalized = multiply(item["value"][1], factor)
            else:
                continue
            item["value"] = canonicalize(normalized)
            units[key]["converted"].add(companion)
            log["converted_items"].append({"field": companion, "normalized_value": safe(normalized)})
        logs.append(log)
    row["unit_context"] = units
    return logs


def compare_units(left, right, table, context, decisions):
    """Guard same-number/different-unit matches; human decisions are per item."""
    overrides, queue, valid, audit = {}, [], set(), []
    for key, a in left.get("unit_context", {}).items():
        b = right["unit_context"][key]
        raw_a, raw_b = left["raw"].get(a["rule"]["unit_field"]), right["raw"].get(b["rule"]["unit_field"])
        fields = [key, a["rule"]["unit_field"], *a["rule"].get("scale_companion_items", [])]
        fields += a['rule'].get('whole_field_companions', [])
        fixed = 'count_as_field' in left['items'].get(key, {})
        unit_field = a['rule']['unit_field']
        if fixed and (not counted(left['items'].get(unit_field)) or not counted(right['items'].get(unit_field))):
            # No complete declared unit pair: compare original content without
            # inventing the absent unit or silently applying a one-sided scale.
            for row, meta in ((left,a),(right,b)):
                for field in fields:
                    if field in row['items'] and field in meta['original_values']:
                        row['items'][field]['value'] = meta['original_values'][field]
                meta['unit'] = row['raw'].get(unit_field)
                meta['converted'].clear()
            if counted(left['items'].get(key)) and counted(right['items'].get(key)):
                overrides[key] = left['items'][key]['value'] == right['items'][key]['value']
            for field in a['rule'].get('whole_field_companions', []):
                x,y = left['items'].get(field),right['items'].get(field)
                if counted(x) and counted(y) and x['value'] == y['value']:
                    overrides[field] = True
            audit.append({'table':table,'field':key,'prediction_row':left['id'],
                          'reference_row':right['id'],'status':'unconverted_comparison_missing_unit',
                          'submitted_unit':safe(raw_a),'reference_unit':safe(raw_b)})
            continue
        same_context = True
        if 'catalog_identity' in a['rule']:
            from .unit_catalog import quantity_context
            same_context = raw_a == raw_b or quantity_context(left, right, a['rule'])
        for field in fields:
            x, y = left["items"].get(field), right["items"].get(field)
            if not x or not y or not x["exists"] or not y["exists"]:
                continue
            if fixed and (not counted(x) or not counted(y)):
                continue
            if field == a["rule"]["unit_field"] and raw_a == raw_b:
                # Same submitted unit remains correct even when one value is
                # text/NR and only the other side can be numerically scaled.
                if x["state"] == y["state"] == "reported":
                    overrides[field] = True
                continue
            if (fixed and field == unit_field and 'catalog_identity' in a['rule'] and same_context
                    and a['rule']['family'] is not None and a['rule']['family'] == b['rule']['family']
                    and x['state'] == y['state'] == 'reported'):
                overrides[field] = True
                audit.append({'table':table,'field':field,'prediction_row':left['id'],
                              'reference_row':right['id'],'status':'exact_unit_label_equivalence',
                              'equal':True,'catalog_identity':a['rule']['catalog_identity']})
                continue
            if (field in a['rule'].get('whole_field_companions', [])
                    and raw_a == raw_b):
                continue  # No unit change: preserve ordinary whole-field semantics.
            # Raw equality is sufficient only when both items underwent the
            # same transformation (or neither did). Unsupported companion text
            # must not be treated as converted just because the main value was.
            converted_a, converted_b = field in a["converted"], field in b["converted"]
            independent = field in a.get('independent', set()) and field in b.get('independent', set())
            comparable = (independent or same_context and converted_a and converted_b and a["unit"] == b["unit"]
                          or not converted_a and not converted_b and raw_a == raw_b)
            if comparable:
                if field in a['rule'].get('whole_field_companions', []) and x['value'] == y['value']:
                    overrides[field] = True
                    audit.append({'table': table, 'field': field, 'prediction_row': left['id'],
                                  'reference_row': right['id'], 'status': 'whole_field_exact_unit_equivalence',
                                  'equal': True, 'catalog_identity': a['rule']['catalog_identity']})
                continue
            overrides[field] = False
            qid = digest({"context": context, "prediction": left["id"], "reference": right["id"], "unit_item": field})
            valid.add(qid)
            decision = decisions.get("unit_equivalences", {}).get(qid)
            if decision is not None:
                if (not isinstance(decision, dict) or type(decision.get("equal")) is not bool
                        or not isinstance(decision.get("basis"), str) or not decision["basis"].strip()):
                    raise ValueError("Unit equivalence requires a boolean and an explicit source-based basis")
                if decision["equal"] and (x["state"] != "reported" or y["state"] != "reported"):
                    raise ValueError("Unit adjudication cannot fill or resolve a missing/uncertain value")
                overrides[field] = decision["equal"]
                audit.append({"id": qid, "table": table, "field": field, "prediction_row": left["id"],
                              "reference_row": right["id"], "status": "human_adjudicated",
                              "equal": decision["equal"], "basis": decision["basis"]})
            else:
                queue.append({"id": qid, "kind": "unit_equivalence", "table": table, "field": field,
                              "submitted_value": x["raw"], "submitted_unit": safe(raw_a),
                              "reference_value": y["raw"], "reference_unit": safe(raw_b),
                              "reason": "quantity_context_not_established" if not same_context else "no_common_declared_exact_conversion_for_item"})
                audit.append({"id": qid, "table": table, "field": field, "prediction_row": left["id"],
                              "reference_row": right["id"], "status": "pending_unit_adjudication"})
    return overrides, queue, valid, audit
