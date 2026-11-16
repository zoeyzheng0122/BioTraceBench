"""Execution management views; no model calls, gold access, or scientific scoring."""
import csv
import html
import json
import uuid
from decimal import Decimal
from pathlib import Path
from .common import digest, event, now, read, verify, verify_events, write, Stop
from .conditions import canonical, stages, CANONICAL, identity as condition_identity

PROTOCOL = 'biotracebench-management-1'

def identity(root, manifest):
    folder=Path(root)/'management';folder.mkdir(exist_ok=True)
    expected={"protocol":PROTOCOL,"manifest_identity":manifest['identity'],"manifest_hash":digest(manifest),
              "code_identity":manifest.get('implementation'),"runtime":manifest.get('runtime'),
              "task_set_identity":manifest.get('task_set_identity'),"condition_identity":manifest.get('condition_identity') or condition_identity(manifest),
              "prompts":manifest.get('prompt_hashes'),"model":manifest['model'],
              "pdf_policy":manifest.get('pdf_policy'),"cost_purpose":manifest.get("cost_purpose","task_generation")}
    if manifest.get("submission_protocol"):
        expected.update(dataset=manifest.get("dataset"), submission_protocol=manifest["submission_protocol"],
                        input_bindings=[{k: task.get(k) for k in ("case_id", "source_identity", "dataset_identity", "effective_input_identity")}
                                        for task in manifest["tasks"]])
    if manifest.get("initial_review_policy"):
        expected["initial_review_policy"] = manifest["initial_review_policy"]
    p=folder/'identity.json'
    if p.exists():
        saved=read(p)
        if saved.get('binding')!=expected or saved.get('identity')!=digest({k:v for k,v in saved.items() if k!='identity'}):
            raise Stop('tampered','Run management identity changed')
    else:
        saved={'run_id':str(uuid.uuid4()),'created_at':now(),'binding':expected}
        saved['identity']=digest(saved);write(p,saved)
    verify_events(folder)
    return saved

def begin(root,manifest,offline):
    ident=identity(root,manifest)
    session=str(uuid.uuid4())
    existing=[str(p.relative_to(root)) for p in sorted(Path(root).glob('*/**/calls/*/completion/request.json'))]
    event(Path(root)/'management','session_started',session_id=session,run_id=ident['run_id'],
          mode='offline_replay' if offline else 'execute_or_resume',existing_requests=existing,
          limit_extensions=[digest(read(p)) for p in sorted((Path(root)/'limit-extensions').glob('*.json'))])
    return session, set(existing)

def transition(root,case,stage,before,after,reason=None):
    if before!=after:
        event(Path(root)/'management','stage_transition',case_id=case,stage=stage,before=before,after=after,reason=reason)

def answer_state(final):
    if not final.exists():return 'no_submission',None
    try:
        stamp=verify(final)
    except Stop:
        return "archive_integrity_error",None
    db=read(final/'database.json')
    diagnostics=read(final/'diagnostics.json') if (final/'diagnostics.json').exists() else []
    assessment=read(final/'output-assessment.json') if (final/'output-assessment.json').exists() else {}
    # Readability only, not scientific validity. Do not repair or delete any row.
    if isinstance(db,dict) and any(isinstance(v,list) for v in db.values()):
        state='partially_readable' if assessment.get('database_schema_valid') is False or (not assessment and diagnostics) else 'readable'
    else:state='unreadable'
    return state,stamp

def execution_state(raw,answer):
    if answer=='archive_integrity_error':return 'integrity_error'
    if answer!='no_submission':return 'submitted'
    if raw in {'running','replaying'}:return raw
    if raw=='blocked_initial':return 'blocked_dependency'
    if raw.startswith('deferred'):return 'deferred'
    if raw.startswith('paused') or raw in {'offline_missing','account_busy'}:return 'paused'
    if raw.startswith('failed') or raw in {'cancelled','terminated'}:return 'failed'
    return 'not_started'

def money_view(rows):
    estimates=[r.get('amount') for r in rows]
    bounds=[r.get('budget_upper') for r in rows]
    return {'request_count':len(rows),'billed_actual':None,
            'tariff_estimate':str(sum(Decimal(x) for x in estimates)) if all(x is not None for x in estimates) else None,
            'cost_upper':str(sum(Decimal(x) for x in bounds)) if all(x is not None for x in bounds) else None,
            'known_upper_subtotal':str(sum(Decimal(x) for x in bounds if x is not None)),
            'unknown_cost_requests':sum(x is None for x in bounds),
            'basis':'tariff_calculation_not_provider_invoice'}

def refresh(root,manifest,status,costs,session=None,existing=None):
    root=Path(root);folder=root/'management';ident=identity(root,manifest)
    existing=existing or set()
    call_rows=[]
    for r in costs['calls']:
        r=dict(r)
        r.update(purpose=manifest.get('cost_purpose','task_generation'),run_id=ident['run_id'],currency=costs['currency'],
                 tariff_identity=r.get('tariff_identity') if r.get('imported') else digest(manifest['tariff']),
                 tariff_basis=r.get('tariff_basis',r.get('cost')) if r.get('imported') else manifest['tariff'],billed_actual=None,
                 cost_class='tariff_estimate' if r.get('amount') is not None else 'upper_bound' if r.get('budget_upper') is not None else 'unknown',
                 execution='response_archived' if r.get('http') else 'execution_or_consumption_unknown',
                 reuse='imported_prior_run' if r.get('imported') else 'local_physical_request')
        if not r.get('imported'):
            raw_path=Path(root)/r['attempt']/'response.bin'
            raw=None
            if raw_path.exists():
                try:
                    if manifest['model'].get('stream'):
                        from model_conversation.streaming import decode
                        from model_conversation import Conversation
                        raw=decode(raw_path.read_bytes(), Conversation(manifest['model']).adapter.protocol)
                    else:
                        raw=read(raw_path)
                except (ValueError,UnicodeError,Stop):pass
            r['requested_model']=manifest['model'].get('model')
            r['actual_model']=raw.get('model',raw.get('modelVersion')) if isinstance(raw,dict) else None
            r['provider_request_id']=raw.get('id',raw.get('responseId')) if isinstance(raw,dict) else None
            phase=Path(root)/r['case_id']/r['stage']
            request_index=int(Path(r['attempt']).parent.name)
            events_path=phase/'events.jsonl'
            history=[json.loads(line) for line in events_path.read_text().splitlines()] if events_path.exists() else []
            relevant=[x for x in history if x.get('index')==request_index]
            r['started_at']=next((x['time'] for x in relevant if x['kind']=='request_started'),None)
            r['ended_at']=next((x['time'] for x in reversed(relevant) if x['kind'] in {'request_finished','request_stopped'}),None)
        r['call_id']=digest({'run':ident['run_id'],'attempt':r.get('attempt'),'request':r.get('request_hash'),'imported':r.get('imported',False)})
        call_rows.append(r)
    rows=[];forks={}; workflows={}
    for task in manifest['tasks']:
        case=task['case_id'];start_hashes={};origins={}
        initial_start = root/case/stages(manifest)[0]/'initial-review-start.json'
        initial_review = read(initial_start) if initial_start.exists() else None
        for stage in stages(manifest):
            directory=root/case/stage;final=directory/'final'
            answer,stamp=answer_state(final)
            raw=status.get('tasks',{}).get(case,{}).get(stage,'not_started')
            calls=[r for r in call_rows if r['case_id']==case and r['stage']==stage]
            branch=read(directory/'branch.json') if (directory/'branch.json').exists() else None
            if branch and canonical(stage)!='i0':
                start_hashes[canonical(stage)]=branch.get('i0_history_sha256',branch.get('initial_history_sha256'))
                origins[canonical(stage)]=branch.get('parent_final_identity')
            metrics=money_view(calls)
            new=sum(not r.get('imported') and r['attempt']+'/request.json' not in existing for r in calls) if session else None
            row={'case_id':case,'condition':stage,'execution':execution_state(raw,answer), 'answer':answer,
                 'scientific_evaluation':'not_evaluated_by_execution','raw_status':raw,
                 'new_requests_this_session':new,'session_id':session,'requests_in_accounting':len(calls),
                 'stop_reason':(status.get('failure') or {}).get('message') if raw.startswith(('failed','paused')) else raw if raw in {'blocked_initial','deferred_capacity'} else None,
                 'result_path':str(final.relative_to(root)) if final.exists() else None,'result_identity':stamp,
                 'branch':branch,'cost':metrics}
            rows.append(row)
        comparable=set(start_hashes)=={'gsr','ssr'} and all(start_hashes.values())
        same=bool(comparable and len(set(start_hashes.values()))==1)
        if comparable and not same:raise Stop('branch_mismatch','GSR/SSR initial history differs')
        nonempty=[x for x in origins.values() if x]
        if len(nonempty)==2 and len(set(nonempty))!=1:raise Stop('branch_mismatch','GSR/SSR initial answer differs')
        forks[case]={'history_hashes':start_hashes,'initial_result_identities':origins,
                     'common_start':'verified' if same else 'not_yet_comparable',
                     'condition_protocol':manifest['protocol'],
                     'interpretation':'hashes verify that both reviews share the same initial conversation'}
        if manifest.get('initial_review_policy'):
            forks[case]['initial_review_start'] = initial_review
        scoped=[r for r in call_rows if r['case_id']==case]
        labels={'I0':{'i0'},'I0+GSR':{'i0','gsr'},'I0+SSR':{'i0','ssr'},'experiment_total':{'i0','gsr','ssr'}}
        if stages(manifest)!=CANONICAL:
            labels={'I0':{'i0'},'I0+G':{'i0','gsr'},'I0+IR':{'i0','ssr'},'experiment_total':{'i0','gsr','ssr'}}
        workflows[case]={label:money_view([r for r in scoped if canonical(r['stage']) in include and
                        (label=='experiment_total' or not r.get('historical_round'))]) for label,include in labels.items()}
    estimator=[]
    for p in sorted(root.glob('*/**/calls/*/estimate*/request.json')):
        request=read(p)
        estimator.append({'path':str(p.relative_to(root)),'kind':'local_reservation' if 'policy' in request else 'provider_token_estimate',
                          'billed_actual':None,'cost_status':'not_an_api_call' if 'policy' in request else 'not_established'})
    accounting={'protocol':PROTOCOL,'cost_contract':'biotracebench-cost-record-1','run_id':ident['run_id'],'purpose':manifest.get('cost_purpose','task_generation'),'currency':costs['currency'],
                'calls':call_rows,'generation_totals':money_view(call_rows),'workflows':workflows,
                'estimation_operations':estimator,'scoring_costs':'separate_scoring_run_not_included',
                'generation_actual_total':None,'estimator_costs_complete':not any(x['kind']=='provider_token_estimate' for x in estimator)}
    write(folder/'cost-ledger.json',accounting)
    report={'protocol':PROTOCOL,'run_id':ident['run_id'],'session_id':session,'updated_at':now(),
            'manifest_identity':manifest['identity'],'rows':rows,'forks':forks,'science_correctness':'not_assessed'}
    write(folder/'overview.json',report)
    headers=['case_id','condition','execution','answer','scientific_evaluation','new_requests_this_session','requests_in_accounting','stop_reason','result_path']
    with (folder/'overview.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=headers+['tariff_estimate','cost_upper','unknown_cost_requests'])
        writer.writeheader()
        for r in rows:writer.writerow({**{k:r[k] for k in headers},**{k:r['cost'][k] for k in ('tariff_estimate','cost_upper','unknown_cost_requests')}})
    cells=[]
    for r in rows:
        values=[r['case_id'],r['condition'],r['execution'],r['answer'],r['new_requests_this_session'],r['cost']['tariff_estimate'],r['cost']['cost_upper'],r['cost']['unknown_cost_requests'],r['stop_reason']]
        line=''.join('<td>'+html.escape(str(x) if x is not None else 'Unknown / not applicable')+'</td>' for x in values)
        link='<a href="../'+html.escape(r['result_path'],quote=True)+'/">Result archive</a>' if r['result_path'] else 'No final submission'
        cells.append('<tr>'+line+'<td>'+link+'</td></tr>')
    review_note = '<p>Normally received initial answers are retained, including format defects. GSR and SSR start from the same answer. Incomplete responses and budget or account stops are not automatically retried.</p>' if manifest.get('initial_review_policy') else ''
    (folder/'overview.html').write_text('<!doctype html><meta charset="utf-8"><title>BioTraceBench run overview</title><style>body{font:15px sans-serif;margin:28px}td,th{padding:9px;border:1px solid #ccc}table{border-collapse:collapse}</style><h1>BioTraceBench run overview</h1><p>Execution and answer readability are shown separately from scientific scoring. Currency: '+html.escape(costs['currency'])+'. Tariff estimates and upper bounds are separate from billed amounts. Scoring judge costs are recorded separately.</p>'+review_note+'<table><tr>'+''.join('<th>'+x+'</th>' for x in ['Task','Condition','Execution','Answer readability','New requests this session','Tariff estimate','Cost upper bound','Requests with unknown cost','Stop reason','Result'])+'</tr>'+''.join(cells)+'</table>',encoding='utf-8')
    return report
