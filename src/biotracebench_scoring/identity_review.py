"""Blinded human identity review; no model calls, score optimization or answer edits."""
from pathlib import Path
from model_conversation.archive import read, write, digest, seal, verify
from .identity_alignment import CONTRACT, source_basis

PROTOCOL = "biotracebench-identity-review-1"


def prepare(scores_path, out):
    scores = read(scores_path)
    packets, routes = [], {}
    for study in scores:
        for stage, score in study["conditions"].items():
            if score.get("identity_contract") != CONTRACT:
                raise ValueError("Human identity packets require identity contract 2")
            for entry in score["adjudication_queue"]:
                if entry["kind"] != "record_identity":
                    continue
                packet_id = digest({"context": score["context_id"], "item": entry["id"]})
                if packet_id in routes:
                    continue  # Identical answers share a context and one review decision.
                candidates = [{"id": digest({"packet": packet_id, "reference": c["reference"]}),
                               "identity": c["content"]} for c in entry["candidates"]]
                packets.append({"id": packet_id, "case_id": study["case_id"], "table": entry["table"],
                                "submitted_identity": entry["submitted"], "candidates": candidates,
                                "objects": score.get("identity_objects", {}),
                                "instruction": "Use task/source identity only. Match, nonmatch, or unresolved; never choose by answer accuracy. Record source and locator."})
                routes[packet_id] = {"context": score["context_id"], "prediction": entry["prediction"],
                                    "table": entry["table"], "stage": stage,
                                    "candidates": {c["id"]: original["reference"] for c, original in zip(candidates, entry["candidates"])}}
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=False)
    write(folder/"review-packets.json", {"protocol": PROTOCOL, "packets": sorted(packets, key=lambda p: p["id"])})
    write(folder/"private-routes.json", routes)
    write(folder/"identity.json", {"protocol": PROTOCOL, "scores_identity": digest(scores)})
    write(folder/"review-template.json", [{"id": p["id"], "verdict": "unresolved", "candidate": None,
                                           "basis": "", "evidence": []} for p in sorted(packets, key=lambda p: p["id"])])
    seal(folder)
    return {"packets": len(packets), "folder": str(folder), "model_calls": 0}


def apply(plan, reviews, out, existing=None):
    plan = Path(plan)
    identity = verify(plan)
    if read(plan/"identity.json")["protocol"] != PROTOCOL:
        raise ValueError("Unknown identity review protocol")
    routes, entries = read(plan/"private-routes.json"), read(reviews)
    result = read(existing) if existing else {"contexts": {}}
    if set(result) != {"contexts"} or not isinstance(entries, list):
        raise ValueError("Invalid identity decisions/reviews")
    seen, audit = set(), []
    for entry in entries:
        if (not isinstance(entry, dict) or entry.get("id") not in routes or entry["id"] in seen
                or entry.get("verdict") not in {"match", "nonmatch", "unresolved"}):
            raise ValueError("Unknown, repeated or invalid identity review")
        seen.add(entry["id"])
        route = routes[entry["id"]]
        source_basis(entry)
        if entry["verdict"] == "unresolved":
            if entry.get("candidate") is not None:
                raise ValueError("Unresolved review cannot assert a match")
            audit.append(entry)
            continue
        if entry["verdict"] == "match":
            if entry.get("candidate") not in route["candidates"]:
                raise ValueError("Review candidate is not in the sealed packet")
            reference = route["candidates"][entry["candidate"]]
        else:
            if entry.get("candidate") is not None:
                raise ValueError("Nonmatch cannot identify a reference")
            reference = None
        decisions = result["contexts"].setdefault(route["context"], {}).setdefault("matches", {}).setdefault(route["table"], [])
        if any(d["prediction"] == route["prediction"] or reference is not None and d["reference"] == reference for d in decisions):
            raise ValueError("Identity decisions must remain one-to-one; existing decisions cannot be overwritten")
        decisions.append({"prediction": route["prediction"], "reference": reference,
                          "basis": entry["basis"], "evidence": entry["evidence"]})
        audit.append(entry)
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=False)
    write(folder/"adjudications.json", result)
    write(folder/"review-audit.json", {"protocol": PROTOCOL, "plan_identity": identity, "reviews": audit,
                                      "not_reviewed": sorted(set(routes)-seen)})
    seal(folder)
    return {"adjudications": str(folder/"adjudications.json"), "reviewed": len(audit), "model_calls": 0}
