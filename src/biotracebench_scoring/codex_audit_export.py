"""Export validated Codex and frozen-audit decisions for independent analysis.

This scoring-side preflight replays the counter. Analysis reads the resulting
interchange file and never imports or invokes a grader.
"""
import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from .task_grading_contract import mark_all

FORMAT = 'biotracebench-codex-audit-interchange-1'


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _typed(value):
    if isinstance(value, Decimal):
        if not value.is_finite(): raise ValueError('Nonfinite inventory number')
        sign, digits, exponent = value.as_tuple()
        digits = list(digits)
        while len(digits) > 1 and digits[-1] == 0:
            digits.pop(); exponent += 1
        return ['number', [sign, digits, exponent] if value else [0, [0], 0]]
    if isinstance(value, dict):
        return ['object', [[k, _typed(v)] for k, v in sorted(value.items())]]
    if isinstance(value, list):
        return ['array', [_typed(v) for v in value]]
    return [type(value).__name__, value]


def inventory_signature(inv):
    cells = []
    for cell in inv['cells']:
        value = json.loads(cell['value_json'], parse_int=Decimal, parse_float=Decimal)
        cells.append([cell['side'], cell['table'], cell['row_index'], cell['field'],
                      cell['role'], cell['present'], cell['nonempty'], _typed(value)])
    cells.sort(key=lambda c: (c[0], c[1], c[2], c[3]))
    return hashlib.sha256(json.dumps(cells, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def reference_fields(result):
    output = {}
    for cell in result['cells']:
        ref = cell.get('reference')
        if cell['category'] == 'scientific' and ref and ref['nonempty']:
            identity = ref['table'], ref['row_index'], ref['field']
            if identity in output: raise ValueError('Repeated reference field')
            output[identity] = None if cell['verdict'] == 'uncertain' else cell['verdict'] == 'correct'
    if len(output) != result['field']['gold']: raise ValueError('Reference field denominator mismatch')
    return [[*key, value] for key, value in output.items()]


def reference_records(inv, reply, result):
    rows = {r['id']: r for r in inv['rows']}; output = {}
    for record in reply['records']:
        g, p = record['reference_row'], record['prediction_row']
        if g is None: continue
        cells = [c for c in result['cells'] if
                 (c.get('reference') and c['reference']['row'] == g) or
                 (p and c.get('prediction') and c['prediction']['row'] == p)]
        active = [c for c in cells if c['category'] == 'scientific' and
                  any(c.get(s) and c[s]['nonempty'] for s in ('prediction', 'reference'))]
        verdict = (None if record['verdict'] == 'uncertain' or any(c['verdict'] == 'uncertain' for c in cells)
                   else bool(record['verdict'] == 'matched' and active and
                             all(c['verdict'] in {'correct', 'not_scored'} for c in cells)))
        output[rows[g]['table'], rows[g]['row_index']] = verdict
    if len(output) != result['record']['gold']: raise ValueError('Reference record denominator mismatch')
    return [[*key, value] for key, value in output.items()]


def _same_score(stored, actual):
    return all(stored[level][metric] == actual[level][metric]
               for level in ('field', 'record') for metric in ('tp', 'predicted', 'gold', 'precision', 'recall', 'f1'))


def _validated(inv, marking, stored=None):
    checked = mark_all(inv, marking)
    if stored is not None and not _same_score(stored, checked):
        raise ValueError('Published score does not replay')
    score = {key: checked[key] for key in ('field', 'record', 'unresolved_items', 'score_basis')}
    return {'score': score, 'inventory_signature': inventory_signature(inv),
            'field_items': reference_fields(checked), 'record_items': reference_records(inv, marking, checked)}


def export(new_index, audit_dir, out):
    new_index, out = Path(new_index), Path(out)
    index = read(new_index); jobs, routes, source_hashes = {}, [], {}
    for route in index['positions']:
        item = {key: route[key] for key in ('case', 'model', 'condition', 'domain', 'status')}
        if route.get('status') == 'complete':
            result_path, packet_path = Path(route['result']), Path(route['packet'])
            if not result_path.is_absolute(): result_path = new_index.parent / result_path
            if not packet_path.is_absolute(): packet_path = new_index.parent / packet_path
            paths = str(result_path.resolve()), str(packet_path.resolve())
            token = hashlib.sha256(json.dumps(paths).encode()).hexdigest()
            if token not in jobs:
                try:
                    before = {p: sha(p) for p in paths}
                    result, packet = read(result_path), read(packet_path)
                    if result.get('plan_identity') != route.get('plan_identity', index.get('plan_identity')):
                        raise ValueError('New result belongs to a different campaign')
                    if result.get('input_identity') != packet.get('input_identity'):
                        raise ValueError('New result belongs to a different frozen input')
                    if result.get('reviewer_type') == 'codex_source_review':
                        from .codex_source_review import validate_review_native
                        _, review_files = validate_review_native(result_path, result)
                        source_hashes.update(review_files)
                    value = _validated(packet['payload']['inventory'], result['marking'], result['score'])
                    value['origin_plan_identity'] = result.get('plan_identity')
                    if any(sha(p) != s for p, s in before.items()):
                        raise ValueError('New scoring source changed during validation')
                    source_hashes.update(before)
                    jobs[token] = value
                except (ValueError, KeyError, OSError, TypeError) as error:
                    jobs[token] = {'error': str(error)}
            item['validation_key'] = token
            if 'error' not in jobs[token] and jobs[token]['origin_plan_identity'] != route.get('plan_identity', index.get('plan_identity')):
                raise ValueError('Shared result route has a different origin plan')
            if 'error' not in jobs[token] and not _same_score(route['score'], jobs[token]['score']):
                raise ValueError('Index score differs from response replay')
        routes.append(item)
    root = Path(audit_dir)
    if (root / 'adjudicated').is_dir(): root /= 'adjudicated'
    audit = []
    for path in sorted(root.glob('Q*.json')):
        source_hashes[str(path.resolve())] = sha(path)
        packet = read(path); identity = packet['identity'].copy()
        if identity['stage'] == 'generation': identity['stage'] = 'i0'
        if identity['stage'] != 'i0': continue
        value = _validated(packet['inventory'], packet['marking'])
        if value['score']['unresolved_items']:
            raise ValueError('Frozen audit contains unresolved judgments')
        audit.append({'identity': identity, 'answer_id': path.stem, **value})
    if not audit: raise ValueError('No initial-generation audit outputs')
    for name in ('reviewer_A.json', 'reviewer_B.json'):
        path = root.parent / 'inputs' / name
        if path.is_file(): source_hashes[str(path.resolve())] = sha(path)
    value = {'format': FORMAT, 'new_index': str(new_index.resolve()), 'new_index_sha256': sha(new_index),
             'plan_identity': index.get('plan_identity'), 'source_sha256': source_hashes,
             'positions': routes, 'jobs': jobs, 'audit': audit}
    if any(sha(p) != s for p, s in source_hashes.items()):
        raise ValueError('Frozen audit or scoring source changed during export')
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x') as stream: stream.write(json.dumps(value, ensure_ascii=False) + '\n')
    return {'outputs': len(routes), 'validated_jobs': len(jobs), 'audit_outputs': len(audit), 'out': str(out)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('new-index', 'audit-dir', 'out'): parser.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(export(args.new_index, args.audit_dir, args.out), ensure_ascii=False))


if __name__ == '__main__': main()
