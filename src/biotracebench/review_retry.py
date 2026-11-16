"""Prepare an independent paired review round while retaining prior execution."""
import copy
import fcntl
import os
from pathlib import Path
import shutil
import tempfile
from decimal import Decimal

from model_conversation import Conversation
from model_conversation.archive import read_exact
from .common import Stop, digest, read, sha, verify, write
from .conditions import stages, CANONICAL
from .cost import upper
from .limits import MODEL_KEYS, STAGE_KEYS, apply_limits, effective, extensions, higher_output_limit
from . import prompts


def inherited_costs(folder, manifest):
    rows = read(Path(folder)/'inherited-costs.json')
    if digest(rows) != manifest['review_retry']['inherited_costs_identity']:
        raise Stop('tampered', 'Inherited execution costs changed')
    return rows


def initial_answer(folder, manifest, case):
    origin = manifest['review_retry']['initials'][case]
    final = Path(folder)/case/'i0'/'final'
    verify(final, origin['final_identity'])
    snapshot = read_exact(final/'snapshot.json')
    if digest(snapshot['messages']) != origin['history_identity']:
        raise Stop('tampered', 'Reused initial history changed')
    task = next(t for t in manifest['tasks'] if t['case_id']==case)
    if (snapshot['branch']['case_id'] != case or snapshot['branch']['stage'] != 'i0' or
            snapshot['branch']['material_identity'] != task['material_identity']):
        raise Stop('tampered', 'Reused initial answer belongs to different task inputs')
    return final


def _source_manifest(folder):
    manifest = read(folder/'manifest.json')
    if digest({k:v for k,v in manifest.items() if k!='identity'}) != manifest.get('identity'):
        raise Stop('tampered', 'Source run manifest changed')
    if stages(manifest) != CANONICAL or manifest.get('execution_protocol') != prompts.EXECUTION_PROTOCOL:
        raise ValueError('Review retry requires the current initial/review conversation protocol')
    expected = {'i0': digest(prompts.INITIAL), 'gsr': digest(prompts.GSR), 'ssr': digest(prompts.SSR),
                'execution': digest([prompts.EXECUTION_PROTOCOL, prompts.CONTINUE_OUTPUT])}
    if manifest.get('prompt_hashes') != expected:
        raise ValueError('Source prompts differ; retain this source at its original version')
    return manifest


def prepare(run, cases, changes, output):
    """Prepare only. The regular run --execute command dispatches the new round."""
    source, target = Path(run).resolve(), Path(output).resolve()
    manifest = _source_manifest(source)
    provider = Conversation(manifest['model']).profile['provider']
    lock_path = Path(tempfile.gettempdir())/('biotracebench-'+provider+'-'+str(os.getuid())+'.lock')
    with lock_path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop('account_busy', 'A worker is using this account') from None
        return _prepare(source, target, manifest, cases, changes)


def _prepare(source, target, manifest, cases, changes):
    from .runner import freeze, ledger, validate_manifest

    source_tree = Path(__file__).resolve().parents[2]
    roots = [source, source_tree, Path(manifest['dataset']['root']).resolve(),
             *[Path(t['prepared']).resolve() for t in manifest['tasks']]]
    if target.exists() or any(target.is_relative_to(p) or p.is_relative_to(target) for p in roots):
        raise ValueError('Use a new review directory outside source and input directories')
    known = {t['case_id']:t for t in manifest['tasks']}
    if not cases or len(cases)!=len(set(cases)) or not set(cases)<=set(known):
        raise ValueError('Select unique cases from the source run')
    if not isinstance(changes, dict) or set(changes)-MODEL_KEYS-STAGE_KEYS:
        raise ValueError('Review limits must contain only supported technical-limit increases')
    history = extensions(manifest, source)
    costs = ledger(source, manifest)
    if costs['unknown_budget_calls']:
        raise Stop('paused_unknown_cost', 'Resolve prior unknown consumption before preparing another round')

    draft = copy.deepcopy(manifest)
    for name in ('identity', 'implementation', 'runtime', 'condition_identity', 'task_set_identity', 'frozen_at', 'review_retry'):
        draft.pop(name, None)
    draft['state'] = 'draft'
    draft['tasks'] = [copy.deepcopy(t) for t in manifest['tasks'] if t['case_id'] in cases]
    views = [effective(manifest, history, case, stage) for case in cases for stage in ('gsr', 'ssr')]
    for name in MODEL_KEYS:
        draft['model'][name] = max(v['model'][name] for v in views)
    review_budget = copy.deepcopy(draft['budgets']['gsr'])
    for name in STAGE_KEYS:
        review_budget[name] = max(v['budgets'][s][name] for v in views for s in ('gsr','ssr'))
    draft['budgets']['gsr'] = copy.deepcopy(review_budget)
    draft['budgets']['ssr'] = copy.deepcopy(review_budget)
    changes = dict(changes)
    if 'context_tokens' in changes:
        if type(changes['context_tokens']) is not int or changes['context_tokens'] <= draft['model']['context_tokens']:
            raise ValueError('Context limit must strictly increase')
        draft['model']['context_tokens'] = changes.pop('context_tokens')
    baseline = draft['model']['max_output_tokens']
    changes.setdefault('max_output_tokens', higher_output_limit(draft['model']))
    apply_limits(draft, changes)
    validate_manifest(draft, frozen=False)
    draft['output_limit_basis'] = {'baseline':baseline,'multiplier':2,'selected':draft['model']['max_output_tokens'],
        'ceiling':draft['model'].get('api_limits',{}).get('provider_max_output_tokens'),
        'source_kind':'user','source_reference':'Approved plan: double the prior review cap and restart both branches.'}

    initials, snapshots, checks = {}, {}, []
    reserved = Decimal(costs['known_budget_upper'])
    for case in cases:
        final = source/case/'i0'/'final'
        if manifest.get('review_retry'):
            initial_answer(source, manifest, case)
        stamp = verify(final)
        snapshot = read_exact(final/'snapshot.json')
        if (snapshot.get('status') not in {'completed','invalid_output'} or
                not snapshot.get('assessment',{}).get('final_response_received') or
                not snapshot.get('messages') or snapshot['messages'][-1].get('role')!='assistant'):
            raise ValueError('Retry requires a normally received initial answer and complete native history')
        if (snapshot['branch']['case_id'] != case or snapshot['branch']['stage'] != 'i0' or
                snapshot['branch']['material_identity'] != known[case]['material_identity'] or
                not manifest.get('review_retry') and snapshot['branch']['manifest_identity'] != manifest['identity']):
            raise Stop('tampered','Initial answer does not match the source task/run binding')
        initials[case] = {'source_run':str(source),'source_manifest_identity':manifest['identity'],
                          'final_identity':stamp,'history_identity':digest(snapshot['messages'])}
        snapshots[case] = final
        for stage, prompt in (('gsr',prompts.GSR), ('ssr',prompts.SSR)):
            config = {**draft['model'], 'execution_mode':'final'}
            if draft.get('final_output_policy') == 'json_schema_strict':
                from .output_contract import output_schema
                from .submission import PROTOCOL
                config['output_schema'] = output_schema(read(Path(known[case]['prepared'])/'schema.json'), stage, PROTOCOL)
            messages = copy.deepcopy(snapshot['messages']) + [{'role':'user','content':prompt}]
            Conversation(config).preflight(messages, [])
            estimator = config['estimator']
            input_bound = estimator['input_tokens'] if estimator['kind']=='fixed_upper_bound' else None
            output_bound = config.get('billable_output_token_upper',config['max_output_tokens'])
            if output_bound < config['max_output_tokens']:
                raise ValueError('Verified billable output bound must cover the increased output cap')
            amount = upper(input_bound or 0, output_bound, draft['tariff'])
            budget = draft['budgets'][stage]
            if (input_bound is not None and input_bound+config['max_output_tokens'] > config['context_tokens'] or
                    (input_bound or 0)+output_bound > budget['max_total_tokens']):
                raise Stop('paused_capacity','Review context or cumulative-token allowance is insufficient')
            if amount > Decimal(str(budget['max_cost'])) or (
                    budget.get('max_request_cost') is not None and amount > Decimal(str(budget['max_request_cost']))):
                raise Stop('paused_budget','Review reservation exceeds the unchanged monetary limit')
            reserved += amount
            checks.append({'case_id':case,'condition':stage,'request_bytes':'validated',
                'input_token_bound':input_bound,'token_check':'validated_bound' if input_bound is not None else 'required_before_send',
                'output_tokens':config['max_output_tokens'],'cost_reservation':str(amount),
                'cost_basis':'whole_request_bound' if input_bound is not None else 'output_only_minimum'})
    if reserved > Decimal(str(draft['max_total_cost'])):
        raise Stop('paused_budget','Prior attempts plus the new paired round exceed the unchanged experiment cost limit')

    inherited = []
    for row in costs['calls']:
        record = copy.deepcopy(row)
        record.update(imported=True, historical_round=row['stage']!='i0',
            origin_run=row.get('origin_run',str(source)),
            origin_manifest_identity=row.get('origin_manifest_identity',manifest['identity']),
            tariff_identity=row.get('tariff_identity',digest(manifest['tariff'])),
            tariff_basis=row.get('tariff_basis',manifest['tariff']))
        inherited.append(record)
    draft['review_retry'] = {'source_run':str(source),'source_manifest_identity':manifest['identity'],
        'initials':initials,'inherited_costs_identity':digest(inherited),'source_cost_identity':digest(costs),
        'round':manifest.get('review_retry',{}).get('round',0)+1,
        'selection_rule':'use both review outputs from this explicit round; retain earlier rounds'}
    draft['parameter_basis'].append({'source_kind':'user','source_reference':'Approved paired-review restart plan',
        'output_limit_basis':draft['output_limit_basis'],'inherited_costs_identity':digest(inherited)})
    target.mkdir(parents=True)
    write(target/'inherited-costs.json',inherited)
    write(target/'review-preflight.json',checks)
    write(target/'draft.json',draft)
    for case, final in snapshots.items():
        shutil.copytree(final,target/case/'i0'/'final')
    frozen = freeze(target/'draft.json',target/'manifest.json')
    for case in cases:
        initial_answer(target, frozen, case)
    return {'status':'review_round_prepared','manifest':str(target/'manifest.json'),'run':str(target),
            'cases':cases,'round':draft['review_retry']['round'],'model_calls':0,
            'max_output_tokens':draft['model']['max_output_tokens']}
