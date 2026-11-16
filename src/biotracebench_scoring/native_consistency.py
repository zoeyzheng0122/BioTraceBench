"""Inspect exact repeated contexts in accepted native Codex judgments.

This conservative inspector compares the entire scientific submission under an
already frozen native record mapping. It does not establish scientific identity,
infer semantic equivalence, adjudicate a contradiction, or modify any judgment.
Generation routes, human labels, old marks and model identities are not inputs.
"""
import copy
from collections import defaultdict
from pathlib import Path

from model_conversation.archive import digest, encoded, exact_json, sha
from . import native_codex as native


FORMAT = 'biotracebench-native-consistency-inspection-2'
SCOPE = 'exact_full_scientific_submission_under_frozen_native_mapping'


def _read(path, fingerprints):
    path = Path(path).resolve()
    before = sha(path)
    value = exact_json(path.read_text(encoding='utf-8'))
    if sha(path) != before:
        raise ValueError('Native consistency input changed during inspection')
    fingerprints[str(path)] = before
    return value


def _coordinate(row):
    return {'table': row['table'], 'row_index': row['row_index']}


def _complete_reply(attempt, attempts):
    reply = copy.deepcopy(attempt['reply'])
    if attempt['scope'] == 'fields':
        mapping = native._mapping_for(attempts, attempt['phase'])
        if mapping is None:
            raise ValueError('Accepted native field phase has no frozen record mapping')
        reply['records'] = copy.deepcopy(mapping)
    return reply


def _selected(attempts, require_review, phase):
    first = native._valid_complete(attempts, 'first')
    review = native._valid_complete(attempts, 'review')
    if phase == 'first':
        candidates = first
    elif phase == 'review':
        candidates = review
    else:
        candidates = review or (first if not require_review else [])
    if not candidates:
        raise ValueError('Native consistency requires an accepted complete ' + phase + ' judgment')
    chosen = candidates[-1]
    score = chosen.get('score')
    if not native._score_complete(score) or score.get('unresolved_items') != 0:
        raise ValueError('Unresolved native judgments cannot enter final consistency inspection')
    for item in score.get('field_items', []):
        if (item.get('verdict') not in {'correct', 'incorrect', 'missing', 'extra', 'not_scored'}
                or not isinstance(item.get('predicted'), bool) or not isinstance(item.get('gold'), bool)
                or item['gold'] and not isinstance(item.get('correct'), bool)):
            raise ValueError('Invalid or unresolved native logical field state')
    if any(a.get('verdict') not in {'correct', 'incorrect', 'missing'}
           for a in score.get('assertion_items', [])):
        raise ValueError('Invalid or unresolved native assertion state')
    return chosen


def _normalized(inv, records, dictionary, links, input_identity):
    """Normalize IDs only where the native correspondence proves the target.

    Text and numerical lexemes are retained. A dictionary-declared foreign key
    is replaced only when its actual target identifier is unique and that target
    has a frozen reference correspondence. Ambiguous/unmatched targets retain a
    job binding, preventing unjustified cross-job equivalence. Unmatched records
    retain identifiers; no row-order pairing or graph-isomorphism guess is made.
    """
    rows = {r['id']: r for r in inv['rows']}
    cells = {c['id']: c for c in inv['cells']}
    by_row = {rid: {c['field']: c for c in inv['cells'] if c['row'] == rid} for rid in rows}
    mapped = {r['prediction_row']: r['reference_row'] for r in records
              if r['prediction_row'] is not None and r['reference_row'] is not None}
    identities = defaultdict(list)
    for rid, row in rows.items():
        identifier = dictionary.get(row['table'], {}).get('identifier')
        c = by_row[rid].get(identifier)
        if c and c['present']:
            value = exact_json(c['value_json'])
            if isinstance(value, str):
                identities[row['side'], row['table'], value].append(rid)

    def owner(rid):
        r = rows[rid]
        if r['side'] == 'reference':
            return {'reference': _coordinate(r)}
        if rid in mapped:
            return {'reference': _coordinate(rows[mapped[rid]])}
        # Opaque pointers/order are not identities for surplus objects. Keeping
        # the complete literal row is conservative when surplus identity varies.
        return {'unmatched': {'table': r['table'], 'fields': {
            f: {'present': c['present'], 'role': c['role'], 'value_json': c['value_json']}
            for f, c in sorted(by_row[rid].items())}}}

    def foreign(value, side, target):
        if isinstance(value, list):
            return [foreign(v, side, target) for v in value]
        matches = identities.get((side, target, value), []) if isinstance(value, str) else []
        if len(matches) == 1 and (side == 'reference' or matches[0] in mapped):
            return owner(matches[0])
        return {'unbound_foreign_key': value, 'input_binding': input_identity}

    def cell_value(cell):
        spec = dictionary.get(cell['table'], {})
        target = spec.get('references', {}).get(cell['field'])
        if target is None:
            return {'value_json': cell['value_json']}
        value = foreign(exact_json(cell['value_json']), cell['side'], target)
        field = next((f for f in spec.get('fields', []) if f['key'] == cell['field']), {})
        if isinstance(value, list) and field.get('type') == 'ids':
            value = sorted(value, key=digest)
        return {'declared_reference': target, 'value': value}

    def scientific_row(rid):
        row = rows[rid]
        return {'owner': owner(rid), 'table': row['table'], 'fields': {
            f: {'role': c['role'], 'present': c['present'], 'nonempty': c['nonempty'], **cell_value(c)}
            for f, c in sorted(by_row[rid].items())
            if c['role'] in {'scientific', 'unclassified'}}}

    normalized_links = []
    for link in links:
        if rows[link['from_row']]['side'] != 'prediction':
            continue
        evidence = {}
        for key in ('from_evidence', 'to_evidence'):
            ev = link[key]; c = cells[ev['cell']]
            evidence[key] = {'owner': owner(c['row']), 'field': c['field'], 'path': ev['path']}
            if link['kind'] == 'explicit':
                evidence[key]['quote'] = ev['quote']
        normalized_links.append({'from': owner(link['from_row']), 'to': owner(link['to_row']),
                                 'kind': link['kind'], **evidence})
    return {'prediction': sorted([scientific_row(rid) for rid, r in rows.items()
                                  if r['side'] == 'prediction'], key=digest),
            'reference': sorted([scientific_row(rid) for rid, r in rows.items()
                                 if r['side'] == 'reference'], key=digest),
            'missing_reference_objects': sorted([_coordinate(rows[r['reference_row']]) for r in records
                                                 if r['prediction_row'] is None], key=digest),
            'explicit_prediction_links': sorted(normalized_links, key=digest),
            'diagnostics': copy.deepcopy(inv['diagnostics'])}


def _origin(root, job, frozen, phase, fingerprints, adjudications=None):
    packet_path = root / 'judge-inputs' / 'jobs' / job / 'packet.json'
    packet = _read(packet_path, fingerprints)
    context_path = root / 'judge-inputs' / 'tasks' / packet['task_id'] / 'context.json'
    context = _read(context_path, fingerprints)
    for artifact in context.get('source_artifacts', []):
        path = Path(artifact['path']).resolve()
        if sha(path) != artifact['sha256']:
            raise ValueError('Native source artifact changed')
        fingerprints[str(path)] = artifact['sha256']
    before = sorted((root / 'imports' / job).glob('*.json'))
    for path in before:
        _read(path, fingerprints)
    attempts = native._recheck_attempts(root, job, packet, context, frozen)
    if before != sorted((root / 'imports' / job).glob('*.json')):
        raise ValueError('Native imports changed during consistency inspection')
    if packet['local_terminal']:
        if attempts:
            raise ValueError('Local terminal input has native scientific imports')
        return {'job_id': job, 'local_terminal': True}, before
    chosen = _selected(attempts, frozen['require_review'], phase)
    complete = _complete_reply(chosen, attempts)
    if adjudications is not None and (Path(adjudications) / 'adjudications' / job).exists():
        from .native_adjudication import _history
        _, _, _, _, _, history = _history(root, job, adjudications)
        if history:
            for path, item in history:
                _read(path, fingerprints)
            chosen = {**history[-1][1], 'phase': 'source_adjudication'}
            complete = copy.deepcopy(chosen['reply'])
    normalized = _normalized(packet['inventory'], complete['records'], context['dictionary'],
                             native._bound_policy(packet['inventory'], context['task_policy'])['links']
                             + complete.get('links', []),
                             packet['input_identity'])
    return {'job_id': job, 'task_id': packet['task_id'], 'local_terminal': False,
            'phase': chosen['phase'], 'selected_import_identity': chosen['identity'],
            'input_identity': packet['input_identity'], 'score': chosen['score'],
            'reply': complete, 'normalized': normalized,
            'context_identity': packet['context_identity'],
            'source_policy_identity': digest({key: context.get(key) for key in (
                'task_definition', 'dictionary', 'task_policy', 'sources', 'numerical_rules',
                'source_scope', 'source_artifacts')})}, before


def _index_root(index):
    positions = index.get('position_results')
    if not isinstance(positions, list) or not positions:
        raise ValueError('Native campaign index has no position results')
    roots = {Path(p['packet_path']).resolve().parents[3] for p in positions}
    if len(roots) != 1:
        raise ValueError('Native campaign index spans different plans')
    return roots.pop()


def _validate_index(index, root, frozen, fingerprints):
    if (index.get('protocol') != native.PROTOCOL or index.get('plan_identity') != frozen['identity']
            or index.get('status') != 'completed'):
        raise ValueError('Consistency requires a completed exact native replay index')
    results = {}
    for position in index['position_results']:
        job = position['job_id']
        if job not in frozen['jobs']:
            raise ValueError('Replay index contains an unknown native job')
        result = _read(position['result_path'], fingerprints)
        expected_packet = root / 'judge-inputs' / 'jobs' / job / 'packet.json'
        if (Path(position['packet_path']).resolve() != expected_packet.resolve()
                or result.get('job_id') != job or result.get('plan_identity') != frozen['identity']
                or result.get('input_identity') != position.get('input_identity')
                or result.get('status') != position.get('status')
                or digest(result.get('score')) != digest(position.get('score'))):
            raise ValueError('Native replay position and result bindings differ')
        if job in results and digest(result) != digest(results[job]):
            raise ValueError('Replay positions disagree on their shared job result')
        results[job] = result
    if set(results) != set(frozen['jobs']) or digest({'plan': frozen['identity'], 'jobs': results}) != index.get('snapshot_identity'):
        raise ValueError('Native replay snapshot coverage or identity mismatch')
    return results


def inspect(plan_or_index, out=None, *, index=None, phase='final', jobs=None,
            adjudications=None):
    """Return a read-only contradiction queue, optionally writing one new report.

    ``plan_or_index`` accepts a native plan directory, its ``plan.json``, or a
    replay ``campaign-index.json``. ``index=`` optionally binds a supplied plan
    to its completed replay snapshot. Direct plan inspection replays accepted
    imports without creating a snapshot or reading private generation routes.
    The default compares only the selected final phase. ``first`` and ``review``
    are explicit separate inspections; they never combine phase histories.
    """
    if phase not in {'final', 'first', 'review'}:
        raise ValueError('Native consistency phase must be final, first or review')
    if adjudications is not None and phase != 'final':
        raise ValueError('Source adjudications apply only to final consistency')
    fingerprints, index_value = {}, None
    source = Path(plan_or_index).resolve()
    if source.is_file() and source.name != 'plan.json':
        if index is not None:
            raise ValueError('Specify one native replay index')
        index_value = _read(source, fingerprints)
        root = _index_root(index_value)
    else:
        root = source.parent if source.is_file() else source
        if index is not None:
            index_value = _read(index, fingerprints)
            if _index_root(index_value) != root:
                raise ValueError('Native replay index belongs to another plan')
    original_plan = _read(root / 'plan.json', fingerprints)
    # Explicit jobs prevent _verify_plan from reading private generation routes.
    frozen = native._verify_plan(root, jobs=original_plan['jobs'])
    selected_jobs = frozen['jobs'] if jobs is None else list(jobs)
    if (not selected_jobs or len(set(selected_jobs)) != len(selected_jobs)
            or not set(selected_jobs) <= set(frozen['jobs'])):
        raise ValueError('Invalid explicit native consistency job subset')
    overlay_before = {job: sorted((Path(adjudications) / 'adjudications' / job).glob('*.json'))
                      for job in selected_jobs} if adjudications is not None else {}
    published = _validate_index(index_value, root, frozen, fingerprints) if index_value is not None else None
    grouped, contexts, origins, skipped, imports_before = defaultdict(list), {}, {}, [], {}
    decision_count = 0
    for job in selected_jobs:
        origin, paths = _origin(root, job, frozen, phase, fingerprints, adjudications)
        imports_before[job] = paths
        if origin['local_terminal']:
            skipped.append({'job_id': job, 'reason': 'Deterministic terminal zero has no native scientific judgment.'})
            continue
        if published is not None:
            final = _selected(native._attempts(root, job), frozen['require_review'], 'final')
            if (published[job].get('selected_import_identity') != final['identity']
                    or digest(published[job].get('score')) != digest(final['score'])):
                raise ValueError('Published native result differs from accepted replayed final judgment')
        science_context = {'scope': SCOPE, 'source_policy_identity': origin['source_policy_identity'],
                       'phase': 'effective_final' if phase == 'final' else origin['phase'],
                       'submission': origin['normalized']}
        context_id = digest(science_context)
        contexts[context_id] = science_context
        origins[job] = {key: origin[key] for key in ('job_id', 'task_id', 'phase', 'selected_import_identity',
                       'input_identity', 'context_identity', 'source_policy_identity')}
        origins[job]['scientific_context_identity'] = context_id
        score, reply = origin['score'], origin['reply']
        for item in score['field_items']:
            assertions = sorted([{'assertion_id': a['assertion_id'], 'verdict': a['verdict']}
                                 for a in score['assertion_items'] if a['field_id'] == item['id']], key=digest)
            target = {'table': item['table'], 'row_index': item['row_index'], 'field': item['field']}
            state = {k: item[k] for k in ('verdict', 'predicted', 'gold', 'correct', 'applicable')}
            state['assertions'] = assertions
            integrity = next(m['integrity']['verdict'] for m in reply['fields'] if m['field_id'] == item['id'])
            state['integrity'] = integrity
            member = {'job_id': job, 'field_id': item['id'], 'target': target,
                      'phase': origin['phase'], 'decision': state, 'signature': digest(state),
                      'reason': item['reason'], 'evidence': copy.deepcopy(item['evidence'])}
            grouped[digest({'context': context_id, 'kind': 'logical_field', 'target': target})].append(
                (context_id, 'logical_field', member))
            decision_count += 1
        for item in score['record_items']:
            if item['reference_row'] is None:
                continue
            target = {'table': item['table'], 'row_index': item['row_index']}
            state = {k: item[k] for k in ('verdict', 'correct', 'applicable', 'schema_missing_fields')}
            member = {'job_id': job, 'field_id': None, 'target': target, 'phase': origin['phase'],
                      'decision': state, 'signature': digest(state), 'evidence': []}
            grouped[digest({'context': context_id, 'kind': 'complete_record', 'target': target})].append(
                (context_id, 'complete_record', member))
    groups = []
    for key, members in sorted(grouped.items()):
        if len(members) < 2:
            continue
        signatures = {item[2]['signature'] for item in members}
        groups.append({'key': key, 'kind': members[0][1], 'context_identity': members[0][0],
                       'members': [item[2] for item in members], 'distinct_decisions': len(signatures),
                       'conflict': len(signatures) > 1})
    for job, paths in imports_before.items():
        if paths != sorted((root / 'imports' / job).glob('*.json')):
            raise ValueError('Native import history changed before report publication')
    for job, paths in overlay_before.items():
        if paths != sorted((Path(adjudications) / 'adjudications' / job).glob('*.json')):
            raise ValueError('Source adjudication history changed before report publication')
    if any(sha(path) != expected for path, expected in fingerprints.items()):
        raise ValueError('Native inspection input changed before report publication')
    used = {g['context_identity'] for g in groups}
    report = {'format': FORMAT, 'scope': SCOPE, 'phase': phase, 'plan_identity': frozen['identity'],
              'selected_jobs': len(selected_jobs), 'total_plan_jobs': len(frozen['jobs']),
              'coverage': 'full_plan' if set(selected_jobs) == set(frozen['jobs']) else 'explicit_subset',
              'source_adjudications_applied': adjudications is not None,
              'inspected_jobs': len(origins), 'inspected_field_decisions': decision_count,
              'repeated_context_groups': len(groups), 'conflict_groups': sum(g['conflict'] for g in groups),
              'groups': groups, 'conflicts': [g for g in groups if g['conflict']],
              'contexts': {key: value for key, value in contexts.items() if key in used},
              'origins': origins, 'skipped': skipped, 'source_sha256': fingerprints,
              'action': 'Source-review queue only. No judgment, correspondence, answer or score was changed.',
              'limitations': ['Exact whole-submission comparison is conservative: differences outside a field prevent grouping.',
                              'Record correspondence is an input from native judgment, not inferred or adjudicated by this inspector.',
                              'Unmatched objects and ambiguous foreign keys are retained conservatively; no fuzzy equivalence is inferred.']}
    if out is not None:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(encoded(report) + b'\n')
    return report
