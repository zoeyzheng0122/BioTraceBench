"""Execution coverage and common-case sets, independent of scientific scores."""
import argparse
from collections import Counter
from pathlib import Path
from model_conversation.archive import Stop, read, write, digest, seal


def compare(runs):
    manifests = {name: read(Path(folder) / "manifest.json") for name, folder in runs.items()}
    statuses = {name: read(Path(folder) / "status.json")["tasks"] for name, folder in runs.items()}
    policies = {digest({k: m.get(k) for k in ("prompt_hashes", "stages", "pdf_policy", "submission_protocol", "initial_review_policy")}) for m in manifests.values()}
    if len(policies) > 1:
        raise Stop("blocked_identity", "Execution prompts or condition policies differ across models")
    stages = ("i0", "gsr", "ssr")
    identities, summaries, completed = {}, {}, {}
    for name, manifest in manifests.items():
        tasks = {t["case_id"]: t for t in manifest["tasks"]}
        identities[name] = {case: t.get("evidence_identity", t.get("effective_input_identity")) for case, t in tasks.items()}
        if any(value is None for value in identities[name].values()):
            raise Stop("blocked_identity", "Coverage comparison requires frozen evidence identities")
        completed[name] = {s: {c for c in tasks if statuses[name].get(c, {}).get(s) == "completed"} for s in stages}
        summaries[name] = {s: {"planned": len(tasks), "completed": len(completed[name][s]),
                              "completion_rate": len(completed[name][s]) / len(tasks) if tasks else None,
                              "statuses": dict(Counter(statuses[name].get(c, {}).get(s, "not_started") for c in tasks))} for s in stages}
    common_planned = set.intersection(*(set(v) for v in identities.values())) if identities else set()
    mismatched = [c for c in sorted(common_planned) if len({v[c] for v in identities.values()}) != 1]
    if mismatched:
        raise Stop("blocked_identity", "Different evidence across models: " + ", ".join(mismatched))
    return {"protocol": "biotracebench-comparison-coverage-1", "models": summaries,
            "common_planned_cases": sorted(common_planned),
            "common_completed_cases": {s: sorted(set.intersection(*(v[s] for v in completed.values()))) if completed else [] for s in stages},
            "meaning": "Report coverage for all planned cases; compare scientific metrics on the listed common completed cases. No missing condition is assigned a fabricated score."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="append", required=True, help="NAME=RUN_DIRECTORY")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(); pairs = [s.split("=", 1) for s in args.run]
    if any(len(p) != 2 for p in pairs) or len(dict(pairs)) != len(pairs):
        raise ValueError("Use unique NAME=RUN_DIRECTORY values")
    output = Path(args.out); output.mkdir(parents=True, exist_ok=False)
    result = compare(dict(pairs)); write(output / "coverage.json", result); seal(output)


if __name__ == "__main__":
    main()
