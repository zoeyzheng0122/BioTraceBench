"""Independent scorer. Never imported by generation or material tools.

Exact, dictionary-frozen comparisons are provisional whenever identity or text
equivalence needs a human decision. One row assignment serves both metrics.
"""
import copy
import json
import re
from decimal import Decimal, InvalidOperation, MAX_EMAX, MIN_EMIN, localcontext
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from model_conversation.archive import digest, read, write

IDENTITY = {
    "sample": ["sample_name", "biological_source", "biological_model", "sample_material", "sample_accession"],
    "condition": ["sample_id", "condition_target", "experimental_factor", "time"],
    "assay_run": ["sample_ids", "assay_type", "platform", "method", "experiment_run_accession"],
    "population": ["population_name", "population_definition", "intervention", "intervention_regimen", "population_time_frame"],
    "measure": ["measure_name", "measure_definition"],
    "result": ["population_id", "measure_id", "assessment_time", "statistic_type", "statistical_method", "comparison"],
    "population_relation": ["population_a_id", "population_b_id", "relationship"],
}
MISSING = ("model_unanswered",)


def _decimal_text(value):
    """Remove insignificant zeros without Decimal.normalize's context rounding."""
    number = Decimal(str(value))
    if not number.is_finite():
        return str(number)
    if number.is_zero():
        return "0"
    sign, digits, exponent = number.as_tuple()
    end = len(digits)
    while digits[end - 1] == 0:
        end -= 1
    return str(Decimal((sign, digits[:end], exponent + len(digits) - end)))


def _decimal_product(value, scale):
    """Apply only the caller's declared scale, with sufficient local precision."""
    left, right = Decimal(str(value)), Decimal(str(scale))
    with localcontext() as context:
        context.prec = max(1, len(left.as_tuple().digits) + len(right.as_tuple().digits))
        context.Emax, context.Emin = MAX_EMAX, MIN_EMIN
        return left * right


def canonical(value, rule=None):
    rule = rule or {}
    if value is None:
        return ("source_unreported",)
    if type(value) is bool:
        return ("bool", value)
    if isinstance(value, (int, float, Decimal)):
        return ("number", _decimal_text(value))
    if isinstance(value, str):
        from .scoring_text import normalize_text
        value = normalize_text(value, rule)
        value = rule.get("aliases", {}).get(value, value)
        if rule.get("numeric"):
            try:
                return ("number", _decimal_text(value))
            except InvalidOperation:
                pass
        # NR, NE, ranges, inequalities and conflicts retain their own value.
        return ("text", value)
    if isinstance(value, list):
        return ("list", tuple(sorted((canonical(x) for x in value), key=repr)))
    if isinstance(value, dict):
        return ("object", tuple((k, canonical(v)) for k, v in sorted(value.items())))
    return ("unsupported", repr(value))


def assignment(weights):
    """Rectangular maximum-weight bipartite matching, padded with dummy rows."""
    n = len(weights)
    m = max((len(r) for r in weights), default=0)
    size = max(n, m)
    if not size:
        return []
    a = [[-(weights[i][j] if i < n and j < m else 0) for j in range(size)] for i in range(size)]
    u, v, p, way = [0]*(size+1), [0]*(size+1), [0]*(size+1), [0]*(size+1)
    for i in range(1, size+1):
        p[0], j0 = i, 0
        mins, used = [float("inf")]* (size+1), [False]*(size+1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], float("inf"), 0
            for j in range(1, size+1):
                if not used[j]:
                    cur = a[i0-1][j-1] - u[i0] - v[j]
                    if cur < mins[j]:
                        mins[j], way[j] = cur, j0
                    if mins[j] < delta:
                        delta, j1 = mins[j], j
            for j in range(size+1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    mins[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if not j0:
                break
    return [(p[j]-1, j-1) for j in range(1, size+1) if p[j] <= n and j <= m]


def metrics(tp, predicted, gold):
    """Compute paper metrics from M/P/G directly, without error deductions.

    An incorrect submission is described once as FP. It stays in P, the
    nonempty reference stays in G, and neither increases M; do not turn the
    error description into an extra penalty or a smaller recall denominator.
    """
    precision = tp / predicted if predicted else (1.0 if not gold else 0.0)
    recall = tp / gold if gold else (1.0 if not predicted else 0.0)
    return {"tp": tp, "predicted": predicted, "gold": gold, "precision": precision,
            "recall": recall, "f1": 2*precision*recall/(precision+recall) if precision+recall else 0.0}


def _reference_order(dictionary):
    """Resolve parents before dependants, independently of JSON key order."""
    graph = {}
    for table in sorted(dictionary):
        targets = set(dictionary[table].get("references", {}).values())
        for target in sorted(targets):
            if target not in dictionary:
                raise ValueError(f"Unknown reference target {target!r} in table {table!r}")
            if not dictionary[target].get("identifier"):
                raise ValueError(f"Reference target {target!r} has no identifier (referenced by {table!r})")
        graph[table] = sorted(targets)
    try:
        return tuple(TopologicalSorter(graph).static_order())
    except CycleError as exc:
        # Do not turn an unsupported cyclic identity problem into arbitrary scores.
        raise ValueError("Cyclic table references require explicit joint alignment/adjudication: "
                         + " -> ".join(exc.args[1])) from None


def score(prediction, gold, dictionary, policy, adjudications=None, *, context=None, allow_unfrozen=False):
    if policy.get("version") == "biotracebench-score-2":
        from .scoring import score_v2
        return score_v2(prediction, gold, dictionary, policy, adjudications, canonicalize=canonical,
                        reference_order=_reference_order, metrics=metrics, multiply=_decimal_product, scope=context, allow_unfrozen=allow_unfrozen)
    if policy.get("version") != "biotracebench-score-1" or not policy.get("frozen"):
        raise ValueError("Freeze the scoring dictionary before comparisons")
    decisions = adjudications or {"equivalences": {}, "matches": {}}
    if not isinstance(prediction, dict):
        prediction = {}
    maps, queue, pairs = {}, [], {}
    diagnostics = []
    aligned = []
    # First freeze a single one-to-one assignment for every table. Referencing
    # rows use the already-established assignments of their dependency tables.
    for table in _reference_order(dictionary):
        spec = dictionary[table]
        identifier = spec.get("identifier")
        fields = [f["key"] for f in spec["fields"] if f["key"] != identifier]
        identity_fields = policy.get("identity_fields", {}).get(table, IDENTITY[table])
        predicted = prediction.get(table, [])
        if not isinstance(predicted, list):
            diagnostics.append({"table": table, "error": "not_array"})
            predicted = []
        expected = gold.get(table, [])
        # Invalid rows remain predicted records and contribute false positives.
        predicted = [r if isinstance(r, dict) else {"__invalid_row__": repr(r)} for r in predicted]
        def prepare_row(row, predicted_side):
            result = {k: canonical(v, policy.get("field_rules", {}).get(table+"."+k)) for k, v in row.items() if k != identifier}
            for field in fields:
                rule = policy.get("field_rules", {}).get(table+"."+field, {})
                unit_field = rule.get("unit_field")
                unit = row.get(unit_field) if unit_field else None
                if unit_field and unit in rule.get("unit_scales", {}) and isinstance(row.get(field), (int,float,Decimal)):
                    scaled = _decimal_product(row[field], rule["unit_scales"][unit])
                    result[field] = canonical(scaled)
                    result[unit_field] = canonical(rule["canonical_unit"])
            for key, target in spec.get("references", {}).items():
                if key not in row:
                    continue
                raw = row[key] if isinstance(row[key], list) else [row[key]]
                mapped = [maps.get(target, {}).get(v, "!unmapped:"+str(v)) if predicted_side else v for v in raw]
                result[key] = ("references", tuple(sorted(map(str, mapped))))
            if table == "result" and isinstance(row.get("comparison"), str):
                mapping = maps.get("population", {}) if predicted_side else {}
                text = row["comparison"]
                if mapping:
                    pattern = r"(?<![\w])(?:" + "|".join(re.escape(x) for x in sorted(mapping, key=len, reverse=True)) + r")(?![\w])"
                    text = re.sub(pattern, lambda m: str(mapping[m[0]]), text)
                result["comparison"] = canonical(text, policy.get("field_rules", {}).get("result.comparison"))
            if table == "population_relation" and row.get("relationship") in {"disjoint from", "overlaps with"}:
                a, b = sorted([result.get("population_a_id", MISSING), result.get("population_b_id", MISSING)], key=repr)
                result["population_a_id"], result["population_b_id"] = a, b
            return result
        p = [prepare_row(r, True) for r in predicted]
        g = [prepare_row(r, False) for r in expected]
        # Sort by scientific content, never arbitrary internal IDs or source row order.
        pi = sorted(range(len(p)), key=lambda i: repr(p[i]))
        gi = sorted(range(len(g)), key=lambda i: repr(g[i]))
        weights = []
        for i in pi:
            row_weights = []
            for j in gi:
                anchors = sum(p[i].get(k) == g[j].get(k) and p[i].get(k) not in (None, MISSING, ("source_unreported",), ("text", "")) for k in identity_fields)
                exact = sum(p[i].get(k, MISSING) == g[j].get(k, MISSING) for k in fields)
                manual = (digest(p[i]), digest(g[j])) in [tuple(x) for x in decisions.get("matches", {}).get(table, [])]
                row_weights.append(1000000 if manual else anchors*1000+exact if anchors else 0)
            weights.append(row_weights)
        matched = [(pi[i], gi[j]) for i, j in assignment(weights) if weights[i][j] > 0]
        pairs[table] = [{"prediction": i, "gold": j} for i, j in matched]
        maps[table] = {}
        if identifier:
            frequencies = {}
            for row in predicted:
                if isinstance(row.get(identifier), str):
                    frequencies[row[identifier]] = frequencies.get(row[identifier], 0)+1
            for i, j in matched:
                old = predicted[i].get(identifier)
                identical_duplicates = isinstance(old, str) and len({digest(p[k]) for k,r in enumerate(predicted) if r.get(identifier) == old}) == 1
                if isinstance(old, str) and (frequencies[old] == 1 or identical_duplicates):
                    maps[table][old] = expected[j].get(identifier)
                else:
                    diagnostics.append({"table": table, "error": "ambiguous_identifier", "row": i})
        # Row-identity ambiguity is never silently promoted to a final metric.
        for i, row in enumerate(weights):
            if row and (not max(row) or row.count(max(row)) > 1):
                qid = digest({"table": table, "row": p[pi[i]], "kind": "identity"})
                if decisions.get("equivalences", {}).get(qid) is True:
                    raise ValueError("Identity acceptance requires explicit matches, not a text-equivalence flag")
                if qid not in decisions.get("equivalences", {}):
                    queue.append({"id": qid, "kind": "record_identity", "table": table,
                                  "submitted_fingerprint": digest(p[pi[i]]),
                                  "submitted": repr(p[pi[i]]),
                                  "candidates": [{"fingerprint": digest(row), "content": repr(row)} for row in g]})
        for j in range(len(gi)):
            column = [row[j] for row in weights]
            if column and max(column) and column.count(max(column)) > 1:
                candidates = [p[pi[i]] for i, value in enumerate(column) if value == max(column)]
                if len({digest(x) for x in candidates}) > 1:
                    qid = digest({"table": table, "gold": g[gi[j]], "kind": "assignment_tie"})
                    if qid not in decisions.get("equivalences", {}):
                        queue.append({"id": qid, "kind": "record_identity", "table": table,
                                      "reference": repr(g[gi[j]]), "candidates": [repr(x) for x in candidates]})
        aligned.append((table, identifier, predicted, expected, p, g, matched))

    # Both metrics consume exactly these assignments; neither rematches rows.
    field_tp = field_pred = field_gold = record_tp = record_pred = record_gold = 0
    correctness = {}
    for table, identifier, predicted, expected, p, g, matched in aligned:
        record_pred += len(predicted)
        record_gold += len(expected)
        field_pred += sum(len([k for k in row if k != identifier]) for row in predicted)
        field_gold += sum(len([k for k in row if k != identifier]) for row in expected)
        for row in g:
            for field in row:
                correctness[table+":"+digest(row)+":"+field] = False
        for i, j in matched:
            truths = []
            for field in set(p[i]) | set(g[j]):
                left, right = p[i].get(field, MISSING), g[j].get(field, MISSING)
                qid = digest({"table": table, "prediction": p[i], "gold": g[j], "field": field})
                equal = left == right and left != MISSING
                if qid in decisions.get("equivalences", {}):
                    equal = decisions["equivalences"][qid] is True
                elif not equal and left[0] == right[0] == "text":
                    queue.append({"id": qid, "kind": "text_equivalence", "table": table, "field": field,
                                  "submitted": left[1], "reference": right[1]})
                field_tp += int(equal)
                truths.append(equal)
                correctness[table+":"+digest(g[j])+":"+field] = bool(equal)
            record_tp += int(all(truths) and set(p[i]) == set(g[j]))
    return {"status": "provisional" if queue or diagnostics else "final_under_frozen_dictionary",
            "field": metrics(field_tp, field_pred, field_gold), "record": metrics(record_tp, record_pred, record_gold),
            "pairs": pairs, "adjudication_queue": queue, "diagnostics": diagnostics,
            "gold_field_correctness": correctness, "policy_identity": digest(policy),
            "adjudication_identity": digest(decisions)}
