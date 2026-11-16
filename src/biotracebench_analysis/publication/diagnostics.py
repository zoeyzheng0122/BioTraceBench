"""Aggregate externally reviewed diagnostic labels without changing judgments."""
from collections import Counter, defaultdict
from pathlib import Path
import argparse
from .io import Artifact, read, write, rows, csvwrite, digest
from .statistics import METRICS

SUBTYPES = ("object_identity", "relationship_role", "relation_context_omission")
TAGS = ("analysis_population", "object_granularity", "temporal_context",
        "comparison_roles", "multi_source")
ANNOTATIONS = "03_Experiments/reviewed_diagnostics"

def checked_inputs(artifact, manifest):
    for item in manifest["inputs"]:
        p = (artifact.root / item["path"]).resolve()
        if not p.is_relative_to(artifact.root) or not p.is_file() or digest(p) != item["sha256"]:
            raise ValueError("Diagnostic annotation input identity differs: " + item["path"])

def binding_summary(events, structural, evaluable):
    """Each event has one primary type; answer prevalence permits overlap."""
    event_ids = set()
    answer_types = defaultdict(set)
    event_counts = Counter()
    eligible = set(evaluable)
    for event in events:
        eid = event["event_id"]
        key = event["model"], event["case"]
        if eid in event_ids or event["subtype"] not in SUBTYPES or key not in eligible:
            raise ValueError("Invalid, repeated or ineligible diagnostic event")
        if not event.get("basis") or not event.get("evidence") or event.get("status") != "resolved":
            raise ValueError("Diagnostic event has incomplete review evidence")
        event_ids.add(eid)
        answer_types[key].add(event["subtype"])
        event_counts[event["subtype"]] += 1
    passed = {key for key, value in structural.items() if value == "pass"}
    if not passed <= eligible:
        raise ValueError("Structural cohort includes an ineligible answer")
    result = {}
    cohorts = [("evaluable", eligible), ("structure_pass", passed)]
    cohorts += [(prefix + "_" + domain, {k for k in cohort if k[1].startswith(letter)})
                for prefix, cohort in (("evaluable", eligible), ("structure_pass", passed))
                for domain, letter in (("basic", "B"), ("clinical", "C"))]
    for name, cohort in cohorts:
        hits = {k: v for k, v in answer_types.items() if k in cohort}
        intersections = Counter("+".join(q for q in SUBTYPES if q in v) for v in hits.values())
        result[name] = {"answers": len(cohort), "binding_answers": len(hits),
                        "subtypes": {q: sum(q in v for v in hits.values()) for q in SUBTYPES},
                        "exact_intersections": dict(sorted(intersections.items())),
                        "distinct_tasks": len({c for m, c in hits})}
        if sum(intersections.values()) != len(hits):
            raise ValueError("Diagnostic intersection union differs")
    result["event_counts"] = dict(event_counts)
    return result

def task_groups(annotations, scores):
    """Describe existing scores in overlapping, source-defined task subsets."""
    cases = {r["case"]: r for r in annotations}
    if len(cases) != len(annotations) or set(cases) != {r["case"] for r in scores}:
        raise ValueError("Task annotation coverage differs from the score suite")
    models = sorted({r["model"] for r in scores})
    if len({(r["model"], r["case"]) for r in scores}) != len(scores) or len(scores) != len(cases) * len(models):
        raise ValueError("Model/task score coverage is incomplete")
    for case, a in cases.items():
        if set(a["tags"]) - set(TAGS) or len(a["tags"]) != len(set(a["tags"])) or not a.get("basis") or not a.get("evidence"):
            raise ValueError("Invalid capability labels or missing evidence")
        if a["domain"] not in {"basic", "clinical"}:
            raise ValueError("Invalid task domain")
    coverage, summaries = [], []
    for tag in TAGS:
        selected = {c for c, a in cases.items() if tag in a["tags"]}
        coverage.append({"tag": tag, "studies": len(selected),
                         **{d: sum(cases[c]["domain"] == d for c in selected) for d in ("basic", "clinical")}})
        for model in models:
            rr = [r for r in scores if r["model"] == model and r["case"] in selected]
            for domain in ("basic", "clinical", "overall"):
                group = [r for r in rr if domain == "overall" or r["domain"] == domain]
                result = {"tag": tag, "model": model, "domain": domain, "studies": len(group),
                          "assigned_zeros": sum(r["zero_output"] in (True, "True") for r in group)}
                for metric in METRICS:
                    means, n = [], 0
                    for d in ("basic", "clinical"):
                        vals = [float(r[metric]) for r in group if r["domain"] == d and r[metric] not in (None, "")]
                        if any(v < 0 or v > 1 for v in vals):
                            raise ValueError("Invalid task-group score")
                        n += len(vals)
                        if vals:
                            means.append(sum(vals) / len(vals))
                    result[metric] = sum(means) / len(means) if means else None
                    result[metric + "_n"] = n
                summaries.append(result)
    return coverage, summaries

def run(artifact, out):
    base = artifact.repro / ANNOTATIONS
    manifest = read(base / "annotation_manifest.json")
    checked_inputs(artifact, manifest)
    events = read(base / "binding_subtypes.json")
    annotations = read(base / "task_capabilities.json")
    scores = rows(artifact.published / "projection/scores.csv")
    original = read(artifact.published / "diagnostic-events.json")
    original = [e for e in original if e["category"] == "binding"]
    if {(e["event_id"], tuple(e["item_ids"])) for e in events} != {(e["event_id"], tuple(e["item_ids"])) for e in original}:
        raise ValueError("Subtype labels differ from the frozen binding events")
    structure = rows(artifact.baseline / "structure/output_results.csv")
    structural = {(r["model"], r["case"]): r["structural_status"] for r in structure}
    evaluable = {(r["model"], r["case"]) for r in scores if r["zero_output"] == "False"}
    result = binding_summary(events, structural, evaluable)
    if result["evaluable"]["binding_answers"] != manifest["expected"]["binding_answers"] or result["structure_pass"]["binding_answers"] != manifest["expected"]["structure_pass_binding_answers"]:
        raise ValueError("Frozen diagnostic answer union differs")
    for a in annotations:
        for item in a["evidence"]:
            p = artifact.root / item["path"]
            if digest(p) != item["sha256"]:
                raise ValueError("Capability evidence identity differs")
    coverage, grouped = task_groups(annotations, scores)
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Diagnostic output directory must be empty")
    out.mkdir(parents=True, exist_ok=True)
    write(out / "binding_summary.json", result)
    names = {"object_identity": "Object identity or granularity",
             "relationship_role": "Relationship or role discrepancy",
             "relation_context_omission": "Relation or context omission"}
    passed = result["structure_pass"]
    csvwrite(out / "binding_subtypes_table.csv", [
        {"subtype": names[q], "answers": passed["subtypes"][q],
         "denominator": passed["answers"], "percentage": 100 * passed["subtypes"][q] / passed["answers"]}
        for q in SUBTYPES])
    csvwrite(out / "task_coverage.csv", coverage)
    csvwrite(out / "task_group_scores.csv", grouped)
    write(out / "provenance.json", {"annotation_manifest_sha256": digest(base / "annotation_manifest.json"),
                                   "score_sha256": digest(artifact.published / "projection/scores.csv"),
                                   "weighting": "Equal studies within each represented domain; equal represented domains. Undefined scores omitted with metric-specific n; assigned zeros retained.",
                                   "interpretation": "Overlapping task subsets; descriptive results, not causal capability comparisons."})
    return result, coverage

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--artifact-root", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    result, coverage = run(Artifact(a.artifact_root), a.out)
    print({"binding": result, "task_coverage": coverage})

if __name__ == "__main__":
    main()
