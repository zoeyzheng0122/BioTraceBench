"""Append-only technical-limit extensions; never change prompts, prices or money.

The original frozen manifest and physical requests remain immutable. Replay uses
limits in force at each archived request; only future requests use new limits.
"""
import copy
from pathlib import Path
from .common import Stop, digest, now, read, sha, verify, write

MODEL_KEYS = {'max_output_tokens', 'context_tokens', 'max_request_bytes'}
STAGE_KEYS = {'max_requests', 'max_total_tokens'}


def higher_output_limit(model, multiplier=2):
    """Propose a larger cap using the deployment's declared output ceiling."""
    current = model['max_output_tokens']
    ceiling = model.get('api_limits', {}).get('provider_max_output_tokens')
    if type(ceiling) is not int or ceiling <= 0:
        raise ValueError('Declare a verified api_limits.provider_max_output_tokens before increasing output limits')
    maximum = min(ceiling, model['context_tokens'] - 1)
    if model.get('estimator', {}).get('kind') == 'fixed_upper_bound':
        maximum = min(maximum, model['context_tokens'] - model['estimator']['input_tokens'])
    result = min(current * multiplier, maximum)
    if result <= current:
        raise ValueError('Output limit cannot increase within the declared provider/context bounds')
    return result


def extensions(manifest, folder):
    root = Path(folder)
    previous = manifest['identity']
    result = []
    for index, path in enumerate(sorted((root/'limit-extensions').glob('*.json')), 1):
        entry = read(path)
        body = {k:v for k,v in entry.items() if k != 'identity'}
        if (path.name != f'{index:04d}.json' or digest(body) != entry.get('identity') or
                entry.get('previous') != previous or entry.get('manifest_identity') != manifest['identity']):
            raise Stop('tampered', 'Limit extension chain changed')
        expected_stages = {f'{t["case_id"]}/{s}' for t in manifest['tasks'] for s in manifest['stages']}
        if set(entry['start_indices']) != expected_stages:
            raise Stop('tampered', 'Limit extension stage set changed')
        if 'targets' in entry and (not entry['targets'] or len(set(entry['targets'])) != len(entry['targets'])
                                  or not set(entry['targets']) <= expected_stages):
            raise Stop('tampered', 'Invalid targeted extension scope')
        for relative, identity in entry['anchors'].items():
            path = root/relative
            if not path.resolve().is_relative_to(root.resolve()):
                raise Stop('tampered', 'Limit extension anchor escaped run')
            verify(path, identity)
        for stage, count in entry['start_indices'].items():
            if type(count) is not int or count < 0:
                raise Stop('tampered', 'Invalid extension boundary')
            for i in range(count):
                if f'{stage}/calls/{i:05d}/completion' not in entry['anchors']:
                    raise Stop('tampered', 'Missing previous physical request anchor')
        result.append(entry)
        previous = entry['identity']
    return result


def apply_limits(value, changes):
    if not changes or set(changes) - MODEL_KEYS - STAGE_KEYS:
        raise ValueError('Only explicit technical-limit increases are allowed')
    for key, number in changes.items():
        if type(number) is not int or number < 1:
            raise ValueError('Technical limits must be positive integers')
        if key in MODEL_KEYS:
            if number <= value['model'][key]:
                raise ValueError('New model limit must strictly increase')
            value['model'][key] = number
        else:
            if any(number <= b[key] for b in value['budgets'].values()):
                raise ValueError('New stage limit must increase for every condition')
            for limits in value['budgets'].values():
                limits[key] = number
    if value['model']['max_output_tokens'] >= value['model']['context_tokens']:
        raise ValueError('Output reserve must fit context')
    ceiling = value['model'].get('api_limits', {}).get('provider_max_output_tokens')
    if ceiling is not None and value['model']['max_output_tokens'] > ceiling:
        raise ValueError('Output reserve exceeds the declared provider ceiling')


def effective(manifest, entries, case_id, stage, index=None):
    result = copy.deepcopy(manifest)
    for entry in entries:
        if (case_id+'/'+stage in entry.get('targets', entry['start_indices'])
                and (index is None or index >= entry['start_indices'][case_id+'/'+stage])):
            apply_limits(result, entry['changes'])
    return result


def extension_reason(manifest, root):
    """Verify a batch stop or the task-level stops in a completed deferred queue."""
    status = read(root / 'status.json')
    failure = status.get('failure')
    if failure:
        if failure.get('status') not in {'paused_budget', 'paused_capacity', 'paused_truncated'}:
            raise Stop('extension_not_applicable', 'Only a known technical-limit stop can be extended')
        return failure
    deferred = status.get('deferred')
    if (manifest.get('capacity_policy') != 'defer_and_continue'
            or status.get('queue_status') != 'finished_with_deferred_tasks'
            or not isinstance(deferred, list) or not deferred):
        raise Stop('extension_not_applicable', 'No verified technical-limit stop or deferred capacity task')
    queue_record = root / 'deferred-capacity.json'
    if not queue_record.is_file() or queue_record.is_symlink() or read(queue_record) != deferred:
        raise Stop('tampered', 'Deferred task list differs from the queue status')
    tasks = {task['case_id']: task for task in manifest['tasks']}
    seen = set()
    stages = manifest['stages']
    for item in deferred:
        if not isinstance(item, dict):
            raise Stop('tampered', 'Invalid deferred capacity task record')
        case, stage = item.get('case_id'), item.get('stage')
        if (case not in tasks or case in seen or stage not in stages
                or item.get('status') != 'paused_capacity'
                or item.get('material_identity') != tasks[case]['material_identity']):
            raise Stop('tampered', 'Invalid deferred capacity task identity')
        seen.add(case)
        capacity_record = root / case / stage / 'capacity.json'
        if not capacity_record.is_file() or capacity_record.is_symlink() or read(capacity_record) != item:
            raise Stop('tampered', 'Deferred capacity record changed')
        states = status.get('tasks', {}).get(case, {})
        index = stages.index(stage)
        if (any(states.get(s) not in {'completed', 'invalid_output'} for s in stages[:index])
                or states.get(stage) != 'paused_capacity'
                or any(states.get(s) != 'deferred_capacity' for s in stages[index + 1:])):
            raise Stop('extension_not_applicable', 'Deferred task has an inconsistent or nontechnical stop')
    for case in tasks.keys() - seen:
        if any(status.get('tasks', {}).get(case, {}).get(s) not in {'completed', 'invalid_output'} for s in stages):
            raise Stop('extension_not_applicable', 'Another task has an unresolved nontechnical stop')
    return {'status': 'paused_capacity', 'scope': 'deferred_tasks', 'tasks': deferred}


def extend_limits(manifest, folder, changes, targets=None):
    """Caller holds the same-account lock. No network/model invocation."""
    root = Path(folder)
    if read(root/'manifest.json') != manifest:
        raise Stop('tampered', 'Run is not bound to this manifest')
    failure = extension_reason(manifest, root)
    entries = extensions(manifest, root)
    expected = {f'{t["case_id"]}/{s}' for t in manifest['tasks'] for s in manifest['stages']}
    if targets is not None and (not targets or len(set(targets)) != len(targets) or not set(targets) <= expected):
        raise ValueError('Targets must identify unique task/condition pairs')
    selected = set(targets) if targets is not None else set(expected)
    for case in {t.split('/')[0] for t in selected if t.split('/')[1] in {'gsr', 'ssr'}}:
        selected.update({case+'/gsr', case+'/ssr'})
        if any((root/case/stage/'final').exists() or
               any((root/case/stage/'calls').glob('*/completion/request.json')) for stage in ('gsr', 'ssr')):
            raise Stop('review_restart_required', 'Review execution has started; use review-retry to rerun both branches with common limits')
    for target in sorted(selected):
        case, stage = target.split('/')
        latest = effective(manifest, entries, case, stage)
        apply_limits(latest, changes)
    anchors, starts = {}, {}
    for task in manifest['tasks']:
        for stage in manifest['stages']:
            prefix = f'{task["case_id"]}/{stage}'
            requests = sorted((root/prefix/'calls').glob('*/completion/request.json'))
            starts[prefix] = len(requests)
            for index, path in enumerate(requests):
                if path.parent.parent.name != f'{index:05d}':
                    raise Stop('tampered', 'Noncontiguous physical calls')
                attempt = path.parent
                identity = verify(attempt)
                if (attempt/'failure.json').exists() or read(attempt/'http.json')['status'] != 200:
                    raise Stop('paused_unknown', 'Cannot extend unknown execution or failed HTTP')
                anchors[str(attempt.relative_to(root))] = identity
    # Money, tariffs, task identities, prompts and model identity are inherited unchanged.
    entry = {'protocol':'biotracebench-limit-extension-1', 'manifest_identity':manifest['identity'],
             'previous':entries[-1]['identity'] if entries else manifest['identity'],
             'created_at':now(), 'changes':changes, 'start_indices':starts, 'anchors':anchors,
             'reason':failure, 'extra_model_recheck':False}
    if targets is not None:
        entry['targets'] = sorted(selected)
    entry['identity'] = digest(entry)
    path = root/'limit-extensions'/f'{len(entries)+1:04d}.json'
    if path.exists():
        raise Stop('attempt_reserved', 'Limit extension already exists')
    write(path, entry)
    return entry
