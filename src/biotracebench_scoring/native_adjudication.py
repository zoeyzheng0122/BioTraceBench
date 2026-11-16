"""Source adjudications appended after immutable native first/review phases.

The agent supplies every scientific judgment. This module checks provenance,
replays the existing counter, and exports separately identified judgment views.
It neither calls a model nor changes accepted imports or frozen task policies.
"""
import copy
from pathlib import Path

from model_conversation.archive import digest, encoded, exact_json, now, sha
from . import native_codex as native
from .native_consistency import _complete_reply, _selected

FORMAT = 'biotracebench-native-source-adjudication-1'


def _implementation(frozen):
    return {'native': frozen['implementation'], 'adjudication': sha(__file__),
            'consistency': sha(Path(__file__).with_name('native_consistency.py'))}


def _changes(before, after):
    result = {}
    for group, key in (('fields', lambda x: x['field_id']),
                       ('records', lambda x: 'p:' + x['prediction_row'] if x['prediction_row']
                        else 'g:' + x['reference_row'])):
        old = {key(x): x for x in before[group]}
        new = {key(x): x for x in after[group]}
        result[group] = [{'key': k, 'before': old.get(k), 'after': new.get(k)}
                         for k in sorted(set(old) | set(new)) if digest(old.get(k)) != digest(new.get(k))]
    return result


def _base(plan, job):
    root = Path(plan).resolve()
    frozen = native._verify_plan(root, [job])
    packet, context = native._inputs(root, job, frozen)
    if packet['local_terminal']:
        raise ValueError('Terminal zero has no scientific judgment to adjudicate')
    attempts = native._recheck_attempts(root, job, packet, context, frozen)
    selected = _selected(attempts, frozen['require_review'], 'final')
    return frozen, packet, context, selected, _complete_reply(selected, attempts)


def _evidence(context, evidence):
    """Require literal source support or a located observation of a frozen asset."""
    if not isinstance(evidence, list) or not evidence:
        raise ValueError('Source adjudication requires a nonempty evidence ledger')
    artifacts = {str(Path(a['path']).resolve()): a['sha256']
                 for a in context.get('source_artifacts', [])}
    sources = {s['id']: s for s in context.get('sources', [])}
    for path, expected in artifacts.items():
        if sha(path) != expected:
            raise ValueError('Adjudication source artifact changed')
        if Path(path).suffix == '.json':
            value = exact_json(Path(path).read_text(encoding='utf-8'))
            entries = value if isinstance(value, list) else value.get('sources', []) if isinstance(value, dict) else []
            for entry in entries:
                if isinstance(entry, dict) and {'id', 'text'} <= set(entry):
                    if entry['id'] in sources and sources[entry['id']]['text'] not in entry['text']:
                        raise ValueError('Conflicting source IDs in frozen evidence')
                    sources[entry['id']] = entry
    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError('Invalid source evidence entry')
        if 'source_id' in item:
            source = sources.get(item['source_id'])
            quote = item.get('quote')
            if source is None or not isinstance(quote, str) or not quote.strip() or quote not in source['text']:
                raise ValueError('Adjudication source quote is not in frozen evidence')
        elif 'artifact_path' in item:
            path = str(Path(item['artifact_path']).resolve())
            if (path not in artifacts or artifacts[path] != item.get('artifact_sha256') or
                    not all(isinstance(item.get(k), str) and item[k].strip()
                            for k in ('location', 'observation'))):
                raise ValueError('Adjudication observation is not bound to a located frozen asset')
        else:
            raise ValueError('Source evidence needs a source ID or frozen artifact')
    return copy.deepcopy(evidence)


def _history(plan, job, out):
    frozen, packet, context, base, reply = _base(plan, job)
    previous = base['identity']
    history = []
    for path in sorted((Path(out) / 'adjudications' / job).glob('*.json')):
        item = native._json(path)
        identity = item.pop('identity')
        if digest(item) != identity:
            raise ValueError('Source adjudication identity mismatch')
        item['identity'] = identity
        if (item.get('format') != FORMAT or item['previous'] != previous or
                item['plan_identity'] != frozen['identity'] or item['job_id'] != job or
                item['input_identity'] != packet['input_identity'] or
                item['base_import_identity'] != base['identity'] or
                item['implementation'] != _implementation(frozen)):
            raise ValueError('Source adjudication chain, implementation or input binding changed')
        native._actor(item['actor'])
        request = {k: item[k] for k in ('format', 'plan_identity', 'job_id', 'input_identity',
                   'base_import_identity', 'previous', 'reply', 'actor', 'reason', 'evidence',
                   'implementation')}
        if (digest(request) != item['request_identity'] or
                item['previous_reply_identity'] != digest(reply) or
                digest(item['changes']) != digest(_changes(reply, item['reply'])) or
                not isinstance(item['reason'], str) or not item['reason'].strip()):
            raise ValueError('Source adjudication request or preceding judgment changed')
        _evidence(context, item['evidence'])
        score = native._score(packet['inventory'], item['reply'], context['task_policy'])
        if not native._score_complete(score) or digest(score) != digest(item['score']):
            raise ValueError('Source adjudication does not replay exactly')
        previous, reply = identity, item['reply']
        history.append((path, item))
    return frozen, packet, context, base, reply, history


def adjudication_request(plan, job, out):
    """Return the current complete judgment for a source review, without routes."""
    frozen, packet, context, base, reply, history = _history(plan, job, out)
    return {'format': FORMAT, 'plan_identity': frozen['identity'], 'job_id': job,
            'input_identity': packet['input_identity'], 'packet': packet, 'context': context,
            'base_import_identity': base['identity'],
            'supersedes': history[-1][1]['identity'] if history else base['identity'],
            'reply': reply}


def adjudicate_native(plan, job, reply, actor, out, *, reason, evidence, supersedes):
    """Append one explicit source adjudication, retaining all previous phases."""
    out = Path(out).resolve()
    if out.is_relative_to(Path(plan).resolve()):
        raise ValueError('Keep source adjudications outside the immutable native plan')
    out.mkdir(parents=True, exist_ok=True)
    with native._lock(out):
        frozen, packet, context, base, current_reply, history = _history(plan, job, out)
        actor, reply = native._actor(actor), native._json(reply)
        evidence = _evidence(context, native._json(evidence))
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError('Source adjudication requires a scientific reason')
        request = {'format': FORMAT, 'plan_identity': frozen['identity'], 'job_id': job,
                   'input_identity': packet['input_identity'], 'base_import_identity': base['identity'],
                   'previous': supersedes, 'reply': reply, 'actor': actor,
                   'reason': reason, 'evidence': evidence,
                   'implementation': _implementation(frozen)}
        request_identity = digest(request)
        repeated = next((item for _, item in history if item['request_identity'] == request_identity), None)
        if repeated:
            return {'identity': repeated['identity'], 'job_id': job, 'status': 'accepted',
                    'score': repeated['score']}
        current = history[-1][1]['identity'] if history else base['identity']
        if supersedes != current:
            raise ValueError('Source adjudication supersedes a stale judgment')
        score = native._score(packet['inventory'], reply, context['task_policy'])
        if not native._score_complete(score):
            raise ValueError('Source adjudication has unresolved scientific items')
        item = {**request, 'request_identity': request_identity, 'time': now(), 'score': score,
                'previous_reply_identity': digest(current_reply),
                'changes': _changes(current_reply, reply)}
        item['identity'] = digest(item)
        path = out / 'adjudications' / job / (str(len(history) + 1).zfill(5) + '.json')
        native._write_once(path, item)
        return {'identity': item['identity'], 'job_id': job, 'status': 'accepted',
                'score': score, 'path': str(path)}


def export_view(plan, out, *, phase='final', adjudications=None, historical=None,
                audit=None, audit_provenance=None, require_complete=False):
    """Export first, reviewed, or source-adjudicated scores as explicit views."""
    if phase not in {'first', 'final'} or phase == 'first' and adjudications is not None:
        raise ValueError('First-pass exports cannot apply later source adjudications')
    exported = native.export_native(plan, Path(out) / 'base', historical=historical,
                                   audit=audit, audit_provenance=audit_provenance)
    data = native._json(exported['path'])
    frozen = native._verify_plan(plan)
    if adjudications is not None:
        unknown = {p.name for p in (Path(adjudications) / 'adjudications').glob('*')
                   if p.is_dir()} - set(frozen['jobs'])
        if unknown:
            raise ValueError('Unknown native job in source adjudications')
    routes = native._json(Path(plan) / 'private' / 'routes.json')
    by_identity = {(r['case'], r['model'], r['condition']): r['job_id'] for r in routes}
    replacement, selected = {}, {}
    for job in frozen['jobs']:
        packet, context = native._inputs(plan, job, frozen)
        if packet['local_terminal']:
            continue
        if phase == 'first':
            attempts = native._recheck_attempts(plan, job, packet, context, frozen)
            first = native._valid_complete(attempts, 'first')
            if first and native._score_complete(first[-1]['score']):
                item = first[-1]
                replacement[job] = item['score']
                selected[job] = {'phase': 'first', 'identity': item['identity']}
                for path in (Path(plan) / 'imports' / job).glob('*.json'):
                    data['source_sha256'][str(path.resolve())] = sha(path)
        elif adjudications is not None and (Path(adjudications) / 'adjudications' / job).exists():
            _, _, _, base, _, history = _history(plan, job, adjudications)
            if history:
                item = history[-1][1]
                replacement[job] = item['score']
                selected[job] = {'phase': 'source_adjudication', 'identity': item['identity'],
                                 'base_import_identity': base['identity']}
                for path, _ in history:
                    data['source_sha256'][str(path.resolve())] = sha(path)
    for row in data['positions']:
        key = tuple(row['identity'][k] for k in ('case', 'model', 'condition'))
        job = by_identity[key]
        if job in replacement:
            score = replacement[job]
            row['base_score'] = row['score']
            row.update(status='complete', score={k: score[k] for k in ('field', 'record')},
                       field_items=[[i['table'], i['row_index'], i['field'], i['correct']]
                                    for i in score['field_items'] if i['gold']],
                       record_items=[[i['table'], i['row_index'], i['correct']]
                                     for i in score['record_items']
                                     if i['reference_row'] and i.get('applicable', True)],
                       selected_judgment=selected[job])
        elif phase == 'first' and not native._json(row['packet_path'])['local_terminal']:
            row.update(status='awaiting_first_pass', score=None, field_items=[], record_items=[])
    if require_complete and any(r['status'] != 'complete' for r in data['positions']):
        raise ValueError('Judgment view has incomplete positions')
    data['judgment_view'] = ('first' if phase == 'first' else
                             'source_adjudicated' if adjudications is not None else 'reviewed')
    data['source_sha256'][str(Path(__file__).resolve())] = sha(__file__)
    data['source_sha256'][str(Path(exported['path']).resolve())] = sha(exported['path'])
    path = Path(out) / 'exports' / digest(data) / 'comparison-input.json'
    native._write_once(path, data)
    return {'path': str(path.resolve()), 'sha256': sha(path),
            'positions': len(data['positions']), 'judgment_view': data['judgment_view'],
            'validation_status': data['validation_status']}
