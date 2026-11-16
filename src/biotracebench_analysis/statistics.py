"""Paired study summaries with explicit unresolved decisions and coverage."""
from collections import Counter
import random

from biotracebench.conditions import CANONICAL, LEGACY, CONTRASTS, TO_LEGACY


def compare_conditions(before, after):
    """Keep unresolved decisions separate from the four resolved transitions."""
    a = before.get("gold_field_correctness", {})
    b = after.get("gold_field_correctness", {})
    states = {True: "correct", False: "incorrect", None: "uncertain"}
    transitions = {f"{x}->{y}": 0 for x in states.values() for y in states.values()}
    pending = []
    for key in sorted(set(a) | set(b)):
        left, right = a.get(key, False), b.get(key, False)
        if left is not None and type(left) is not bool or right is not None and type(right) is not bool:
            raise ValueError("Field correctness must be true, false or null")
        transitions[f"{states[left]}->{states[right]}"] += 1
        if left is None or right is None:
            pending.append({"field": key, "before": states[left], "after": states[right]})
    return {
        "corrected": transitions["incorrect->correct"],
        "persistent_error": transitions["incorrect->incorrect"],
        "regressed": transitions["correct->incorrect"],
        "stable_correct": transitions["correct->correct"],
        "transitions": transitions, "uncertain_transitions": len(pending),
        "total_fields": sum(transitions.values()), "pending_review": pending,
    }


def condition_names(studies):
    names = set()
    for study in studies:
        names.update(study.get("conditions", {}))
        names.update(study.get("outputs", {}))
        names.update(study.get("scoring_scope", {}).get("expected_conditions", []))
    if not names or names <= set(CANONICAL):
        return CANONICAL
    if names <= set(LEGACY):
        return LEGACY
    raise ValueError("Do not mix condition naming versions in one comparison")


def uncertainty(studies, stages):
    """Count cells and records separately, retaining their original locations."""
    tasks, items = [], []
    for study in studies:
        for stage in stages:
            result = study.get("conditions", {}).get(stage)
            context = {"case_id": study.get("case_id", study["study_id"]),
                       "study_id": study["study_id"], "domain": study.get("domain"), "condition": stage}
            if result is None:
                tasks.append({**context, "uncertain_fields": 0, "uncertain_records": 0,
                              "structural_issues": 0, "pending": True, "score_available": False})
                items.append({**context, "kind": "unavailable_output",
                              "reason": study.get("outputs", {}).get(stage, "missing_score")})
                continue
            review = list(result.get("review_items", []))
            if "review_items" not in result:
                for cell in result.get("cells", []):
                    if cell["verdict"] == "uncertain":
                        location = cell.get("reference") or cell.get("prediction") or {}
                        review.append({"kind": "field", "table": location.get("table"),
                                       "row_index": location.get("row_index"), "field": location.get("field"),
                                       "reason": cell["reason"]})
                for row in result.get("records", []):
                    if row["verdict"] == "uncertain":
                        review.append({"kind": "record", **row})
                if not result.get("cells"):
                    review.extend({"kind": "field", "field": key, "reason": "Unresolved field judgment"}
                                  for key, value in result.get("gold_field_correctness", {}).items() if value is None)
            counts = Counter(item["kind"] for item in review)
            tasks.append({**context, "uncertain_fields": counts["field"], "uncertain_records": counts["record"],
                          "structural_issues": counts["structure"], "pending": bool(review), "score_available": True})
            items.extend({**context, **item} for item in review)
    groups = {}
    for domain in ("basic", "clinical", "overall"):
        groups[domain] = {}
        for stage in stages:
            rows = [t for t in tasks if t["condition"] == stage and (domain == "overall" or t["domain"] == domain)]
            groups[domain][stage] = {key: sum(t[key] for t in rows)
                                    for key in ("uncertain_fields", "uncertain_records", "structural_issues")}
            groups[domain][stage].update(tasks=len(rows), affected_tasks=sum(t["pending"] for t in rows),
                                         unavailable_outputs=sum(not t["score_available"] for t in rows))
    return {"tasks": tasks, "groups": groups, "count_basis": "raw_counts_cells_and_records_reported_separately"}, items


def _metric(study, stage, metric):
    return study.get("conditions", {}).get(stage, {}).get(metric)


def _validate_pairing(study):
    bindings = [r.get('score_binding', {}) for r in study.get('conditions', {}).values()]
    for key in ('run_manifest_identity', 'reference_sha256', 'scientific_criteria_identity',
                'judge_profile_identity', 'policy_identity', 'grading_implementation_identity'):
        identities = {b[key] for b in bindings if b.get(key) is not None}
        expected = study.get('scoring_scope', {}).get(key)
        if len(identities) > 1 or expected is not None and identities and identities != {expected}:
            raise ValueError('Conditions must share one explicit run, reference and scoring configuration: '+key)


def aggregate(studies, seed=20261024, resamples=10000):
    for study in studies:
        _validate_pairing(study)
    stages = condition_names(studies)
    contrasts = CONTRASTS if stages == CANONICAL else tuple((TO_LEGACY[a], TO_LEGACY[b]) for a, b in CONTRASTS)
    if resamples != 10000:
        raise ValueError("Protocol freezes 10,000 paired study resamples")
    if len({s["study_id"] for s in studies}) != len(studies):
        raise ValueError("Aggregate repeated DOI/tasks within study before bootstrap")
    rng = random.Random(seed)
    domains = {name: [s for s in studies if s.get("domain") == name] for name in ("basic", "clinical")}
    unassigned = [s["study_id"] for s in studies if s.get("domain") not in domains]
    results, coverage = {}, {}
    for metric in ("field", "record"):
        for a, b in contrasts:
            samples = {}
            for domain, records in domains.items():
                if not records:
                    continue
                available = [r for r in records if _metric(r, a, metric) is not None and _metric(r, b, metric) is not None]
                key = f"{domain}:{metric}:{a}-{b}"
                if len(available) != len(records):
                    results[key] = {"mean": None, "ci95": None, "studies": len(records),
                                    "available_studies": len(available), "score_basis": "incomplete_metrics"}
                    continue
                deltas = [_metric(r, a, metric)["f1"] - _metric(r, b, metric)["f1"] for r in records]
                draws = [sum(rng.choice(deltas) for _ in deltas) / len(deltas) for _ in range(resamples)]
                samples[domain] = draws
                ordered = sorted(draws)
                results[key] = {"mean": sum(deltas) / len(deltas), "ci95": [ordered[249], ordered[9749]], "studies": len(deltas)}
                if any(r['conditions'][s].get('status')=='provisional' or
                       r['conditions'][s].get('review_items') for r in records for s in (a,b)):
                    results[key]['score_basis'] = 'provisional_inputs'
            if all(domains.values()):
                key = f"overall:{metric}:{a}-{b}"
                if len(samples) == 2 and not unassigned:
                    draws = sorted((x + y) / 2 for x, y in zip(samples["basic"], samples["clinical"]))
                    means = [results[f"{d}:{metric}:{a}-{b}"]["mean"] for d in domains]
                    results[key] = {"mean": sum(means) / 2, "ci95": [draws[249], draws[9749]], "domain_weights": [0.5, 0.5]}
                    if any(results[f"{d}:{metric}:{a}-{b}"].get('score_basis')=='provisional_inputs' for d in domains):
                        results[key]['score_basis'] = 'provisional_inputs'
                else:
                    results[key] = {"mean": None, "ci95": None, "domain_weights": [0.5, 0.5], "score_basis": "incomplete_metrics"}
    means = {}
    for domain, records in domains.items():
        if not records:
            continue
        means[domain], coverage[domain] = {}, {}
        for stage in stages:
            means[domain][stage], coverage[domain][stage] = {}, {}
            for metric in ("field", "record"):
                values = [_metric(r, stage, metric) for r in records]
                available = [v for v in values if v is not None]
                coverage[domain][stage][metric] = {"expected_studies": len(records), "available_studies": len(available),
                    "unavailable_studies": [r["study_id"] for r, v in zip(records, values) if v is None]}
                means[domain][stage][metric] = {stat: sum(v[stat] for v in available) / len(records)
                    if len(available) == len(records) else None for stat in ("precision", "recall", "f1")}
    if len(means) == 2:
        means["overall"] = {s: {m: {v: (means["basic"][s][m][v] + means["clinical"][s][m][v]) / 2
            if not unassigned and means["basic"][s][m][v] is not None and means["clinical"][s][m][v] is not None
            else None for v in ("precision", "recall", "f1")} for m in ("field", "record")} for s in stages}
    unresolved, review = uncertainty(studies, stages)
    provisional = not studies or bool(review) or any(c.get("status") == "provisional" for s in studies for c in s.get("conditions", {}).values())
    return {"means": means, "paired_differences": results, "seed": seed, "resamples": resamples,
            "coverage": coverage, "unassigned_studies": unassigned,
            "uncertainty": unresolved, "pending_review": review,
            "score_basis": "provisional_inputs" if provisional else "resolved_scores",
            "status": "provisional" if provisional else "final_under_frozen_dictionary"}
