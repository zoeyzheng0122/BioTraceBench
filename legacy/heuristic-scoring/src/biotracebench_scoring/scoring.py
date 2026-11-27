"""Opt-in scoring projections; no model calls or generation dependencies.

Identity groups are a separate, explicitly frozen scientific policy. No result
value or number of correct attributes breaks an identity tie. Unresolved rows
and items remain visible in provisional counts and in the adjudication queue.
"""
import re

from model_conversation.archive import digest
from .alignment import TABLES, align, validate_identity
from .scoring_items import field_role, project_row, safe
from .scoring_units import rules_for, convert_row, compare_units
from .scoring_precision import prepare_rules, compare_precision
from .scoring_text import validate_rules as validate_text_rules, normalization_audit, compare_text
from .reference_policy import fixed_reference, counted


def _present(item):
    return counted(item)


def _anchor(item):
    return bool(item and item["exists"] and item["state"] == "reported"
                and not item["unknown_field"] and item["value"] not in {("text", ""), ("source_unreported",)})


def score_v2(prediction, gold, dictionary, policy, adjudications, *, canonicalize, reference_order, metrics, multiply, scope=None, allow_unfrozen=False):
    if (not policy.get("frozen") and not allow_unfrozen) or policy.get("item_policy") != "biotracebench-scoring-items-1":
        raise ValueError("Freeze the versioned scoring item policy before comparisons")
    if not isinstance(gold, dict):
        raise ValueError("Reference database must be an object")
    if not isinstance(prediction, dict):
        prediction = {}
    fixed = fixed_reference(policy)
    boundary = 'scoring-boundaries-3' if fixed else 'scoring-boundaries-2'
    from .identity_alignment import scoped_policy, rules as identity_rules
    identity_policy = scoped_policy(policy, scope)
    catalog_rules = {}
    if 'unit_catalog' in policy or 'unit_bindings' in policy:
        from .unit_catalog import compile_unit_rules
        catalog_rules = compile_unit_rules(policy.get('unit_catalog'), policy.get('unit_bindings'), dictionary, policy)
    validate_text_rules(dictionary, policy)
    text_normalization_audit, text_comparison_audit = {}, []
    precision_rules = prepare_rules(policy, dictionary, gold, scope)
    precision_audit = []
    context = digest({"boundary_revision": boundary, "scope": scope, "prediction": safe(prediction), "reference": safe(gold), "dictionary": dictionary, "policy": policy})
    contexts = (adjudications or {}).get("contexts", {})
    if adjudications and set(adjudications) != {"contexts"}:
        raise ValueError("Version 2 adjudications must be bound to scoring contexts")
    decisions = contexts.get(context, {})
    if set(decisions) - {"field_states", "projections", "matches", "equivalences", "unit_equivalences"}:
        raise ValueError("Unknown adjudication category")
    maps, gold_maps, aligned, pairs, audit, queue, diagnostics = {}, {}, [], {}, {}, [], []
    identity_objects = {}
    alignment_audit, unit_audit, unit_comparison_audit = {}, {}, []
    valid_unit_equivalences = set()
    valid_fields, valid_projections, valid_equivalences = set(), set(), set()
    extra_pred_fields = extra_pred_records = 0
    table_names = set(dictionary)
    for declared in list(policy.get("field_roles", {})) + list(policy.get("field_rules", {})) + policy.get("compound_fields", []):
        table, separator, key = declared.partition(".")
        if not separator or table not in table_names | TABLES:
            raise ValueError("Unknown table in scoring policy: " + declared)
        if table not in dictionary:
            continue
        field_role(table, key, dictionary[table], policy)
        if declared in policy.get("compound_fields", []) and key not in {f["key"] for f in dictionary[table]["fields"]}:
            raise ValueError("Compound itemization requires a declared field")
    for category in ("identity_groups", "identity_guards", "identity_accessions", "identity_strong_groups", "identity_native_labels"):
        for name in identity_policy.get(category, {}):
            if name not in table_names | TABLES:
                raise ValueError("Unknown identity-policy table: " + name)
    for name in decisions.get("matches", {}):
        if name not in table_names:
            raise ValueError("Unknown adjudicated table: " + name)
    for side, database in (("prediction", prediction), ("reference", gold)):
        for name in sorted(set(database) - table_names):
            # Do not discard a submitted extra table and award an apparently final score.
            diagnostics.append({"side": side, "table": name, "error": "unknown_table", "raw": safe(database[name])})
            queue.append({"id": digest({"context": context, "side": side, "table": name}),
                          "kind": "content_classification", "side": side, "table": name,
                          "raw": safe(database[name]), "reason": "undeclared_table_not_counted_by_key_count"})

    for table in reference_order(dictionary):
        spec = dictionary[table]
        identifier = spec.get("identifier")
        if policy.get("identity_contract") == "biotracebench-identity-2":
            identity_rules(table, spec, identity_policy)
        else:
            validate_identity(table, spec, identity_policy)
        unit_rules = rules_for(table, spec, policy, catalog_rules.get(table))
        unit_audit[table] = {"prediction": [], "reference": []}
        rows = {}
        text_normalization_audit[table] = {"prediction": [], "reference": []}
        for side, database in (("prediction", prediction), ("reference", gold)):
            submitted = database.get(table, [])
            if not isinstance(submitted, list):
                diagnostics.append({"side": side, "table": table, "error": "not_array", "raw": safe(submitted)})
                submitted = [submitted] if side == "prediction" else []
            rows[side] = []
            for index, raw in enumerate(submitted):
                if not isinstance(raw, dict):
                    diagnostics.append({"side": side, "table": table, "row": index, "error": "not_object"})
                    raw = {"__invalid_row__": safe(raw)}
                row = project_row(raw, side, table, index, spec, policy, context, decisions, canonicalize)
                text_normalization_audit[table][side].extend(normalization_audit(row, table, policy))
                valid_fields.update(item["field_id"] for item in row["items"].values())
                valid_projections.update(row["projection_fields"])
                queue.extend(row["queue"])
                items = row["items"]
                unit_audit[table][side].append({"row_id": row["id"], "row_index": index,
                                               "conversions": convert_row(row, unit_rules, canonicalize, multiply)})
                for key, target in spec.get("references", {}).items():
                    if key not in items or not _anchor(items[key]):
                        continue
                    values = raw[key] if isinstance(raw[key], list) else [raw[key]]
                    mapping = maps.get(target, {}) if side == "prediction" else gold_maps.get(target, {})
                    resolved = []
                    for value in values:
                        mapped = mapping.get(value) if isinstance(value, str) else None
                        if mapped is None:
                            diagnostics.append({"side": side, "table": table, "row": index, "field": key,
                                                "error": "unresolved_reference", "raw": safe(value)})
                            mapped = ("unresolved", side, row["id"], key, repr(value))
                        resolved.append(mapped)
                    items[key]["value"] = ("references", tuple(sorted(resolved, key=repr)))
                if table == "result" and _anchor(items.get("comparison")) and isinstance(raw.get("comparison"), str):
                    mapping = maps.get("population", {}) if side == "prediction" else gold_maps.get("population", {})
                    if mapping:
                        pattern = r"(?<![\w])(?:" + "|".join(re.escape(k) for k in sorted(mapping, key=len, reverse=True)) + r")(?![\w])"
                        text = re.sub(pattern, lambda m: str(mapping[m[0]]), raw["comparison"])
                        items["comparison"]["value"] = canonicalize(text, policy.get("field_rules", {}).get("result.comparison"))
                if table == "population_relation" and raw.get("relationship") in {"disjoint from", "overlaps with"}:
                    keys = ("population_a_id", "population_b_id")
                    if all(_anchor(items.get(k)) for k in keys):
                        values = sorted((items[k]["value"] for k in keys), key=repr)
                        for key, value in zip(keys, values):
                            items[key]["value"] = value
                rows[side].append(row)
        p, g = rows["prediction"], rows["reference"]
        matches, identity_queue, alignment_audit[table] = align(table, p, g, spec, identity_policy, decisions)
        queue.extend(identity_queue)
        pairs[table] = [{"prediction": i, "gold": j} for i, j in matches]
        maps[table], gold_maps[table] = {}, {}
        if identifier:
            def unique_id(row, pool):
                value = row["raw"].get(identifier)
                return isinstance(value, str) and bool(value) and sum(r["raw"].get(identifier) == value for r in pool) == 1
            for j, row in enumerate(g):
                if unique_id(row, g):
                    gold_maps[table][row["raw"][identifier]] = str(j)
                else:
                    diagnostics.append({"side": "reference", "table": table, "row": j, "error": "invalid_or_duplicate_identifier"})
            for i, j in matches:
                if unique_id(p[i], p) and unique_id(g[j], g):
                    maps[table][p[i]["raw"][identifier]] = str(j)
                else:
                    diagnostics.append({"side": "prediction", "table": table, "row": i, "error": "invalid_or_duplicate_identifier"})
            if policy.get("identity_contract") == "biotracebench-identity-2":
                targets = dict(matches)
                for entry in alignment_audit[table]:
                    if entry["status"] == "duplicate_prediction" and entry["duplicate_of"] in targets:
                        targets[entry["prediction"]] = targets[entry["duplicate_of"]]
                for i, j in targets.items():
                    key = p[i]["raw"].get(identifier)
                    if not isinstance(key, str) or not key or not unique_id(g[j], g):
                        continue
                    same_id = [n for n, row in enumerate(p) if row["raw"].get(identifier) == key]
                    if all(targets.get(n) == j for n in same_id):
                        maps[table][key] = str(j)
        aligned.append((table, p, g, matches))
        audit[table] = {side: [{"row_id": row["id"], "row_index": row["index"], "items": safe(row["items"]),
                               "excluded": row["ignored"]} for row in values] for side, values in rows.items()}
        from .alignment import OUTCOME_FIELDS
        identity_keys = set(identity_policy.get("identity_guards", {}).get(table, []))
        for category in ("identity_groups", "identity_strong_groups"):
            identity_keys.update(key for group in identity_policy.get(category, {}).get(table, []) for key in group)
        identity_keys -= OUTCOME_FIELDS
        identity_objects[table] = [{"object": str(j), "fields": {
            key: safe(row["items"][key]["value"]) for key in sorted(identity_keys) if key in row["items"]}}
            for j, row in enumerate(g)]

    field_tp = field_gold = record_tp = record_gold = 0
    field_pred, record_pred = extra_pred_fields, extra_pred_records
    correctness = {}
    for table, p, g, matches in aligned:
        record_pred += len(p)
        record_gold += len(g)
        field_pred += sum(_present(item) for row in p for item in row["items"].values())
        field_gold += sum(_present(item) for row in g for item in row["items"].values())
        for j, row in enumerate(g):
            for key, item in row["items"].items():
                if _present(item):
                    # Reference row index is stable across conditions, not tied to prediction content.
                    correctness[table + ":" + str(j) + ":" + key] = False
        for i, j in matches:
            left, right = p[i]["items"], g[j]["items"]
            truths = []
            unit_overrides, unit_queue, unit_ids, unit_decision_audit = compare_units(p[i], g[j], table, context, decisions)
            unit_comparison_audit.extend(unit_decision_audit)
            queue.extend(unit_queue)
            valid_unit_equivalences.update(unit_ids)
            # Unit context may reject candidate normalization when a required
            # unit is blank. Audit the actual comparison representation too.
            if fixed:
                audit[table]['prediction'][i]['items'] = safe(left)
                audit[table]['reference'][j]['items'] = safe(right)
            for key in sorted(set(left) | set(right)):
                a, b = left.get(key), right.get(key)
                if not _present(a) and not _present(b):
                    continue
                if fixed and (not _present(a) or not _present(b)):
                    # An omission or surplus is decided by fixed-reference
                    # presence, not semantic/unit proposals or missing states.
                    truths.append(False)
                    continue
                equal = bool(_present(a) and _present(b) and not a["unknown_field"] and not b["unknown_field"]
                             and a["state"] == b["state"] and a["state"] in {"reported", "not_reported"}
                             and a["value"] == b["value"])
                if (_present(a) and _present(b) and a["state"] == b["state"]
                        and a["state"] in {"ambiguous", "conflicting"}):
                    qid = digest({"context": context, "prediction": p[i]["id"], "reference": g[j]["id"], "item": key})
                    valid_equivalences.add(qid)
                    decision = decisions.get("equivalences", {}).get(qid)
                    if decision is not None:
                        if type(decision.get("equal")) is not bool or not decision.get("basis"):
                            raise ValueError("State-content decision requires boolean and basis")
                        equal = decision["equal"]
                    else:
                        queue.append({"id": qid, "kind": "state_equivalence", "table": table, "field": key,
                                      "submitted": a["raw"], "reference": b["raw"], "state": a["state"],
                                      "submitted_record": safe(p[i]["raw"]), "reference_record": safe(g[j]["raw"])})
                if key in unit_overrides:
                    equal = unit_overrides[key]
                elif (_present(a) and _present(b) and a["state"] == b["state"] == "reported"
                        and not a["unknown_field"] and not b["unknown_field"]
                        and a["value"][0] == b["value"][0] == "text"):
                    equal, text_queue, text_id, text_log = compare_text(p[i], g[j], table, key, context, decisions, policy)
                    text_comparison_audit.append(text_log)
                    if text_id is not None:
                        valid_equivalences.add(text_id)
                    if text_queue is not None:
                        queue.append(text_queue)
                precision_rule = precision_rules.get((table, j, key))
                if precision_rule is not None:
                    rounded_equal, precision_log = compare_precision(p[i], g[j], table, j, key, precision_rule, unit_overrides)
                    precision_audit.append(precision_log)
                    if rounded_equal is not None:
                        equal = rounded_equal
                field_tp += int(equal)
                truths.append(equal)
                if _present(b):
                    correctness[table + ":" + str(j) + ":" + key] = equal
            record_tp += int(bool(truths) and all(truths))
    for category, allowed in (("field_states", valid_fields), ("projections", valid_projections)):
        if set(decisions.get(category, {})) - allowed:
            raise ValueError("Stale or unknown field adjudication in this scoring context")
    if set(decisions.get("unit_equivalences", {})) - valid_unit_equivalences:
        raise ValueError("Stale or inapplicable unit adjudication in this scoring context")
    if set(decisions.get("equivalences", {})) - valid_equivalences:
        raise ValueError("Stale or inapplicable text adjudication in this scoring context")
    return {"version": "biotracebench-score-2", "boundary_revision": boundary, "context_id": context,
            **({'reference_contract': policy['reference_contract']} if fixed else {}),
            "status": "provisional" if queue or diagnostics or not policy.get("frozen") else "final_under_frozen_dictionary",
            **({"policy_frozen": False, "diagnostic_only": True} if not policy.get("frozen") else {}),
            "field": metrics(field_tp, field_pred, field_gold), "record": metrics(record_tp, record_pred, record_gold),
            "pairs": pairs, "adjudication_queue": [{**q, "context_id": context} for q in queue], "diagnostics": diagnostics,
            "identity_contract": policy.get("identity_contract", "biotracebench-identity-1"),
            "identity_rules_identity": digest({k: v for k, v in identity_policy.items() if k.startswith("identity_")}),
            "identity_objects": identity_objects,
            "scoring_items": audit, "alignment_audit": alignment_audit, "unit_conversion_audit": unit_audit,
            "precision_comparison_audit": precision_audit,
            "text_normalization_audit": text_normalization_audit, "text_comparison_audit": text_comparison_audit,
            "unit_comparison_audit": unit_comparison_audit, "gold_field_correctness": correctness,
            "policy_identity": digest(policy), "adjudication_identity": digest(safe(decisions)),
            **({"unit_catalog_identity": digest(policy['unit_catalog'])} if catalog_rules else {}),
            "adjudications_applied": bool(decisions)}
