"""Historical scoring orchestration; comparisons belong to module four."""
import json
from pathlib import Path
from model_conversation.archive import read, write, digest

def score_run(args):
    from .evaluation import score
    if getattr(args,'with_analysis',False):
        raise ValueError('Run biotracebench_analysis separately after scoring')
    from model_conversation.archive import verify, sha
    from decimal import Decimal
    run = Path(args.run)
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=False)
    manifest = read(run/"manifest.json")
    from biotracebench import conditions as condition_names
    condition_names.stages(manifest)
    policy = read(args.policy)
    if getattr(args, "provisional", False) and policy.get("version") != "biotracebench-score-2":
        raise ValueError("Draft diagnostic scoring requires the v2 policy")
    decisions = json.loads(Path(args.adjudications).read_text(), parse_float=Decimal) if args.adjudications else None
    studies, blind, gold_identities = [], {}, {}
    expected, capsules = [], []
    task_ids = [task['case_id'] for task in manifest['tasks']]
    if len(task_ids) != len(set(task_ids)) or len(manifest['stages']) != len(set(manifest['stages'])):
        raise ValueError('Expected scoring outputs must be unique')
    for task in manifest["tasks"]:
        prepared = Path(task["prepared"])
        try:
            verify(prepared, task["material_identity"])
            meta = read(prepared/"materials.json")
            dictionary = read(prepared/"dictionary.json")
            gold_path = Path(args.gold_root)/meta["domain"]/task["case_id"]/(task["case_id"]+".json")
            gold = json.loads(gold_path.read_text(), parse_float=Decimal)
            gold_identities[task["case_id"]] = sha(gold_path)
        except (OSError, ValueError, RuntimeError, KeyError) as error:
            expected.extend({'case_id':task['case_id'], 'condition':stage, 'status':'blocked',
                             'reason':'input_archive_or_reference_error', 'error_type':type(error).__name__}
                            for stage in manifest['stages'])
            continue
        conditions = {}
        for stage in manifest["stages"]:
            final = run/task["case_id"]/stage/"final"
            from .scoring_input import load_submission
            scope = {"case_id": task["case_id"], "study_id": meta["study_id"], "materials": task["material_identity"]}
            try:
                prediction, intake = load_submission(run, task["case_id"], stage)
                result = score(prediction, gold, dictionary, policy, decisions, context=scope, allow_unfrozen=getattr(args, "provisional", False))
            except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
                pending = isinstance(error, ValueError) and str(error).startswith('Scoring deferred:')
                expected.append({'case_id':task['case_id'], 'condition':stage,
                                 'status':'pending' if pending else 'blocked',
                                 'reason':'execution_not_terminal' if pending else 'intake_or_evaluator_error',
                                 'error_type':type(error).__name__})
                continue
            capsules.append({'case_id':task['case_id'], 'condition':stage, 'study_id':meta['study_id'],
                             'domain':meta['domain'], 'prediction':prediction, 'gold':gold, 'dictionary':dictionary,
                             'policy':policy, 'decisions':decisions, 'scope':scope, 'intake':intake,
                             'result_identity':digest(result), 'reference_identity':gold_identities[task['case_id']]})
            result['comparison_status'] = result['status']
            result['completion_status'] = 'awaiting_human_review'
            result['status'] = 'provisional'
            result["submission_intake"] = intake
            if intake["availability"] == "unreadable_requires_review":
                result["status"] = "provisional"
                result["adjudication_queue"].append({"id": digest(intake), "kind": "unreadable_submission",
                                                   "context_id": result.get("context_id"), "intake": intake})
            for entry in result["adjudication_queue"]:
                blind[entry["id"]] = {**entry, "case_id": task["case_id"], "study_id": meta["study_id"]}
            conditions[stage] = result
            expected.append({'case_id':task['case_id'], 'condition':stage, 'status':'awaiting_human_review',
                             'pending_items':len(result['adjudication_queue']), 'reason':'batch_human_check_required'})
        studies.append({"case_id": task["case_id"], "study_id": meta["study_id"], "domain": meta["domain"], "conditions": conditions})
    write(output/"study-scores.json", studies)
    write(output/"object-alignment.json", [
        {"case_id": study["case_id"], "condition": stage, "context_id": result.get("context_id"),
         "identity_contract": result.get("identity_contract"),
         "identity_rules_identity": result.get("identity_rules_identity"),
         "tables": result.get("alignment_audit", {})}
        for study in studies for stage, result in study["conditions"].items()])
    write(output/"blind-adjudication-queue.json", list(blind.values()))
    from .scoring_items import safe
    write(output/"identity.json", {"run_manifest": digest(manifest), "policy": digest(policy), "adjudications": digest(safe(decisions)), "gold":gold_identities})
    from biotracebench.export import database
    rows = [{"case_id":s["case_id"],"study_id":s["study_id"],"domain":s["domain"],"condition":stage,"metric":metric,"status":result["status"],**result[metric]}
            for s in studies for stage,result in s["conditions"].items() for metric in ("field","record")]
    database({"study_metrics":rows}, output/"report")
    from .completion import save_round
    save_round(output, expected, capsules, studies)
    return 0
