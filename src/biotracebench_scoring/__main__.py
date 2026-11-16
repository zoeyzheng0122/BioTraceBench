import argparse
import json
from .workflow import score_run
from . import scoring_judge

def main(argv=None):
    parser=argparse.ArgumentParser(prog="biotracebench_scoring")
    commands=parser.add_subparsers(dest="command",required=True)
    p=commands.add_parser("native-prepare",help="Freeze blinded inputs for direct native Codex judgment; starts no model process")
    for name in ("manifest","contexts","task-policies","out"):p.add_argument("--"+name,required=True)
    p.add_argument("--condition",action="append",choices=["i0","gsr","ssr"])
    p=commands.add_parser("native-import",help="Validate and retain an existing direct Codex judgment")
    for name in ("plan","job","reply","actor"):p.add_argument("--"+name,required=True)
    p.add_argument("--phase",choices=["first","review"],default="first")
    p.add_argument("--scope",choices=["whole","records","fields"],default="whole")
    p.add_argument("--mapping-identity")
    p.add_argument("--evidence",help="Optional source evidence ledger JSON")
    p=commands.add_parser("native-replay",help="Revalidate saved direct judgments and export coverage offline")
    for name in ("plan","out"):p.add_argument("--"+name,required=True)
    p=commands.add_parser("native-export",help="Export exact-replay data for the independent analysis package")
    for name in ("plan","out"):p.add_argument("--"+name,required=True)
    for name in ("historical","audit","audit-provenance"):p.add_argument("--"+name)
    p.add_argument("--require-complete",action="store_true")
    p=commands.add_parser("native-compose",help="Replay and compose uniform case applicability amendments")
    for name in ("base-plan","amendments","out"):p.add_argument("--"+name,required=True)
    for name in ("base-adjudications","historical","audit","audit-provenance"):p.add_argument("--"+name)
    p.add_argument("--require-complete",action="store_true")
    p=commands.add_parser("native-adjudicate",help="Append an evidence-bound source adjudication without changing accepted imports")
    for name in ("plan","job","reply","actor","out","reason","evidence","supersedes"):
        p.add_argument("--"+name,required=True)
    p=commands.add_parser("native-export-view",help="Export separately identified first-pass or final native judgments")
    for name in ("plan","out"):p.add_argument("--"+name,required=True)
    p.add_argument("--phase",choices=["first","final"],default="final")
    for name in ("adjudications","historical","audit","audit-provenance"):p.add_argument("--"+name)
    p.add_argument("--require-complete",action="store_true")
    p=commands.add_parser("codex-prepare",help="Freeze blinded Codex CLI scoring requests from a versioned archive")
    for name in ("manifest","contexts","out"):p.add_argument("--"+name,required=True)
    p.add_argument("--condition",action="append",choices=["i0","gsr","ssr"])
    p.add_argument("--model",help="Optional explicit supported Codex model; otherwise authenticated CLI default")
    p.add_argument("--reasoning-effort",choices=["minimal","low","medium","high","xhigh","max"])
    p.add_argument("--whole-cell-limit",type=int,default=400)
    p.add_argument("--reply-encoding",choices=["expanded","compact"],default="expanded",
                   help="Serialize explicit cell judgments as full objects or lossless parallel arrays")
    for command in ("codex-run","codex-recover"):
        p=commands.add_parser(command,help="Execute or recover frozen Codex CLI scoring jobs")
        for name in ("plan","out"):p.add_argument("--"+name,required=True)
        p.add_argument("--workers",type=int,default=3)
        p.add_argument("--case")
        p.add_argument("--condition",choices=["i0","gsr","ssr"])
        p.add_argument("--limit",type=int)
        p.add_argument("--priority",help="Private JSON array of case/model/condition positions to schedule first")
        if command=="codex-run":
            p.add_argument("--execute",action="store_true",required=True)
            p.add_argument("--resume-blocked",action="store_true",help="Explicitly resume after a campaign-wide transport block")
    p=commands.add_parser("audit-rules",help="Inspect task rules and references without scoring or freezing")
    for name in ("dataset","policy","paper","out"):p.add_argument("--"+name,required=True)
    p.add_argument("--expected-tasks",type=int,required=True)
    p=commands.add_parser("grade-prepare",help="Prepare one generation run's independent I0/GSR/SSR marking; cross-model consolidation is a later analysis step")
    for name in ("run","gold-root","policy","profile","budget","out"):p.add_argument("--"+name,required=True)
    p.add_argument("--sources",help="Optional frozen non-PDF source excerpts by case")
    p.add_argument("--scoring-revision",help="Output-level revision required by a new scoring campaign")
    p.add_argument("--consistency",help="Frozen context aliases and archived model decisions by case")
    p.add_argument("--alignment-protocol",help="Versioned EFE evidence contract for new record correspondences")
    p.add_argument("--condition",action="append",choices=["i0","gsr","ssr"],
                   help="Grade selected archived outputs only; default grades all declared conditions. Repeat to select several.")
    p.add_argument("--provisional",action="store_true",help="Explicit diagnostic grading with an unfrozen policy")
    for command in ("grade-run","grade-recover"):
        p=commands.add_parser(command)
        for name in ("plan","out"):p.add_argument("--"+name,required=True)
        if command=="grade-run":p.add_argument("--execute",action="store_true",required=True)
    p=commands.add_parser("protocol-review",help="Apply a source-grounded full judgment revision in a new artifact")
    for name in ("bundle","review","out"):p.add_argument("--"+name,required=True)
    p=commands.add_parser("score",help="Historical rule/proposal workflow; use grade-prepare for current whole-task Qwen grading")
    for name in ("run","gold-root","policy","out"):p.add_argument("--"+name,required=True)
    p.add_argument("--adjudications")
    p.add_argument("--provisional", action="store_true", help="Explicit diagnostic scoring with an unfrozen v2 policy; cannot finalize")
    p=commands.add_parser("judge-prepare")
    for name in ("scores","evidence","profile","budget","out"):p.add_argument("--"+name,required=True)
    for command in ("judge-run","judge-recover"):
        p=commands.add_parser(command)
        for name in ("plan","out"):p.add_argument("--"+name,required=True)
        if command=="judge-run":p.add_argument("--execute",action="store_true",required=True)
    p=commands.add_parser("judge-review")
    for name in ("plan","run","reviews","out"):p.add_argument("--"+name,required=True)
    p.add_argument("--existing")
    p=commands.add_parser("identity-prepare",help="Create blinded human identity packets from provisional scores")
    for name in ("scores","out"):p.add_argument("--"+name,required=True)
    p=commands.add_parser("identity-review",help="Apply source-grounded human one-to-one decisions")
    for name in ("plan","reviews","out"):p.add_argument("--"+name,required=True)
    p.add_argument("--existing")
    p=commands.add_parser("check-prepare",help="Prepare one human check batch after all Qwen proposals")
    for name in ("bundle","out"):p.add_argument("--"+name,required=True)
    p.add_argument("--judge-plan")
    p.add_argument("--judge-run")
    p=commands.add_parser("check-finalize",help="Apply human checks and verify offline scoring completion")
    for name in ("plan","reviews","out"):p.add_argument("--"+name,required=True)
    a=parser.parse_args(argv)
    if a.command=='native-compose':
        from .native_case_versions import compose_native
        with open(a.amendments) as stream:amendments=json.load(stream)
        result=compose_native(a.base_plan,amendments,a.out,base_adjudications=a.base_adjudications,
            historical=a.historical,audit=a.audit,audit_provenance=a.audit_provenance,
            require_complete=a.require_complete)
        print(json.dumps(result,ensure_ascii=False))
        return 0
    if a.command in {'native-adjudicate','native-export-view'}:
        from . import native_adjudication
        if a.command=='native-adjudicate':
            with open(a.actor) as stream:actor=json.load(stream)
            result=native_adjudication.adjudicate_native(a.plan,a.job,a.reply,actor,a.out,
                reason=a.reason,evidence=a.evidence,supersedes=a.supersedes)
            result={k:v for k,v in result.items() if k!='score'}
        else:
            result=native_adjudication.export_view(a.plan,a.out,phase=a.phase,
                adjudications=a.adjudications,historical=a.historical,audit=a.audit,
                audit_provenance=a.audit_provenance,require_complete=a.require_complete)
        print(json.dumps(result,ensure_ascii=False))
        return 0
    if a.command in {'native-prepare','native-import','native-replay','native-export'}:
        from . import native_codex
        if a.command=='native-prepare':
            result=native_codex.prepare_native(a.manifest,a.contexts,a.out,
                conditions=a.condition,task_policies=a.task_policies)
        elif a.command=='native-import':
            with open(a.actor) as stream:actor=json.load(stream)
            result=native_codex.ingest_native(a.plan,a.job,a.reply,actor,
                phase=a.phase,scope=a.scope,mapping_identity=a.mapping_identity,evidence=a.evidence)
        elif a.command=='native-replay':
            result=native_codex.replay_native(a.plan,a.out)
        else:
            result=native_codex.export_native(a.plan,a.out,historical=a.historical,audit=a.audit,
                audit_provenance=a.audit_provenance,require_complete=a.require_complete)
        print(json.dumps(result,ensure_ascii=False))
        return 0 if result.get('status') not in {'incomplete','validation_error'} else 1
    if a.command in {'codex-prepare','codex-run','codex-recover'}:
        from . import codex_grading
        if a.command=='codex-prepare':
            result=codex_grading.prepare(a.manifest,a.contexts,a.out,conditions=a.condition,
                model=a.model,reasoning_effort=a.reasoning_effort,whole_cell_limit=a.whole_cell_limit,
                reply_encoding=a.reply_encoding)
        else:
            result=codex_grading.execute(a.plan,a.out,offline=a.command=='codex-recover',
                workers=a.workers,case=a.case,condition=a.condition,limit=a.limit,
                resume_blocked=getattr(a,'resume_blocked',False),
                priority_keys=json.load(open(a.priority)) if a.priority else None)
        print(json.dumps(result,ensure_ascii=False))
        return 0 if not result.get('incomplete_jobs',0) else 1
    if a.command in {'grade-prepare','grade-run','grade-recover'}:
        from . import task_grading
        result=(task_grading.prepare(a.run,a.gold_root,a.policy,a.profile,a.budget,a.out,
                  provisional=a.provisional,sources_path=a.sources,selected_conditions=a.condition,
                  scoring_revision=a.scoring_revision,consistency_path=a.consistency,
                  alignment_path=a.alignment_protocol) if a.command=='grade-prepare' else
                task_grading.execute(a.plan,a.out,offline=a.command=='grade-recover'))
        print(json.dumps(result,ensure_ascii=False))
        return task_grading.command_exit_code(result)
    if a.command=="audit-rules":
        from .rule_audit import audit
        result=audit(a.dataset,a.policy,a.paper,a.out,a.expected_tasks)
        print(json.dumps(result,ensure_ascii=False))
        return 0 if not result["failures"] else 1
    if a.command=="protocol-review":
        from .efe_protocol import review
        print(json.dumps(review(a.bundle,a.review,a.out),ensure_ascii=False))
        return 0
    if a.command=="score":return score_run(a)
    if a.command in {"check-prepare","check-finalize"}:
        from . import completion
        result = completion.prepare(a.bundle,a.out,a.judge_plan,a.judge_run) if a.command=="check-prepare" else completion.finalize(a.plan,a.reviews,a.out)
        print(json.dumps(result,ensure_ascii=False))
        return 0
    if a.command in {"identity-prepare","identity-review"}:
        from . import identity_review
        result = identity_review.prepare(a.scores,a.out) if a.command=="identity-prepare" else identity_review.apply(a.plan,a.reviews,a.out,a.existing)
        print(json.dumps(result,ensure_ascii=False))
        return 0
    if a.command=="judge-prepare":result=scoring_judge.prepare(a.scores,a.evidence,a.profile,a.budget,a.out)
    elif a.command=="judge-review":result=scoring_judge.apply_reviews(a.plan,a.run,a.reviews,a.out,a.existing)
    else:result=scoring_judge.execute(a.plan,a.out,offline=a.command=="judge-recover")
    print(json.dumps(result,ensure_ascii=False))
    return 0

if __name__=="__main__":raise SystemExit(main())
