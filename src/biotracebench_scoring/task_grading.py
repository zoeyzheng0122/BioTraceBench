"""Qwen marks full tasks, exports corrections and finishes before external human review."""
import copy
import fcntl
import hashlib
import re
import sys
from decimal import Decimal
from pathlib import Path
from model_conversation.archive import read, write, digest, sha, seal, verify, within, event, encoded, verify_events
from model_api import Backend, load_profile, implementation_identity as api_identity
from model_api.archive_integrity import ArchiveConflict
from model_api import dispatch
from .scoring_input import strict_json, load_submission
from .scoring_judge import positive
from .identity_alignment import scoped_policy
from .task_grading_contract import PROTOCOL, PROMPT, RESPONSE_SCHEMA, inventory, mark_all, usable_prediction, zero_result
from .task_grading_report import task_report, overview, WORKFLOW_SCOPE
from .task_grading_budget import output_control, usage_breakdown
from .grading_attempts import GradingAttempts, retry_limit
from .grading_archives import assessment_path
from .grading_precision import criteria as precision_criteria, POLICY as PRECISION_POLICY
from .grading_consistency import checked_memory, validate_decisions, alignment_hint

SCIENTIFIC_POLICY_KEYS = {
    'version', 'item_policy', 'reference_contract', 'field_roles', 'field_rules',
    'field_granularity', 'null_policy', 'compound_fields', 'compound_policy',
    'numeric_policy', 'identity_contract', 'identity_policy', 'identity_groups',
    'identity_guards', 'identity_accessions', 'identity_strong_groups',
    'identity_native_labels', 'text_contract', 'text_policy', 'semantic_context_fields',
    'precision_contract', 'precision_policy', 'unit_contract', 'unit_bindings'}
UNIT_CRITERIA_KEYS = {'version', 'value_unit_pairs', 'families',
    'not_automatically_equivalent', 'coupled_content', 'unsupported_forms'}


def _grading_policy(policy, case, dictionary):
    """Select current scientific criteria, never an entire mixed workflow config."""
    scoped=scoped_policy(policy,{'case_id':case})
    precision=precision_criteria(scoped)
    for rule in scoped.get('field_rules',{}).values():
        if not isinstance(rule,dict):raise ValueError('Field rules must be objects')
        if {'unit_field','canonical_unit','unit_scales','scale_companion_items'} & set(rule):
            raise ValueError('Remove superseded field-level unit rules; whole-task grading uses unit_catalog and unit_bindings only')
        if {'rounding','decimal_places','source_precision','tolerance','absolute_tolerance','relative_tolerance'} & set(rule):
            raise ValueError('Remove competing field-level precision rules; use shared bidirectional rounding')
    effective={key:copy.deepcopy(scoped[key]) for key in SCIENTIFIC_POLICY_KEYS if key in scoped}
    effective.update(precision)
    if 'unit_catalog' in scoped or 'unit_bindings' in scoped:
        from .unit_catalog import compile_unit_rules
        compile_unit_rules(scoped.get('unit_catalog'),scoped.get('unit_bindings'),dictionary,scoped)
        catalog=scoped['unit_catalog']
        criteria={key:copy.deepcopy(catalog[key]) for key in UNIT_CRITERIA_KEYS if key in catalog}
        permission=catalog.get('case_specific_existing_permission',{}).get(case)
        if permission is not None:criteria['case_specific_existing_permission']={case:permission}
        effective['unit_catalog']=criteria
    return effective


def implementation():
    return {'scorer':{p.name:sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
            'api':api_identity(),'python':sys.version}


def _no_pdf(folder):
    if any(p.suffix.lower()=='.pdf' for p in Path(folder).rglob('*')):
        raise ValueError('PDF archives are excluded from task grading')


def _prepared(folder, expected):
    """Check only used text/metadata against the preparation receipt; never hash materials."""
    folder=Path(folder).resolve()
    receipt=read(folder/'receipt.json')
    if digest(receipt['files'])!=receipt['sha256'] or receipt['sha256']!=expected:
        raise ValueError('Prepared-input receipt identity changed')
    result={}
    for name in ('dictionary.json','materials.json','instruction.md'):
        path=within(folder,name)
        raw=path.read_bytes()
        if name not in receipt['files'] or hashlib.sha256(raw).hexdigest()!=receipt['files'][name]:
            raise ValueError('Used preparation input identity changed')
        text=raw.decode('utf-8-sig')
        result[name]=text if name.endswith('.md') else strict_json(text)
    return result


def preparation_summary(entries):
    """Report technical readiness separately from grading or scientific correctness."""
    ready=sum(e['status']=='prepared' for e in entries)
    waiting=sum(e['status']=='waiting_for_input' for e in entries)
    blocked=sum(e['status']=='blocked_input_or_capacity' for e in entries)
    if not entries or ready+waiting+blocked!=len(entries):
        raise ValueError('Preparation entries must have explicit readiness states')
    status=('preparation_completed' if ready==len(entries) else
            'preparation_partial' if ready else
            'waiting_for_inputs' if waiting==len(entries) else 'no_ready_outputs')
    return {'status':status,'expected_outputs':len(entries),'prepared_outputs':ready,
            'blocked_outputs':blocked,'waiting_outputs':waiting,
            'blocked_or_waiting':blocked+waiting,'can_start_grading':bool(ready)}


def command_exit_code(result):
    """Expose incomplete preparation to shell callers without discarding ready work."""
    status=result.get('status')
    if status=='preparation_partial':return 2
    if result.get('failed_outputs') or status in {'paused','no_ready_outputs'}:return 1
    if status=='waiting_for_inputs':return 3
    return 0 if status in {'preparation_completed','automatic_scoring_completed'} else 1


def prepare(run, gold_root, policy_path, profile_path, budget_path, out, *, provisional=False, sources_path=None,
            selected_conditions=None, scoring_revision=None, consistency_path=None, alignment_path=None):
    run=Path(run).resolve();gold_root=Path(gold_root).resolve();out=Path(out).resolve()
    source_root=Path(__file__).resolve().parents[2]
    if out.is_relative_to(source_root) or out.is_relative_to(run) or out.is_relative_to(gold_root):
        raise ValueError('Keep grading artifacts outside source and input directories')
    policy=strict_json(Path(policy_path).read_text())
    if policy.get('task_grading_contract',PROTOCOL)!=PROTOCOL:
        raise ValueError('Unknown whole-task grading policy contract')
    if not policy.get('frozen') and not provisional:
        raise ValueError('Rules are unfrozen; use explicit provisional grading, not a formal comparison')
    profile=load_profile(profile_path).describe()
    if profile['provider'] not in {'qwen','deepseek'}:raise ValueError('Whole-task grading requires an explicit supported Qwen or DeepSeek profile')
    control=output_control(profile)
    from . import efe_protocol
    alignment_definition=efe_protocol.definition(alignment_path) if alignment_path else None
    instruction=PROMPT+'\n'+efe_protocol.INSTRUCTION if alignment_definition else PROMPT
    grading_identity=digest(implementation())
    prompt_identity=digest(instruction)
    transport=Backend(profile)
    manifest=read(run/'manifest.json')
    stages=manifest.get('stages',[]);tasks=manifest.get('tasks',[])
    safe_name=lambda v:isinstance(v,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',v)
    if (not stages or not tasks or any(not safe_name(s) for s in stages)
            or len(stages)!=len(set(stages)) or any(not safe_name(t.get('case_id')) for t in tasks)
            or len(tasks)!=len({t['case_id'] for t in tasks})):
        raise ValueError('Expected task/condition identities must be explicit, safe and unique')
    expected_stages=list(stages)
    if selected_conditions is not None:
        requested=list(selected_conditions)
        if not requested or len(requested)!=len(set(requested)) or not set(requested)<=set(stages):
            raise ValueError('Grading conditions must be a unique nonempty subset of the declared experiment')
        stages=[s for s in stages if s in requested]
    input_roots=[str(run),str(gold_root),*[str(Path(t['prepared']).resolve()) for t in tasks]]
    if any(out.is_relative_to(Path(p)) for p in input_roots):
        raise ValueError('Keep grading artifacts outside immutable input directories')
    sources=read(sources_path) if sources_path else {}
    memories=read(consistency_path) if consistency_path else {}
    if scoring_revision is not None and (not isinstance(scoring_revision,str)
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',scoring_revision)):
        raise ValueError('Scoring revision must be a nonempty safe identifier')
    if not isinstance(memories,dict) or not set(memories)<=set(t['case_id'] for t in tasks):
        raise ValueError('Consistency memory must select declared cases')
    entries,packets=[],[]
    for task in tasks:
        case=task['case_id']
        for stage in stages:
            entry={'id':digest({'run':digest(manifest),'case':case,'condition':stage}),
                   'case_id':case,'condition':stage,'status':'prepared'}
            try:
                prepared=_prepared(task['prepared'],task['material_identity'])
                meta=prepared['materials.json'];domain=meta['domain']
                if domain not in {'basic','clinical'}:raise ValueError('Invalid task domain')
                entry.update(domain=domain,study_id=meta['study_id'])
                gold_path=within(gold_root,domain+'/'+case+'/'+case+'.json')
                gold_bytes=gold_path.read_bytes();gold_text=gold_bytes.decode('utf-8-sig')
                gold=strict_json(gold_text);gold_checksum=hashlib.sha256(gold_bytes).hexdigest()
                _no_pdf(run/case/stage/'final')
                prediction,intake=load_submission(run,case,stage)
                if intake['availability']=='unreadable_requires_review':
                    raise ValueError('Unreadable submission retained; no scientific cells or zero score invented')
                dictionary=prepared['dictionary.json']
                inv=inventory(prediction,gold,dictionary,policy)
                entry['structural_diagnostics']=inv['diagnostics']
                effective=_grading_policy(policy,case,dictionary)
                entry['score_binding']={'run_manifest_identity':digest(manifest),
                    'preparation_identity':task['material_identity'],'reference_sha256':gold_checksum,
                    'scientific_criteria_identity':digest(effective),'submission':intake,
                    'precision_policy_identity':digest(effective['precision_policy']),
                    'judge_profile_identity':digest(profile),'policy_identity':digest(policy),
                    'grading_implementation_identity':grading_identity,'prompt_identity':prompt_identity}
                context=sources.get(case,[])
                if not isinstance(context,list):raise ValueError('Source excerpts must be a list')
                for excerpt in context:
                    if (not isinstance(excerpt,dict) or set(excerpt)!={'id','source','locator','text'}
                            or any(not isinstance(v,str) or not v.strip() for v in excerpt.values())
                            or '.pdf' in excerpt['source'].lower()):
                        raise ValueError('Only explicit non-PDF frozen source excerpts are accepted')
                if len({s['id'] for s in context}) != len(context):
                    raise ValueError('Frozen source excerpt IDs must be unique')
                memory=checked_memory(memories.get(case),context)
                entry['score_binding']['sources_identity']=digest(context)
                if alignment_definition:
                    entry['score_binding']['alignment_definition_identity']=digest(alignment_definition)
                if scoring_revision is not None:
                    entry['score_binding']['scoring_revision']=scoring_revision
                if case in memories:
                    entry['score_binding']['consistency_memory_identity']=digest(memory)
                request={'protocol_version':PROTOCOL,'stage':'task_grading','instruction':instruction,
                    'payload':{'task_definition':prepared['instruction.md'],
                        'dictionary_json':encoded(dictionary).decode(),
                        'scoring_policy_json':encoded(effective).decode(),
                        'inventory':inv,'sources':context},
                    'response_schema':efe_protocol.schema() if alignment_definition else RESPONSE_SCHEMA,'images':[]}
                if alignment_definition:
                    request['payload']['alignment_definition']=alignment_definition
                if case in memories:
                    request['payload']['consistency_memory']=memory
                terminal=intake.get('terminal') or intake['availability'] in {'terminal_no_output','terminal_no_usable_output'}
                local=terminal and not usable_prediction(inv)
                entry['scoring_mode']='local' if local else profile['provider']
                packet={'id':entry['id'],'request':None if local else request,'inventory':inv,
                    'consistency_scope':{k:entry['score_binding'][k] for k in (
                        'reference_sha256','scientific_criteria_identity','judge_profile_identity',
                        'prompt_identity','grading_implementation_identity','sources_identity',
                        'scoring_revision','alignment_definition_identity') if k in entry['score_binding']},
                    'local_result':zero_result(inv) if local else None,
                    'inputs':{'prediction_json':None if prediction is None else
                              encoded(prediction).decode(),
                              'reference_json':gold_text,'reference_sha256':gold_checksum,
                              'preparation_receipt':task['material_identity'],'intake':intake}}
                if alignment_definition:
                    packet['alignment_definition']=alignment_definition
                    packet['sources']=context
                    if local:
                        packet['local_result']=efe_protocol.terminal(inv,alignment_definition,context)
                if not local:
                    hint=alignment_hint(packet)
                    if hint is not None:request['payload']['frozen_record_alignment']=hint
                    transport.preflight(request)
                if sha(gold_path)!=gold_checksum:raise ValueError('Reference changed during preparation')
                packets.append(packet)
            except (OSError,ValueError,RuntimeError,KeyError,TypeError) as error:
                deferred=isinstance(error,ValueError) and str(error).startswith('Scoring deferred:')
                entry.update(status='waiting_for_input' if deferred else 'blocked_input_or_capacity',
                             reason=str(error),error_type=type(error).__name__)
            entries.append(entry)
    out.mkdir(parents=True,exist_ok=False)
    scope={'protocol':'biotracebench-grading-scope-1','run_manifest_identity':digest(manifest),
           'expected_conditions':expected_stages,'selected_conditions':list(stages),
           'case_ids':[t['case_id'] for t in tasks],'policy_identity':digest(policy),
           'judge_profile_identity':digest(profile),
           'grading_implementation_identity':grading_identity,'prompt_identity':prompt_identity,
           'purpose':'Independent scores only; comparisons belong to biotracebench_analysis'}
    readiness=preparation_summary(entries)
    write(out/'preparation-status.json',readiness)
    write(out/'plan.json',{'protocol':PROTOCOL,'implementation':implementation(),'profile':profile,
          'preparation':readiness,
          'scoring_scope':scope,
          'output_control':control,
          'precision_policy':copy.deepcopy(PRECISION_POLICY),
          'budget':read(budget_path),'policy_identity':digest(policy),'policy_frozen':bool(policy.get('frozen')),
          'diagnostic_only':not policy.get('frozen'),'run_manifest_identity':digest(manifest),
          'input_roots':input_roots,'entries':entries,'packets':packets,'human_review':'external_not_recorded'})
    seal(out)
    return {'plan':str(out),**readiness,
            'model_calls':0,'human_review_required_for_completion':False}


def _checked_output_control(plan):
    control=output_control(plan['profile'])
    if plan.get('output_control')!=control:
        raise ValueError('Grading output-control identity changed; prepare a new plan')
    return control


def _budget(plan, control=None):
    if control is None:
        control=_checked_output_control(plan)
    b=plan['budget'];cap=b.get('max_requests')
    retry_limit(b)
    if type(cap) is not int or cap<1 or not b.get('price_source') or not b.get('price_verified_at'):
        raise ValueError('Supply explicit request cap and dated price basis before execution')
    total=positive(b.get('total_cny'),'total_cny');single=positive(b.get('per_request_cny'),'per_request_cny')
    input_rate=positive(b.get('max_input_cny_per_million'),'input rate')
    output_rate=positive(b.get('max_output_cny_per_million'),'output rate')
    reserve=(Decimal(control['input_token_upper_bound'])*input_rate+
             Decimal(control['reserved_output_tokens'])*output_rate)/1000000
    return cap,total,single,input_rate,output_rate,reserve


def _saved_progress(out, entries):
    """Retain the last published views and all known physical-request costs."""
    results, costs = {}, []
    by_id = {entry['id']:entry for entry in entries}
    for entry in entries:
        path = out/'tasks'/entry['id']/'marking.json'
        if not path.exists():
            continue
        saved = read(path)
        prior = saved['entry']
        for key in ('id', 'case_id', 'condition', 'score_binding'):
            if prior.get(key) != entry.get(key):
                raise ValueError('Saved marking belongs to different grading inputs')
        result = saved['result']
        if result is not None:
            if result.get('score_binding') != entry.get('score_binding'):
                raise ValueError('Saved score belongs to different grading inputs')
            results[entry['id']] = result
        entry.update(prior)
    ledger = out/'costs.json'
    if ledger.exists():
        saved = read(ledger)
        costs = saved['requests']
        if (not isinstance(costs, list) or any(not isinstance(c, dict) for c in costs)
                or len({(c.get('output'),c.get('attempt')) for c in costs}) != len(costs)
                or any(c.get('output') not in by_id for c in costs)):
            raise ValueError('Saved cost ledger has unknown or duplicate requests')
        amounts = [Decimal(c['upper_cny']) for c in costs]
        if any(not amount.is_finite() or amount < 0 for amount in amounts):
            raise ValueError('Saved cost ledger has invalid amounts')
        if sum(amounts, Decimal(0)) != Decimal(saved['total_upper_cny']):
            raise ValueError('Saved cost ledger total changed')
    return results, costs


def _bind_result(result, plan, entry, **details):
    result.update(policy_frozen=plan['policy_frozen'],diagnostic_only=plan['diagnostic_only'],
        policy_identity=plan['policy_identity'],precision_policy=copy.deepcopy(plan['precision_policy']),
        precision_policy_identity=entry['score_binding']['precision_policy_identity'],
        score_binding=entry['score_binding'],**details)
    return result


def _publish_local(out, plan, entry, packet, results):
    from . import efe_protocol
    previous=results.get(entry['id'])
    result=_bind_result(copy.deepcopy(packet['local_result']),plan,entry,
        grading_model=None,request_identity=None,attempt=None)
    if previous is not None and previous != result:
        raise ValueError('Saved local score differs from the sealed grading plan')
    results[entry['id']]=result
    entry.update(status='automatic_scoring_completed',unresolved_items=result['unresolved_items'])
    extra={'protocol_bundle':efe_protocol.bundle(packet,result)} if packet.get('alignment_definition') else {}
    task_report(out/'tasks'/entry['id'],entry,result,**extra)
    if previous is None:
        event(out,'task_scored_locally',output=entry['id'],reason=result['score_basis'],model_calls=0)


def execute(plan_folder, out, *, offline=False, backend=None):
    from . import efe_protocol
    plan_folder=Path(plan_folder);out=Path(out)
    identity=verify(plan_folder);plan=read(plan_folder/'plan.json')
    if plan.get('protocol')!=PROTOCOL or plan.get('implementation')!=implementation():
        raise ValueError('Grading protocol/implementation/runtime changed; use a new plan')
    readiness=preparation_summary(plan['entries'])
    if readiness!=plan.get('preparation'):
        raise ValueError('Preparation summary differs from the frozen entries')
    needs_model=any(p['request'] is not None for p in plan['packets'])
    control=_checked_output_control(plan) if needs_model else None
    roots=[plan_folder.resolve(),Path(__file__).resolve().parents[2],*[Path(p) for p in plan['input_roots']]]
    if any(out.resolve().is_relative_to(p) for p in roots):raise ValueError('Run outside source, plan and immutable inputs')
    out.mkdir(parents=True,exist_ok=True)
    if (out/'receipt.json').exists():
        verify(out)
        if read(out/'plan-identity.json')!=identity:raise ValueError('Run belongs to another plan')
        return read(out/'status.json')  # Completed run: read-only, never submit again.
    with (out/'grading.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        verify_events(out)
        if (out/'plan-identity.json').exists() and read(out/'plan-identity.json')!=identity:
            raise ValueError('Run belongs to another plan')
        write(out/'plan-identity.json',identity)
        scope_path=out/'scoring-scope.json'
        if scope_path.exists() and read(scope_path)!=plan['scoring_scope']:
            raise ValueError('Grading scope changed')
        write(scope_path,plan['scoring_scope'])
        write(out/'preparation-status.json',readiness)
        entries=copy.deepcopy(plan['entries']);by_id={e['id']:e for e in entries}
        results,costs = _saved_progress(out, entries)
        spent = sum((Decimal(c['upper_cny']) for c in costs), Decimal(0))
        published=set(results)|{e['id'] for e in entries if e['status']=='failed_grading_response'}
        for entry in entries:
            if not (out/'tasks'/entry['id']/'marking.json').exists():
                task_report(out/'tasks'/entry['id'],entry)
        if not (out/'status.json').exists():
            overview(out,entries,results,plan['policy_frozen'])
        if not readiness['can_start_grading']:
            state=overview(out,entries,results,plan['policy_frozen'])
            event(out,'grading_not_started',status=state['status'],preparation=readiness,
                  model_calls=0,automatic_retry=False)
            verify_events(out)
            seal(out)
            return state
        for packet in plan['packets']:
            if packet.get('local_result') is not None:
                _publish_local(out,plan,by_id[packet['id']],packet,results)
        if needs_model:
            try:
                cap,total,single,input_rate,output_rate,reserve=_budget(plan,control)
                transport=backend or Backend(plan['profile'])
                if transport.describe().profile!=plan['profile']:
                    raise ValueError('Grader backend differs from the frozen profile')
            except (OSError,ValueError,RuntimeError) as error:
                state=overview(out,entries,results,plan['policy_frozen'])
                state.update(status='paused',reason=str(error),automatic_retry=False)
                write(out/'status.json',state)
                event(out,'grading_configuration_error',reason=str(error),model_calls=0)
                raise
        attempts=(GradingAttempts(out,transport,costs,cap,single,total,reserve,control,
                                 retry_limit(plan['budget'])) if needs_model else None)

        def pause(entry, status, reason, **details):
            # A replay failure must not erase an already published correction.
            if entry['id'] not in published:
                entry.update(status=status,reason=reason,**details)
                task_report(out/'tasks'/entry['id'],entry)
            state=overview(out,entries,results,plan['policy_frozen'])
            state.update(status='paused',automatic_retry=False,reason=reason,
                pause={'output':entry['id'],'status':status,'reason':reason,
                       'saved_marking_preserved':entry['id'] in published,**details})
            write(out/'status.json',state)

        for packet in plan['packets']:
            entry=by_id[packet['id']];attempt=out/'attempts'/packet['id']
            request=packet['request']
            if packet.get('local_result') is not None:
                continue
            failure=None
            try:
                attempt,response=attempts.obtain(packet,offline=offline)
            except ArchiveConflict as error:
                attempt=attempts.failure.attempt if attempts.failure else attempt
                check=assessment_path(out,attempts.key(attempt))
                archive=read(check) if check.exists() else error.assessment
                entry['archive_integrity']=archive
                if entry['id'] not in published:
                    entry.update(status='blocked_archive_conflict',reason=str(error),
                                 error_type=type(error).__name__)
                    task_report(out/'tasks'/entry['id'],entry)
                # Published scores and incurred costs remain intact; never create zero scores.
                event(out,'archive_conflict',output=entry['id'],attempt=attempts.key(attempt),
                      reason=str(error),saved_marking_preserved=entry['id'] in published,
                      automatic_retry=False)
                attempts.save_state()
                overview(out,entries,results,plan['policy_frozen'])
                continue
            except Exception as error:
                context=attempts.failure
                attempt=context.attempt if context else attempt
                response=context.response if context else None
                check=assessment_path(out,attempts.key(attempt))
                if check.exists():entry['archive_integrity']=read(check)
                if response is None:
                    send_state=context.dispatch_state if context else None
                    if send_state is None and (attempt/dispatch.PREPARED).exists():
                        send_state='not_sent' if dispatch.state(attempt)=='not_sent' else 'unknown'
                    attempts.save_state()
                    pause(entry,'paused_before_send' if send_state=='not_sent' else 'paused_request_or_budget',
                          str(error),error_type=type(error).__name__,dispatch_state=send_state)
                    event(out,'paused',output=entry['id'],reason=str(error),automatic_retry=False)
                    raise
                failure=error
            check=assessment_path(out,attempts.key(attempt))
            archive=read(check) if check.exists() else {'status':'unverified',
                'reasons':['Transport provenance assessment is unavailable']}
            entry['archive_integrity']=archive
            entry['dispatch_state']='response_saved'
            write(attempt/'grading-response.json',response.as_dict())
            raw_text=out/'tasks'/entry['id']/'raw-grading.txt'
            raw_text.write_text(response.text,encoding='utf-8')
            details=usage_breakdown(response.usage,response.raw_usage)
            write(attempt/'usage-breakdown.json',details)
            ni,no=response.usage.get('input_tokens'),response.usage.get('output_tokens')
            if type(ni) is not int or type(no) is not int or ni<0 or no<0:
                pause(entry,'paused_unknown_usage','Usage missing; cost remains unknown')
                write(out/'unknown-cost.json',{'output':entry['id'],'reserved_upper_cny':str(reserve),
                      'recorded_total_upper_cny':str(spent),'output_control':control,
                      'usage_breakdown':details,'billed_actual':None,'exact_cny':None,'consumption':'unknown'})
                event(out,'paused_unknown_usage',output=entry['id'],reserved_upper_cny=str(reserve),
                      automatic_retry=False)
                raise ValueError('Grading usage missing; do not assume zero cost')
            upper=(Decimal(ni)*input_rate+Decimal(no)*output_rate)/1000000
            cost={'output':entry['id'],'attempt':attempts.key(attempt),
                 'actual_model':response.actual_model,'usage':response.usage,
                 'raw_usage':response.raw_usage,'usage_breakdown':details,'output_control':control,
                 'reserved_upper_cny':str(reserve),'billed_actual':None,'exact_cny':None,'upper_cny':str(upper),
                 'elapsed_seconds':response.elapsed_seconds,'request_id':response.request_id}
            prior_cost=next((c for c in costs if c['output']==entry['id'] and
                            c.get('attempt','attempts/'+c['output'])==attempts.key(attempt)),None)
            if prior_cost is not None and prior_cost!=cost:
                pause(entry,'paused_cost_record_changed','Recovered response differs from the saved cost record')
                raise ValueError('Recovered response differs from the saved cost record')
            if prior_cost is None:
                costs.append(cost)
                spent+=upper
            write(out/'costs.json',{'purpose':'whole_task_grading','currency':'CNY','requests':costs,
                  'total_upper_cny':str(spent),'billed_actual':None,'exact_cny':None,'price_basis':plan['budget']})
            attempts.save_state()
            if ni>control['input_token_upper_bound'] or no>control['reserved_output_tokens']:
                pause(entry,'paused_usage_exceeded_token_bounds','Recorded usage exceeds declared token bound or total-output cap plus provider margin')
                event(out,'paused_token_bounds',output=entry['id'],usage_breakdown=details,
                      output_control=control,automatic_retry=False)
                raise ValueError('Usage exceeded grading token bounds; original response and cost retained')
            if upper>reserve or upper>single or spent+attempts.unknown_upper()>total:
                pause(entry,'paused_usage_exceeded_budget','Recorded usage exceeds reservation')
                event(out,'paused_usage_budget',output=entry['id'],upper_cny=str(upper),
                      automatic_retry=False)
                raise ValueError('Usage exceeded grading budget; stop for review')
            if plan['profile']['provider']=='deepseek' and response.actual_model!=plan['profile']['model']:
                pause(entry,'paused_model_identity','DeepSeek grader response model differs from the declared model')
                raise ValueError('DeepSeek grader model identity mismatch; original response and cost retained')
            try:
                if failure:raise ValueError('API returned a rejected, truncated or incomplete grading response')
                reply=strict_json(response.text)
                result=(efe_protocol.mark(packet['inventory'],reply,packet['alignment_definition'],packet['sources'])
                        if packet.get('alignment_definition') else mark_all(packet['inventory'],reply))
                if result.get('score_basis')=='qwen_machine_marking':
                    result['score_basis']=plan['profile']['provider']+'_machine_marking'
                result['judge']={'provider':plan['profile']['provider'],'requested_model':plan['profile']['model'],
                    'actual_model':response.actual_model,'request_id':response.request_id}
                _bind_result(result,plan,entry,grading_model=response.actual_model,
                    attempt=attempts.key(attempt),archive_integrity=archive,request_identity=digest(request))
                validate_decisions(packet,result)
                results[entry['id']]=result
                entry.update(status='automatic_scoring_completed',unresolved_items=result['unresolved_items'])
                entry.pop('reason',None);entry.pop('error_type',None)
                event(out,'task_graded',output=entry['id'],unresolved_items=result['unresolved_items'])
            except (ValueError,TypeError,KeyError) as error:
                entry.update(status='failed_grading_response',reason=str(error),error_type=type(error).__name__)
                event(out,'invalid_grading_retained',output=entry['id'],reason=entry['reason'],automatic_retry=False)
            saved_result=results.get(entry['id'])
            extra=({'protocol_bundle':efe_protocol.bundle(packet,saved_result)}
                   if saved_result and packet.get('alignment_definition') else {})
            task_report(out/'tasks'/entry['id'],entry,saved_result,**extra)
            overview(out,entries,results,plan['policy_frozen'])
        state=overview(out,entries,results,plan['policy_frozen'])
        if not needs_model:
            write(out/'costs.json',{'purpose':'whole_task_grading','currency':'CNY','requests':[],
                'total_upper_cny':'0','billed_actual':None,'exact_cny':'0','price_basis':plan['budget']})
        write(out/'completion-audit.json',{'protocol':PROTOCOL,'plan_identity':identity,
              'implementation':implementation(),
              'automatic_workflow_finished':state['automatic_workflow_finished'],
              'all_selected_outputs_graded':state['all_selected_outputs_graded'],
              'human_review_required':False,'human_review_performed':False,
              'automatic_retry':False,'generated_requests':attempts.count() if attempts else 0,'total_upper_cny':str(spent),
              'unknown_reserved_upper_cny':str(attempts.unknown_upper()) if attempts else '0',
              'unknown_network_reserved_upper_cny':str(sum((Decimal(r['reserve_upper_cny'])
                    for r in (attempts.unknown() if attempts else []) if r['reason']=='transport_interrupted'),Decimal(0))),
              'unknown_archive_reserved_upper_cny':str(sum((Decimal(r['reserve_upper_cny'])
                    for r in (attempts.unknown() if attempts else []) if r['reason']=='archive_conflict'),Decimal(0))),
              'budget_committed_upper_cny':str(spent+(attempts.unknown_upper() if attempts else Decimal(0))),
              'max_network_retries_per_output':retry_limit(plan['budget']),
              'output_control':plan['output_control'],'workflow_scope':dict(WORKFLOW_SCOPE)})
        event(out,'automatic_grading_finished' if state['automatic_workflow_finished'] else
              'grading_incomplete',status=state['status'])
        verify_events(out)
        seal(out)
        return state
