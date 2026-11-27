"""Scoring-only identity alignment. Never select rows by attribute accuracy."""
import re

from .scoring_items import field_role, safe

TABLES = {"sample", "condition", "assay_run", "population", "measure", "result", "population_relation"}
OUTCOME_FIELDS = {"population_size", "result_value", "factor_value", "supplementary_statistics"}
WEAK_FIELDS = {"time", "assessment_time", "population_time_frame", "assay_type", "platform", "method",
               "species", "biological_model", "statistic_type", "statistical_method", "result_unit", "factor_unit"}
ACCESSION = re.compile(r"[^\s:;]+:[^\s;]+ \(([^()\s]+)\)")


def identity_value(item):
    if not item or not item["exists"] or item["state"] != "reported" or item["unknown_field"]:
        return False
    kind, value = item["value"]
    if kind == "text":
        return bool(value.strip()) and value.strip().upper() not in {"NR", "NE", "NA", "N/A", "UNKNOWN"}
    if kind == "references":
        return bool(value) and all(isinstance(v, str) for v in value)
    # Counts, result numbers, booleans, empty lists and unresolved references
    # cannot become identity evidence merely because a policy names the field.
    return False


def validate_identity(table, spec, policy):
    known = {field["key"] for field in spec["fields"]}
    groups = policy.get("identity_groups", {}).get(table, [])
    guards = policy.get("identity_guards", {}).get(table, [])
    accessions = policy.get("identity_accessions", {}).get(table, {})
    if not isinstance(groups, list) or any(not isinstance(g, list) or not g for g in groups):
        raise ValueError("Identity groups must be nonempty field combinations: " + table)
    if not isinstance(guards, list) or not isinstance(accessions, dict):
        raise ValueError("Invalid identity guards/accessions: " + table)
    for key in [k for group in groups for k in group] + guards + list(accessions):
        if (key not in known or field_role(table, key, spec, policy) != "scientific"
                or key in OUTCOME_FIELDS):
            raise ValueError("Identity rules require scientific identity fields, never primary IDs or outcome values: " + table)
    for group in groups:
        if set(group) <= WEAK_FIELDS and not (policy.get("identity_contract") == "biotracebench-identity-2"
                and set(group) & set(policy.get("identity_native_labels", {}).get(table, {}))):
            raise ValueError("Time, technique or other weak attributes alone cannot establish identity: " + table)
    for key, levels in accessions.items():
        if not isinstance(levels, list) or not levels or set(levels) - {"sample", "run", "library", "experiment"}:
            raise ValueError("Identity accessions require explicit object-level types: " + table + "." + key)
    return groups, guards, accessions


def _accession_ok(row, key, levels):
    raw = row["raw"].get(key)
    if not isinstance(raw, str) or not raw.strip():
        return False
    tokens = [ACCESSION.fullmatch(token) for token in raw.split("; ")]
    return bool(tokens) and all(token and token[1] in levels for token in tokens)


def align(table, p, g, spec, policy, decisions):
    contract = policy.get("identity_contract", "biotracebench-identity-1")
    if contract == "biotracebench-identity-2":
        from .identity_alignment import align_identity
        return align_identity(table, p, g, spec, policy, decisions)
    if contract != "biotracebench-identity-1":
        raise ValueError("Unknown identity contract")
    groups, guards, accessions = validate_identity(table, spec, policy)
    matched, handled, occupied, audit, queue = [], set(), set(), [], []
    pids, gids = {row["id"]: i for i, row in enumerate(p)}, {row["id"]: j for j, row in enumerate(g)}
    for decision in decisions.get("matches", {}).get(table, []):
        if not isinstance(decision, dict) or not isinstance(decision.get("basis"), str) or not decision["basis"].strip():
            raise ValueError("Identity adjudication requires an explicit written basis")
        i = pids.get(decision.get("prediction"))
        j = gids.get(decision.get("reference")) if decision.get("reference") is not None else None
        if i is None or i in handled or "reference" not in decision or decision["reference"] is not None and (j is None or j in occupied):
            raise ValueError("Identity adjudication must bind valid rows one-to-one")
        handled.add(i)
        if j is not None:
            matched.append((i, j))
            occupied.add(j)
        audit.append({"prediction": i, "reference": j, "status": "human_match" if j is not None else "human_nonmatch",
                      "basis": decision["basis"]})
    candidates, evidence = {}, {}
    for i, left in enumerate(p):
        if i in handled:
            continue
        candidates[i], evidence[i] = [], []
        for j, right in enumerate(g):
            if j in occupied:
                continue
            a, b = left["items"], right["items"]
            supported = [group for group in groups if all(
                identity_value(a.get(key)) and identity_value(b.get(key)) and a[key]["value"] == b[key]["value"]
                and (key not in accessions or _accession_ok(left, key, accessions[key]) and _accession_ok(right, key, accessions[key]))
                for key in group)]
            # A matching fallback description cannot override a contradictory
            # object-level identifier or another explicitly declared discriminator.
            conflicts = [key for key in guards if identity_value(a.get(key)) and identity_value(b.get(key))
                         and a[key]["value"] != b[key]["value"]]
            conflicts += [key for key, levels in accessions.items() if _accession_ok(left, key, levels)
                          and _accession_ok(right, key, levels) and a[key]["value"] != b[key]["value"] and key not in conflicts]
            if supported and not conflicts:
                candidates[i].append(j)
            evidence[i].append({"reference": right["id"], "row_index": j,
                                "matched_groups": supported, "conflicting_fields": conflicts})
    for i, options in candidates.items():
        if len(options) == 1 and sum(options[0] in other for other in candidates.values()) == 1:
            j = options[0]
            matched.append((i, j))
            audit.append({"prediction": i, "reference": j, "status": "unique_identity_match",
                          "evidence": next(v for v in evidence[i] if v["row_index"] == j)})
        else:
            reason = "no_reference_records" if not g else "no_identity_policy" if not groups else "ambiguous_or_unmatched_identity"
            audit.append({"prediction": i, "reference": None, "status": reason, "evidence": evidence[i]})
            if g:
                queue.append({"id": p[i]["id"], "kind": "record_identity", "table": table,
                              "prediction": p[i]["id"], "submitted": safe(p[i]["raw"]), "reason": reason,
                              "identity_evidence": evidence[i],
                              "candidates": [{"reference": row["id"], "content": safe(row["raw"])} for row in g]})
    return sorted(matched), queue, audit
