"""Evidence and applicability checks for new scientific reviews; no inferred facts."""
from collections import defaultdict
from biotracebench_scoring.identity_alignment import source_basis
from biotracebench_scoring.alignment import validate_identity, OUTCOME_FIELDS, WEAK_FIELDS
from biotracebench_scoring.scoring_items import STATES
from .io import read, digest

ANNOTATIONS = "03_Benchmark_Data/01_Task_Materials/metadata/evaluation_annotations.json"

def eligibility(inv, records, case, dispositions):
    """Project frozen exclusions through resolved pairs, never an uncertain identity."""
    rows = {r["id"]: r for r in inv["rows"]}
    masks = {(d["table"], d["row_index"]): set(d["field_exclusions"])
             for d in dispositions if d["case"] == case and d["main_record_scoring"] == "excluded"}
    pairs = {r["prediction_row"]: r["reference_row"] for r in records
             if r["verdict"] == "matched"}
    def target(row):
        return rows.get(pairs.get(row["id"])) if row["side"] == "prediction" else row
    excluded_rows = {r["id"] for r in rows.values()
                     if (g := target(r)) and (g["table"], g["row_index"]) in masks}
    excluded_cells = set()
    for cell in inv["cells"]:
        g = target(rows[cell["row"]])
        fields = masks.get((g["table"], g["row_index"]), set()) if g else set()
        if "*" in fields or cell["field"] in fields:
            excluded_cells.add(cell["id"])
    return excluded_rows, excluded_cells

def source_registry(artifact, case, manifest):
    domain = "basic" if case.startswith("B") else "clinical"
    base = artifact.materials / "materials" / domain / case
    result = {}
    for item in manifest["files"]:
        name = item["path"]
        p = (base / name).resolve()
        if not p.is_relative_to(base.resolve()) or not p.is_file() or digest(p) != item["sha256"]:
            raise ValueError("Declared source identity differs: " + name)
        if name in result:
            raise ValueError("Duplicate declared source: " + name)
        result[name] = item["sha256"]
    return result

def field_states(artifact, case, inv, reference_sha256, dispositions):
    """Preserve source states separately from fixed-reference item presence."""
    path = artifact.root / ANNOTATIONS
    data = read(path) if path.exists() else {"cases": {}}
    entry = data["cases"].get(case, {})
    if entry and entry.get("reference_sha256") != reference_sha256:
        raise ValueError("Field-state annotations use a different reference")
    domain = "basic" if case.startswith("B") else "clinical"
    manifest = read(artifact.materials / "metadata/manifests" / domain / (case + ".json"))
    sources = {item["path"] for item in manifest["files"]}
    excluded = {(d["table"], d["row_index"]): set(d["field_exclusions"])
                for d in dispositions if d["case"] == case and d["main_record_scoring"] == "excluded"}
    supplied = {}
    for state in entry.get("fields", []):
        key = state["table"], state["row_index"], state["field"]
        if key in supplied or state["state"] not in STATES:
            raise ValueError("Invalid or duplicate field-state annotation")
        source_basis(state)
        for proof in state["evidence"]:
            if proof["source"] not in sources | {"reference", "task", "eligibility"}:
                raise ValueError("Field-state evidence source is not declared")
            if proof["source"] == "eligibility":
                mask = excluded.get(key[:2], set())
                if (key[2] not in mask and "*" not in mask
                        or proof["locator"] != f"{case}/{key[0]}/{key[1]}/{key[2]}"):
                    raise ValueError("Field-state eligibility evidence does not match its exclusion")
        supplied[key] = state
    result = []
    known = set()
    for cell in inv["cells"]:
        if cell["side"] != "reference":
            continue
        key = cell["table"], cell["row_index"], cell["field"]
        known.add(key)
        annotation = supplied.get(key)
        if annotation and annotation["state"] == "reported" and not cell["nonempty"]:
            raise ValueError("Empty reference content cannot become a reported scoring item")
        result.append({"reference_cell": cell["id"], "value_present": cell["present"],
                       "nonempty": cell["nonempty"],
                       "state": annotation["state"] if annotation else
                                "reported_content" if cell["nonempty"] else "unspecified_null",
                       "basis": annotation["basis"] if annotation else
                                "Frozen reference content; source state is not inferred from a blank value.",
                       "evidence": annotation["evidence"] if annotation else
                                   [{"source": "reference", "locator": cell["id"]}]})
    if set(supplied) - known:
        raise ValueError("Field-state annotation points outside the fixed reference")
    return result, digest(path) if path.exists() else None

def validate_identity_evidence(packet, reply, dispositions):
    """Validate proof structure and locations; the reviewer decides scientific identity."""
    inv = packet["inventory"]
    rows = {r["id"]: r for r in inv["rows"]}
    cells = {c["id"]: c for c in inv["cells"]}
    records = {(r["prediction_row"], r["reference_row"]): r for r in reply["records"]}
    evidence = reply.get("identity_evidence")
    if not isinstance(evidence, list):
        raise ValueError("New reviews require structured identity_evidence")
    er, ec = eligibility(inv, reply["records"], packet["case"], dispositions)
    scientific = {i for m in reply["cells"] if m["category"] in {"scientific", "uncertain"}
                  for i in (m["prediction_cell"], m["reference_cell"])
                  if i and cells[i]["nonempty"] and i not in ec}
    seen, dependencies = set(), set()
    for table, spec in packet["field_dictionary"].items():
        validate_identity(table, spec, packet["policy"])
    for item in evidence:
        if not isinstance(item, dict) or set(item) != {"prediction_row", "reference_row", "basis", "evidence"}:
            raise ValueError("Invalid structured identity evidence")
        pair = item["prediction_row"], item["reference_row"]
        if pair not in records or pair in seen:
            raise ValueError("Identity evidence must cover declared row pairs exactly once")
        seen.add(pair)
        source_basis(item)
        supports = defaultdict(list)
        external = False
        active = (any(r and r not in er for r in pair)
                  or any(cells[i]["row"] in pair for i in scientific))
        for proof in item["evidence"]:
            source, locator = proof["source"], proof["locator"]
            if source in {"prediction", "reference"}:
                rid = pair[0 if source == "prediction" else 1]
                if rid and locator == "row:" + str(rid) and records[pair]["verdict"] != "matched":
                    continue
                c = cells.get(locator)
                if not c or c["side"] != source or c["row"] != rid:
                    raise ValueError("Identity evidence cell is outside its declared object")
                spec = packet["field_dictionary"][c["table"]]
                if (not c["nonempty"] or c["field"] == spec.get("identifier")
                        or c["field"] in OUTCOME_FIELDS):
                    raise ValueError("Local IDs, empty cells and outcome values cannot establish identity")
                supports[source].append(c["field"])
                if active:
                    dependencies.add(locator)
            elif source == "eligibility":
                if active or locator not in er or locator not in pair:
                    raise ValueError("Eligibility evidence requires an excluded object")
            elif source == "task" or source in packet["source_identities"]:
                external = True
            else:
                raise ValueError("Identity evidence source is not declared")
        if records[pair]["verdict"] == "matched":
            if not supports["prediction"] or not supports["reference"]:
                if active:
                    raise ValueError("Matched objects require submitted and reference identity evidence")
            for side in ("prediction", "reference"):
                spec = packet["field_dictionary"][rows[pair[0 if side == "prediction" else 1]]["table"]]
                weak = WEAK_FIELDS | set(spec.get("references", {}))
                if supports[side] and set(supports[side]) <= weak and not external:
                    raise ValueError("Weak attributes or local link pointers require task/source identity support")
    if seen != set(records):
        raise ValueError("Identity evidence omitted a record disposition")
    return er, ec, dependencies

def pending_applicable(inv, reply, er, ec, dependencies, states=()):
    """Excluded uncertainty is retained; active identity and proof dependencies block."""
    unresolved, ignored = [], []
    rows = {r["id"]: r for r in inv["rows"]}
    for mark in reply["cells"]:
        if mark["verdict"] != "uncertain" and mark["category"] != "uncertain":
            continue
        ids = {v for k in ("prediction_cell", "reference_cell") if (v := mark[k])}
        (ignored if ids <= ec and not ids & dependencies else unresolved).append({"kind": "field", **mark})
    for mark in reply["records"]:
        if mark["verdict"] != "uncertain":
            continue
        ids = {mark[k] for k in ("prediction_row", "reference_row") if mark[k]}
        # A submitted object with uncertain identity can affect matching and P elsewhere.
        excluded = ids <= er and not mark["prediction_row"]
        (ignored if excluded else unresolved).append({"kind": "identity", **mark})
    for issue in reply["reference_issues"]:
        (ignored if issue["reference_cell"] in ec and issue["reference_cell"] not in dependencies
         else unresolved).append({"kind": "reference_issue", **issue})
    for state in states:
        if state["state"] in {"ambiguous", "conflicting", "unresolved"}:
            (ignored if state["reference_cell"] in ec and state["reference_cell"] not in dependencies
             else unresolved).append({"kind": "source_state", **state})
    return unresolved, ignored
