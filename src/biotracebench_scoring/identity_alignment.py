"""Identity-only matching with explicit conflicts and conservative duplicate groups."""
import copy
import re
from model_conversation.archive import digest
from .alignment import identity_value, validate_identity, OUTCOME_FIELDS
from .scoring_items import safe
from .native_identity import validate as validate_native, extract as extract_native

CONTRACT = "biotracebench-identity-2"
CATEGORIES = {"identity_groups", "identity_guards", "identity_accessions", "identity_strong_groups", "identity_native_labels"}
ACCESSION = re.compile(r"(?P<database>[A-Za-z][A-Za-z0-9 ._-]*):(?P<id>[^;\s]+) \((?P<level>[a-z]+)\)")


def scoped_policy(policy, scope):
    """Overrides are frozen per task, never selected by model, stage or score."""
    result = copy.deepcopy(policy)
    overrides = policy.get("identity_task_rules", {})
    if not isinstance(overrides, dict):
        raise ValueError("Identity task rules must be a mapping")
    for case, rule in overrides.items():
        if (not re.fullmatch(r"[BC]\d{3}", case) or not isinstance(rule, dict)
                or not isinstance(rule.get("basis"), str) or not rule["basis"].strip()
                or set(rule) - CATEGORIES - {"basis"}):
            raise ValueError("Task identity rules require a case, source basis and identity-only overrides")
    if overrides and not (scope or {}).get("case_id"):
        raise ValueError("Task-scoped identity rules require an explicit case")
    selected = overrides.get((scope or {}).get("case_id"), {})
    for category in CATEGORIES:
        if category in selected:
            if not isinstance(selected[category], dict):
                raise ValueError("Task identity category must be a table mapping")
            result.setdefault(category, {}).update(copy.deepcopy(selected[category]))
    return result


def accession_tokens(row, key, levels):
    raw = row["raw"].get(key)
    if not isinstance(raw, str):
        return None
    parsed = [ACCESSION.fullmatch(part) for part in raw.split("; ")]
    if not parsed or not all(parsed):
        return None
    # High-level project/study IDs are retained in the answer but cannot anchor identity.
    tokens = frozenset((m["database"], m["id"], m["level"]) for m in parsed if m["level"] in levels)
    return tokens or None


def rules(table, spec, policy):
    groups, guards, accessions = validate_identity(table, spec, policy)
    native = policy.get("identity_native_labels", {}).get(table, {})
    known = {field["key"] for field in spec["fields"]}
    if not isinstance(native, dict):
        raise ValueError("Native identity labels must be a field mapping")
    for key, rule in native.items():
        if (key not in known or key == spec.get("identifier") or key in OUTCOME_FIELDS
                or key in spec.get("references", {}) or not isinstance(rule, dict)):
            raise ValueError("Native labels require an existing non-outcome field and a source basis")
        validate_native(rule)
    strong = policy.get("identity_strong_groups", {}).get(table, [])
    if not isinstance(strong, list) or any(not isinstance(g, list) or not g for g in strong):
        raise ValueError("Strong identity groups must be nonempty lists")
    if any(key not in set(accessions) | set(native) for group in strong for key in group):
        raise ValueError("Strong identity requires an object accession or a source-defined native label")
    return groups, guards, accessions, native, strong


def source_basis(decision):
    evidence = decision.get("evidence")
    if (not isinstance(decision.get("basis"), str) or not decision["basis"].strip()
            or not isinstance(evidence, list) or not evidence
            or any(not isinstance(e, dict) or set(e) != {"source", "locator"}
                   or any(not isinstance(v, str) or not v.strip() for v in e.values()) for e in evidence)):
        raise ValueError("Identity adjudication requires a written basis and source/locator evidence")


def align_identity(table, p, g, spec, policy, decisions):
    groups, guards, accessions, native, strong = rules(table, spec, policy)
    native_cache = {}
    def value(row, key):
        if key in accessions:
            return accession_tokens(row, key, accessions[key])
        item = row["items"].get(key)
        if not identity_value(item):
            return None
        if key in native:
            token = row['id'], key
            if token not in native_cache:
                native_cache[token] = extract_native(row['raw'].get(key), native[key])
            return native_cache[token]
        return item["value"]
    identity_keys = sorted(set(guards) | set(accessions) | set(native) | {k for group in groups + strong for k in group})
    def view(row):
        # No outcome values, scientific scores, provider or condition labels.
        return {key: safe(row["items"][key]["value"]) for key in identity_keys if key in row["items"]}
    def signature(row):
        # Full equality is used only to recognize interchangeable duplicate copies,
        # never to choose the prediction most similar to the reference.
        return digest(safe({key: item for key, item in row["raw"].items() if key != spec.get("identifier")}))
    matched, handled, occupied, audit, queue = [], set(), set(), [], []
    pids, gids = {r["id"]: i for i, r in enumerate(p)}, {r["id"]: j for j, r in enumerate(g)}
    for decision in decisions.get("matches", {}).get(table, []):
        if not isinstance(decision, dict):
            raise ValueError("Invalid identity adjudication")
        source_basis(decision)
        i = pids.get(decision.get("prediction"))
        j = gids.get(decision.get("reference")) if decision.get("reference") is not None else None
        if i is None or i in handled or "reference" not in decision or decision["reference"] is not None and (j is None or j in occupied):
            raise ValueError("Identity adjudication must bind valid rows one-to-one")
        handled.add(i)
        if j is not None:
            matched.append((i, j)); occupied.add(j)
        audit.append({"prediction": i, "reference": j, "status": "human_match" if j is not None else "human_nonmatch",
                      "basis": decision["basis"], "evidence": decision["evidence"]})
    candidates, evidence = {}, {}
    for i, left in enumerate(p):
        if i in handled:
            continue
        candidates[i], evidence[i] = [], []
        for j, right in enumerate(g):
            def supports(group):
                return all(value(left, k) is not None and value(left, k) == value(right, k) for k in group)
            anchors = [group for group in strong if supports(group)]
            supported = [group for group in groups if supports(group)]
            anchor_conflicts = [key for key in set(accessions) | set(native)
                                if value(left, key) is not None and value(right, key) is not None
                                and value(left, key) != value(right, key)]
            attribute_conflicts = [key for key in guards if value(left, key) is not None and value(right, key) is not None
                                   and value(left, key) != value(right, key)]
            conflicts = anchor_conflicts + ([] if anchors else attribute_conflicts)
            if (anchors or supported) and not conflicts and j not in occupied:
                candidates[i].append(j)
            evidence[i].append({"reference": right["id"], "row_index": j, "matched_groups": supported,
                                "strong_groups": anchors, "conflicting_fields": sorted(set(conflicts)),
                                "attributes_for_separate_scoring": sorted(set(attribute_conflicts)) if anchors else [],
                                "already_occupied": j in occupied,
                                **({'native_labels': {
                                    'prediction': {k:safe(value(left,k)) for k in native},
                                    'reference': {k:safe(value(right,k)) for k in native}}} if native else {})})
    clusters = {}
    for i in candidates:
        clusters.setdefault(signature(p[i]), []).append(i)
    for members in clusters.values():
        i = min(members, key=lambda n: (str(p[n]["raw"].get(spec.get("identifier"), "")), n))
        options = candidates[i]
        contenders = [k for k, opts in candidates.items() if options and options[0] in opts]
        if len(options) == 1 and set(contenders) == set(members):
            j = options[0]
            matched.append((i, j)); occupied.add(j)
            audit.append({"prediction": i, "reference": j, "status": "unique_identity_match",
                          "evidence": next(v for v in evidence[i] if v["row_index"] == j)})
            for duplicate in members:
                if duplicate != i:
                    audit.append({"prediction": duplicate, "reference": None, "status": "duplicate_prediction",
                                  "duplicate_of": i, "basis": "Exact non-identifier duplicate; retained in prediction counts"})
            continue
        for member in members:
            # An identical copy of an explicitly adjudicated match is a surplus copy.
            duplicates = [(a, b) for a, b in matched if a in handled and signature(p[a]) == signature(p[member])]
            if len(duplicates) == 1:
                audit.append({"prediction": member, "reference": None, "status": "duplicate_prediction",
                              "duplicate_of": duplicates[0][0], "basis": "Exact duplicate of adjudicated prediction; retained"})
                continue
            reason = "no_reference_records" if not g else "ambiguous_or_unmatched_identity"
            audit.append({"prediction": member, "reference": None, "status": reason, "evidence": evidence[member]})
            if g:
                queue.append({"id": p[member]["id"], "kind": "record_identity", "table": table,
                              "prediction": p[member]["id"], "submitted": view(p[member]), "reason": reason,
                              "identity_evidence": evidence[member],
                              "candidates": [{"reference": row["id"], "content": view(row)} for row in g]})
    for j, row in enumerate(g):
        if j not in occupied:
            audit.append({"prediction": None, "reference": j, "status": "unmatched_reference"})
    return sorted(matched), queue, audit
