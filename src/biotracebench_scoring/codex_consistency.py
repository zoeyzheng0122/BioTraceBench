"""Inspect repeated scientific contexts in fresh accepted Codex judgments.

The report is a source-review queue. It never selects or applies a verdict.
Actual Codex phase origins remain separate from the compatibility Context wrapper.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from model_conversation.archive import digest, encoded
from .grading_consistency import decisions, record_alignments
from .grading_context import Context
from .scoring_input import strict_json
from .task_grading_contract import mark_all

FORMAT = 'biotracebench-codex-consistency-inspection-1'


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _native_origin(result_path, result):
    if result.get('reviewer_type') == 'codex_source_review':
        from .codex_source_review import validate_review_native
        native, files = validate_review_native(result_path, result)
        predecessor = result['source_review']['first_pass_result']
        prior_native, prior_files = _native_origin(Path(predecessor), read(predecessor))
        files.update(prior_files)
        native['predecessor_origin'] = prior_native
        return native, files
    models = result.get('actual_models')
    if not isinstance(models, list) or len(models) != 1 or not isinstance(models[0], str) or not models[0]:
        raise ValueError('Scientific consistency requires one archived actual Codex model')
    accepted = sorted(result_path.parent.glob('*/accepted.json'))
    if not accepted:
        raise ValueError('Accepted Codex phase archives are missing')
    phases, replies, fingerprints = [], {}, {}
    for path in accepted:
        value = read(path)
        if value.get('reply_identity') != digest(value.get('reply')):
            raise ValueError('Accepted Codex reply identity mismatch')
        selected = None
        for attempt in sorted(path.parent.glob('attempt-*')):
            request_path = attempt / 'request.json'
            if not request_path.is_file() or digest(read(request_path)) != value.get('request_identity'):
                continue
            response_path = attempt / 'reply.json'
            if not response_path.is_file(): response_path = attempt / 'response.txt'
            if response_path.is_file() and digest(strict_json(response_path.read_text())) == value['reply_identity']:
                selected = request_path, response_path
                break
        if selected is None:
            raise ValueError('Accepted phase has no matching native request/reply archive')
        fingerprints[str(path.resolve())] = sha(path)
        for selected_path in selected:
            fingerprints[str(selected_path.resolve())] = sha(selected_path)
        phases.append({'phase': path.parent.name, 'request_identity': value['request_identity'],
                       'reply_identity': value['reply_identity'], 'accepted_sha256': sha(path),
                       'request_sha256': sha(selected[0]), 'reply_sha256': sha(selected[1])})
        replies[path.parent.name] = value['reply']
    if 'whole' in replies:
        if len(replies) != 1 or replies['whole'] != result['marking']:
            raise ValueError('Published marking differs from accepted whole-task response')
    else:
        pair = replies.get('pair')
        cells = sorted(name for name in replies if name.startswith('cells-'))
        if not pair or not cells or set(replies) != {'pair', *cells}:
            raise ValueError('Incomplete accepted staged Codex responses')
        combined = {'records': pair['records'],
                    'cells': [cell for name in cells for cell in replies[name]['cells']],
                    'reference_issues': [issue for name in cells for issue in replies[name]['reference_issues']]}
        if combined != result['marking']:
            raise ValueError('Published marking differs from accepted staged responses')
    return {'request_identity': digest(phases), 'actual_model': models[0],
            'origin_type': 'composite_native_codex_phase_archives', 'phases': phases}, fingerprints


def context_packet(packet, result):
    """Compatibility view for Context; this is not a fabricated model request."""
    payload = packet['payload']
    scope = {'semantic_definition': digest(payload['semantic_definition']),
             'field_rubric': digest(payload['field_rubric']),
             'configured_profile': digest(result['configured_profile']),
             'actual_models': result['actual_models']}
    return {'inventory': payload['inventory'], 'consistency_scope': scope,
            'request': {'payload': {'task_definition': payload['task_definition'],
                        'dictionary_json': encoded(payload['dictionary']).decode(),
                        'scoring_policy_json': encoded(payload['policy']).decode(),
                        'sources': payload['sources']}}}


def _same_metrics(stored, checked):
    return all(stored[level][metric] == checked[level][metric]
               for level in ('field', 'record')
               for metric in ('tp', 'predicted', 'gold', 'precision', 'recall', 'f1'))


def _group(items, kind):
    groups, conflicts = [], []
    for identity, members in sorted(items.items()):
        if len(members) < 2: continue
        signatures = Counter(member['signature'] for member in members)
        group = {'key': identity, 'kind': kind, 'members': members,
                 'distinct_decisions': len(signatures), 'conflict': len(signatures) > 1}
        groups.append(group)
        if group['conflict']: conflicts.append(group)
    return groups, conflicts


def inspect(index_path, out):
    index_path, out = Path(index_path), Path(out)
    index = read(index_path)
    routes = defaultdict(list)
    for row in index['positions']:
        if row.get('status') == 'complete':
            result_path, packet_path = Path(row['result']), Path(row['packet'])
            if not result_path.is_absolute(): result_path = index_path.parent / result_path
            if not packet_path.is_absolute(): packet_path = index_path.parent / packet_path
            routes[str(result_path.resolve()), str(packet_path.resolve())].append(row)
    local, alignments = defaultdict(list), defaultdict(list)
    origins, skipped, fingerprints = {}, [], {str(index_path.resolve()): sha(index_path)}
    decision_count = 0
    for (result_name, packet_name), position_rows in sorted(routes.items()):
        result_path, packet_path = Path(result_name), Path(packet_name)
        try:
            initial = {name: sha(name) for name in (result_name, packet_name)}
            result, packet = read(result_path), read(packet_path)
            expected_plans = {row.get('plan_identity', index.get('plan_identity')) for row in position_rows}
            if expected_plans != {result.get('plan_identity')} or result.get('input_identity') != packet.get('input_identity'):
                raise ValueError('Result and frozen input campaign identities differ')
            if result.get('result_identity') != digest({k: v for k, v in result.items() if k != 'result_identity'}):
                raise ValueError('Published Codex result identity mismatch')
            if result.get('local_terminal'):
                skipped.append({'job_id': position_rows[0].get('job_id'), 'reason': 'Local terminal count has no scientific judge response'})
                continue
            checked = mark_all(packet['payload']['inventory'], result['marking'])
            if not _same_metrics(result['score'], checked):
                raise ValueError('Published score differs from its accepted marking')
            native, native_hashes = _native_origin(result_path, result)
            compatible = context_packet(packet, result)
            checked.update(request_identity=native['request_identity'], grading_model=native['actual_model'])
            context = Context(compatible, checked['records'])
            job_key = digest({'result': result_name, 'packet': packet_name})
            origins[job_key] = {'job_id': position_rows[0].get('job_id'),
                                'positions': [{k: row.get(k) for k in ('case', 'model', 'condition', 'domain')}
                                              for row in position_rows],
                                'input_identity': result['input_identity'],
                                'packet_sha256': initial[packet_name], 'result_sha256': initial[result_name],
                                'result_path': result_name, 'packet_path': packet_name, 'native_origin': native}
            for decision in decisions(compatible, checked, context):
                decision_count += 1
                member = {'origin_key': job_key, 'job_id': position_rows[0].get('job_id'),
                          'case': position_rows[0]['case'], 'context_identity': decision['context_identity'],
                          'table': decision['table'], 'reference_row_index': decision['reference_row_index'],
                          'field': decision['field'], 'category': decision['category'], 'verdict': decision['verdict'],
                          'reason': decision['reason'], 'prediction_value_json': decision['prediction_value_json'],
                          'reference_value_json': decision['reference_value_json'],
                          'signature': digest([decision['category'], decision['verdict']])}
                local[decision['key']].append(member)
            for alignment in record_alignments(compatible, checked, context):
                signature = digest(sorted([{k: pair[k] for k in ('prediction_object', 'reference_object', 'verdict')}
                                           for pair in alignment['pairs']], key=digest))
                alignments[alignment['input_identity']].append({'origin_key': job_key,
                    'job_id': position_rows[0].get('job_id'), 'case': position_rows[0]['case'],
                    'signature': signature, 'pairs': alignment['pairs']})
            if any(sha(path) != expected for path, expected in initial.items()):
                raise ValueError('Published input changed during consistency inspection')
            fingerprints.update(initial); fingerprints.update(native_hashes)
        except (ValueError, KeyError, TypeError, OSError) as error:
            raise ValueError('Cannot inspect accepted Codex output ' + result_name + ': ' + str(error)) from error
    local_groups, local_conflicts = _group(local, 'scientific_field')
    alignment_groups, alignment_conflicts = _group(alignments, 'complete_input_alignment')
    if any(sha(path) != expected for path, expected in fingerprints.items()):
        raise ValueError('Inspected archive changed before report publication')
    report = {'format': FORMAT, 'index': str(index_path.resolve()), 'index_sha256': sha(index_path),
              'inspected_native_jobs': len(origins), 'inspected_scientific_decisions': decision_count,
              'repeated_local_context_groups': len(local_groups), 'local_context_conflicts': len(local_conflicts),
              'repeated_complete_input_alignment_groups': len(alignment_groups),
              'alignment_conflicts': len(alignment_conflicts), 'origins': origins,
              'groups': local_groups + alignment_groups, 'conflicts': local_conflicts + alignment_conflicts,
              'skipped': skipped, 'source_sha256': fingerprints,
              'action': 'Source-review queue only; no verdict, alignment, answer or score was changed.'}
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x') as stream: stream.write(json.dumps(report, ensure_ascii=False) + '\n')
    return {k: report[k] for k in ('inspected_native_jobs', 'inspected_scientific_decisions',
            'repeated_local_context_groups', 'local_context_conflicts',
            'repeated_complete_input_alignment_groups', 'alignment_conflicts')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', required=True); parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    print(json.dumps(inspect(args.index, args.out), ensure_ascii=False))


if __name__ == '__main__': main()
