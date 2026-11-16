"""Source-backed Codex revisions of fresh uncertain or inconsistent judgments.

First-pass archives remain immutable. Review artifacts bind additional evidence,
scoped native responses, their predecessor and the resulting complete marking.
"""
import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from model_conversation.archive import digest
from . import codex_grading as native
from .human_semantic import build_rubric, instruction
from .task_grading_contract import mark_all
from .task_grading_batches import phase_schema, record_plan, CELL_INSTRUCTION

PROTOCOL = 'biotracebench-codex-source-review-1'
REVIEW = '''This is a source review of a new Codex judgment. Assess the complete scientific meaning under the same human-semantic, strict-field-local contract. Added text and original figures are scientific evidence. A fact absent from an excerpt may be present elsewhere: inspect the supplied additional evidence and remaining-catalog coverage. Report task-required unknown/conflicting source states faithfully. A supported unknown attribute can receive a definite field verdict; never invent an unavailable value or choose whichever verdict gives a higher score. Earlier uncertainty reasons identify questions, not correct answers. Return a specific scientific reason for every reviewed field. Preserve the fixed reference and submitted content. Genuine unresolved identity or meaning stays uncertain and enters a further source-review round.'''


def read(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.' + path.name, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        stream.flush(); os.fsync(stream.fileno())
    try: os.replace(temporary, path)
    finally:
        if temporary.exists(): temporary.unlink()
def _path(base, value):
    path = Path(value)
    return path if path.is_absolute() else base / path

def _plain(reply):
    return {'records': reply['records'], 'reference_issues': reply['reference_issues'],
            'cells': [{k: c[k] for k in ('prediction_cell', 'reference_cell', 'category', 'verdict', 'reason')}
                      for c in reply['cells']]}


def _scope(inv, marking, indices):
    groups = record_plan(inv, marking['records'])
    selected = [groups[i] for i in indices]
    ids = {rid for group in selected for rid in (group['record']['prediction_row'], group['record']['reference_row']) if rid}
    return {'record_indices': indices, 'records': [g['record'] for g in selected],
            'expected_cell_pairs': [p for g in selected for p in g['expected_cell_pairs']]}, {
            'rows': [r for r in inv['rows'] if r['id'] in ids],
            'cells': [c for c in inv['cells'] if c['row'] in ids], 'diagnostics': []}


def _merge(inv, previous, reply, scope):
    if scope is None:
        mark_all(inv, reply)
        return copy.deepcopy(reply)
    expected = {(c['prediction_cell'], c['reference_cell']) for c in scope['expected_cell_pairs']}
    actual = {(c['prediction_cell'], c['reference_cell']) for c in reply['cells']}
    if expected != actual or len(reply['cells']) != len(expected):
        raise ValueError('Source review changed or omitted its frozen field scope')
    ids = {rid for r in scope['records'] for rid in (r['prediction_row'], r['reference_row']) if rid}
    sub = {'rows': [r for r in inv['rows'] if r['id'] in ids],
           'cells': [c for c in inv['cells'] if c['row'] in ids], 'diagnostics': []}
    mark_all(sub, {'records': scope['records'], **reply})
    replacements = {(c['prediction_cell'], c['reference_cell']): c for c in reply['cells']}
    result = copy.deepcopy(previous)
    result['cells'] = [copy.deepcopy(replacements.get((c['prediction_cell'], c['reference_cell']), c)) for c in result['cells']]
    reviewed_refs = {pair[1] for pair in expected if pair[1]}
    if any(issue['reference_cell'] not in reviewed_refs for issue in reply['reference_issues']):
        raise ValueError('Review reference issue lies outside its field scope')
    result['reference_issues'] = [issue for issue in result['reference_issues'] if issue['reference_cell'] not in reviewed_refs] + reply['reference_issues']
    mark_all(inv, result)
    return result


def _targets(inv, marking, conflicts):
    if any(r['verdict'] == 'uncertain' for r in marking['records']) or any(c.get('kind') == 'complete_input_alignment' for c in conflicts):
        return 'whole', []
    by_cell = {c['id']: c for c in inv['cells']}
    wanted = {(m['table'], m['reference_row_index'], m['field']) for conflict in conflicts for m in conflict.get('members', []) if 'field' in m}
    rows = set()
    for mark in marking['cells']:
        ref = by_cell.get(mark['reference_cell'])
        if mark['verdict'] == 'uncertain' or (ref and (ref['table'], ref['row_index'], ref['field']) in wanted):
            rows.update(by_cell[c]['row'] for c in (mark['prediction_cell'], mark['reference_cell']) if c)
    indices = [i for i, r in enumerate(marking['records']) if rows.intersection({r['prediction_row'], r['reference_row']})]
    return 'fields', indices


def prepare_review(index_path, plan_root, catalog_dir, out, *, conflicts=None, image_manifest=None,
                   source_character_budget=100000, image_batch_limit=4):
    index_path, plan_root, catalog_dir, out = map(Path, (index_path, plan_root, catalog_dir, out))
    if out.exists(): raise FileExistsError('Source review requires a new directory')
    if type(source_character_budget) is not int or source_character_budget < 1 or type(image_batch_limit) is not int or image_batch_limit < 1:
        raise ValueError('Review evidence budgets must be positive integers')
    index, base_plan = read(index_path), read(plan_root / 'plan.json')
    conflict_by_job = {}
    if conflicts:
        report = read(conflicts)
        for conflict in report['conflicts']:
            for member in conflict['members']:
                origin = report['origins'][member['origin_key']]
                if sha(origin['result_path']) != origin['result_sha256'] or sha(origin['packet_path']) != origin['packet_sha256']:
                    raise ValueError('Consistency queue references a changed source')
                conflict_by_job.setdefault(member['job_id'], []).append(conflict)
    images_by_case = read(image_manifest) if image_manifest else {}
    jobs = {}; snapshots = {}
    for route in index['positions']:
        if route.get('status') != 'complete' or route['job_id'] in jobs: continue
        result_path, packet_path = _path(index_path.parent, route['result']), _path(index_path.parent, route['packet'])
        result, packet = read(result_path), read(packet_path)
        expected_plan = route.get('plan_identity', index['plan_identity'])
        if result['plan_identity'] != expected_plan or result['input_identity'] != packet['input_identity']:
            raise ValueError('First-pass route identity mismatch')
        checked = mark_all(packet['payload']['inventory'], result['marking'])
        related = conflict_by_job.get(route['job_id'], [])
        if not checked['unresolved_items'] and not related: continue
        mode, indices = _targets(packet['payload']['inventory'], result['marking'], related)
        if mode == 'fields' and not indices: raise ValueError('Review target has no scientific scope')
        case = route['case']; catalog_path = catalog_dir / (case + '.json')
        catalog = read(catalog_path)
        if not isinstance(catalog, list) or len({s['id'] for s in catalog}) != len(catalog):
            raise ValueError('Review requires a complete unique source catalog')
        for source in catalog:
            if set(source) != {'id', 'source', 'locator', 'text'} or any(not isinstance(v, str) or not v for v in source.values()):
                raise ValueError('Malformed review source excerpt')
        images = images_by_case.get(case, [])
        if isinstance(images, dict): images = images.get('images', [])
        frozen_images = []
        for i, image in enumerate(images):
            path = Path(image['path'])
            if not path.is_absolute(): path = Path(image_manifest).parent / path
            if sha(path) != image['sha256']: raise ValueError('Original figure checksum mismatch')
            frozen_images.append({**image, 'id': image.get('id', case + '-image-' + str(i + 1)), 'path': str(path.resolve())})
        jobs[route['job_id']] = {'case': case, 'mode': mode, 'record_indices': indices,
            'first_pass_result': str(result_path.resolve()), 'first_pass_result_sha256': sha(result_path),
            'first_pass_packet': str(packet_path.resolve()), 'first_pass_packet_sha256': sha(packet_path),
            'origin_plan_identity': expected_plan, 'catalog': case + '.json', 'catalog_sha256': digest(catalog),
            'images': frozen_images, 'conflict_questions': related}
        snapshots[case] = catalog
    plan = {'protocol': PROTOCOL, 'index': str(index_path.resolve()), 'first_index_sha256': sha(index_path),
            'base_plan_sha256': sha(plan_root / 'plan.json'), 'profile': base_plan['profile'],
            'source_character_budget': source_character_budget, 'image_batch_limit': image_batch_limit,
            'jobs': jobs, 'implementation_sha256': sha(Path(__file__))}
    plan['identity'] = digest(plan)
    out.mkdir(parents=True)
    write(out / 'plan.json', plan); write(out / 'first-index.json', index)
    for case, catalog in snapshots.items(): write(out / 'catalog' / (case + '.json'), catalog)
    return {'review_jobs': len(jobs), 'plan_identity': plan['identity'], 'out': str(out)}


def _select_evidence(catalog, seen, questions, budget):
    tokens = set(re.findall(r'[a-zA-Z][a-zA-Z0-9_-]{2,}', questions.lower()))
    available = [s for s in catalog if s['id'] not in seen]
    available.sort(key=lambda s: (-sum(t in (s['locator'] + ' ' + s['text']).lower() for t in tokens), s['id']))
    selected, count = [], 0
    for source in available:
        size = len(source['text'])
        if selected and count + size > budget: continue
        selected.append(source); count += size
        if count >= budget: break
    return selected


def _image_invoke(request, attempt, profile, images):
    """Review-only native image transport; the frozen text runner is unchanged."""
    if not images: return native._invoke(request, attempt, profile)
    write(attempt / 'schema.json', request['response_schema'])
    prompt = request['instruction'] + '\nREQUEST_DATA\n' + json.dumps(request['payload'], ensure_ascii=False)
    (attempt / 'stdin.txt').write_text(prompt)
    command = ['codex', 'exec', '--ignore-user-config', '--sandbox', 'read-only', '--skip-git-repo-check',
               '--json', '--color', 'never', '-c', 'web_search="disabled"',
               '-c', 'model_reasoning_effort=' + json.dumps(profile['reasoning_effort'])]
    if profile['model'] is not None: command += ['-c', 'model=' + json.dumps(profile['model'])]
    for feature in profile['disabled_features']: command += ['--disable', feature]
    image_receipts = []
    for number, image in enumerate(images):
        if sha(image['path']) != image['sha256']: raise ValueError('Review figure changed')
        target = attempt / 'images' / (str(number) + '-' + Path(image['path']).name)
        target.parent.mkdir(exist_ok=True); shutil.copy2(image['path'], target)
        command += ['--image', str(target.resolve())]
        image_receipts.append({'source': image['source'], 'sha256': sha(target), 'attachment': str(target.resolve())})
    empty = attempt / 'empty-worker'; empty.mkdir()
    command += ['--cd', str(empty.resolve()), '--output-schema', str((attempt / 'schema.json').resolve()),
                '-o', str((attempt / 'response.txt').resolve()), '-']
    write(attempt / 'invocation.json', {'argv': command, 'stdin_identity': digest(prompt), 'profile': profile,
                                       'timeout_seconds': 1800, 'image_attachments': image_receipts})
    with (attempt / 'events.jsonl').open('wb') as stdout, (attempt / 'stderr.txt').open('wb') as stderr:
        child = subprocess.run(command, input=prompt.encode(), stdout=stdout, stderr=stderr, timeout=1800, check=False)
    events = [json.loads(line) for line in (attempt / 'events.jsonl').read_text().splitlines()]
    if native._tool_events(events): raise ValueError('Source review attempted tools outside the supplied-input contract')
    if child.returncode: raise native._transport_error(events, (attempt / 'stderr.txt').read_text())
    reply = native.exact_json((attempt / 'response.txt').read_text())
    actual = native._session_model_metadata([e.get('thread_id') for e in events if e.get('type') == 'thread.started'])
    if profile['model'] is not None and any(m['model'] != profile['model'] for m in actual):
        raise ValueError('Review actual model differs from the frozen profile')
    write(attempt / 'transport.json', {'executor': 'codex_cli_chatgpt_login', 'tool_events': 0,
        'actual_model_metadata': actual, 'response_sha256': sha(attempt / 'response.txt'), 'image_attachments': image_receipts})
    return reply


def _part_request(packet, previous, scope, coverage, questions):
    if scope is None:
        request = native._request(packet)
    else:
        request = {'protocol': PROTOCOL, 'phase': 'source_review_fields', 'reply_encoding': 'expanded',
            'instruction': native.TRANSPORT_INSTRUCTION + CELL_INSTRUCTION + '\n' + instruction(),
            'payload': copy.deepcopy(packet['payload']), 'response_schema': phase_schema('cells', 'reference_issues')}
        request['payload'].update(frozen_record_pairs=previous['records'], frozen_record_mapping_identity=digest(previous['records']), batch_scope=scope)
    request['instruction'] += '\n' + REVIEW
    request['payload'].update(source_review_coverage=coverage, source_review_questions=questions)
    return request


def _scopes(inv, previous, indices):
    if indices is None: return [None]
    selected, current, size = [], [], 0
    groups = record_plan(inv, previous['records'])
    for index in indices:
        count = len(groups[index]['expected_cell_pairs'])
        if current and size + count > 200:
            selected.append(_scope(inv, previous, current)[0]); current, size = [], 0
        current.append(index); size += count
    if current: selected.append(_scope(inv, previous, current)[0])
    return selected


def execute_review(review_root, *, job_id=None, offline=False, executor=None):
    root = Path(review_root); plan = read(root / 'plan.json')
    if plan['identity'] != digest({k: v for k, v in plan.items() if k != 'identity'}) or plan['implementation_sha256'] != sha(Path(__file__)):
        raise ValueError('Review plan or implementation changed')
    selected = [job_id] if job_id else list(plan['jobs'])
    for job in selected:
        spec = plan['jobs'][job]; folder = root / 'jobs' / job; folder.mkdir(parents=True, exist_ok=True)
        with (folder / '.lock').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if (folder / 'result.json').exists():
                validate_review_native(folder / 'result.json', read(folder / 'result.json')); continue
            if sha(spec['first_pass_result']) != spec['first_pass_result_sha256'] or sha(spec['first_pass_packet']) != spec['first_pass_packet_sha256']:
                raise ValueError('First-pass archive changed')
            first, packet = read(spec['first_pass_result']), read(spec['first_pass_packet'])
            previous = copy.deepcopy(first['marking']); inv = packet['payload']['inventory']
            catalog = read(root / 'catalog' / spec['catalog'])
            if digest(catalog) != spec['catalog_sha256']: raise ValueError('Review catalog changed')
            base_sources = packet['payload']['sources']; seen = {s['id'] for s in base_sources}; seen_images = set()
            union_sources = {s['id']: s for s in base_sources}; receipts = []; round_number = 0
            while True:
                round_number += 1
                questions = json.dumps([m for m in previous['cells'] if m['verdict'] == 'uncertain'] + spec['conflict_questions'], ensure_ascii=False)
                extra = _select_evidence(catalog, seen, questions, plan['source_character_budget'])
                images = [i for i in spec['images'] if i['id'] not in seen_images][:plan['image_batch_limit']]
                seen.update(s['id'] for s in extra); seen_images.update(i['id'] for i in images)
                sources = {s['id']: s for s in base_sources + extra}
                for image in images:
                    sources[image['id']] = {'id': image['id'], 'source': image['source'], 'locator': image.get('locator', image['source']),
                        'text': 'Attached original figure; inspect its pixels. SHA-256 ' + image['sha256']}
                union_sources.update(sources)
                review_packet = copy.deepcopy(packet); review_packet['payload']['sources'] = list(sources.values())
                p = review_packet['payload']; p['field_rubric'] = build_rubric(p['task_definition'], p['dictionary'], p['sources'], p['policy'])
                coverage = {'catalog_chunks': len(catalog), 'seen_catalog_chunks': sum(s['id'] in seen for s in catalog),
                    'remaining_catalog_chunks': sum(s['id'] not in seen for s in catalog),
                    'attached_images': [i['id'] for i in images], 'remaining_images': len(spec['images']) - len(seen_images),
                    'complete_catalog_ids': [{'id': s['id'], 'source': s['source'], 'locator': s['locator']} for s in catalog]}
                if spec['mode'] == 'whole' and round_number == 1: indices = None
                else:
                    mode, indices = _targets(inv, previous, spec['conflict_questions'] if round_number == 1 else [])
                    if mode == 'whole': indices = None
                    if indices == []: break
                for part_number, scope in enumerate(_scopes(inv, previous, indices), 1):
                    part = folder / ('round-' + str(round_number).zfill(3)) / ('part-' + str(part_number).zfill(3)); part.mkdir(parents=True, exist_ok=True)
                    request = _part_request(review_packet, previous, scope, coverage, questions)
                    if (part / 'accepted.json').exists():
                        accepted = read(part / 'accepted.json')
                        if accepted['request_identity'] != digest(request) or accepted['reply_identity'] != digest(accepted['reply']): raise ValueError('Review recovery request/reply changed')
                        raw_reply = accepted['reply']
                    else:
                        attempts = sorted(part.glob('attempt-*'))
                        recovered = None
                        for prior in attempts:
                            if not (prior / 'request.json').is_file() or digest(read(prior / 'request.json')) != digest(request):
                                raise ValueError('Preserved source-review request changed')
                            response = prior / 'response.txt'; transport = prior / 'transport.json'
                            if response.is_file() and transport.is_file():
                                metadata = read(transport)
                                if metadata.get('tool_events') == 0 and metadata.get('response_sha256') == sha(response):
                                    recovered = native.exact_json(response.read_text()); attempt = prior; break
                        if recovered is None:
                            if offline: raise RuntimeError('No accepted source-review response; offline recovery sent no request')
                            if attempts: raise RuntimeError('Incomplete review attempt preserved; inspect it before an explicit new review plan')
                            attempt = part / 'attempt-001'; attempt.mkdir()
                            write(attempt / 'request.json', request)
                            raw_reply = (executor or _image_invoke)(request, attempt, plan['profile'], images)
                        else: raw_reply = recovered
                        write(attempt / 'reply.json', raw_reply)
                    reply = native.expand_reply(review_packet, 'whole', raw_reply) if scope is None else raw_reply
                    before = digest(previous); previous = _merge(inv, previous, reply, scope)
                    if not (part / 'accepted.json').exists():
                        write(part / 'accepted.json', {'request_identity': digest(request), 'reply_identity': digest(raw_reply), 'reply': raw_reply})
                    attempt = next((a for a in sorted(part.glob('attempt-*')) if (a / 'request.json').exists() and digest(read(a / 'request.json')) == digest(request)), None)
                    if attempt is None: raise ValueError('Accepted review lacks native request archive')
                    receipt = {'before_marking_identity': before, 'scope': scope,
                        'request': str((attempt / 'request.json').resolve()), 'request_sha256': sha(attempt / 'request.json'),
                        'reply': str((attempt / 'reply.json').resolve()), 'reply_sha256': sha(attempt / 'reply.json'),
                        'accepted': str((part / 'accepted.json').resolve()), 'accepted_sha256': sha(part / 'accepted.json'),
                        'request_identity': digest(request), 'reply_identity': digest(raw_reply), 'coverage': coverage,
                        'images': images}
                    receipts.append(receipt)
                checked = mark_all(inv, previous)
                write(folder / 'progress.json', {'rounds': round_number, 'unresolved_items': checked['unresolved_items'], 'coverage': coverage})
                if not checked['unresolved_items'] or (not coverage['remaining_catalog_chunks'] and not coverage['remaining_images']): break
            checked = mark_all(inv, previous)
            final_packet = copy.deepcopy(packet); final_packet['payload']['sources'] = list(union_sources.values())
            p = final_packet['payload']; p['field_rubric'] = build_rubric(p['task_definition'], p['dictionary'], p['sources'], p['policy'])
            final_packet['input_identity'] = digest({'payload': p, 'local_terminal': False})
            write(folder / 'packet.json', final_packet)
            models = sorted({m['model'] for receipt in receipts for m in read(Path(receipt['request']).parent / 'transport.json').get('actual_model_metadata', [])})
            if len(models) != 1: raise ValueError('Source review requires one archived actual Codex model')
            if first.get('actual_models') != models:
                raise ValueError('Source-review model changed from the frozen first-pass backend')
            result = {'protocol': PROTOCOL, 'plan_identity': plan['identity'], 'input_identity': final_packet['input_identity'],
                'marking': previous, 'score': checked, 'reviewer_type': 'codex_source_review', 'configured_profile': plan['profile'],
                'actual_models': models, 'local_terminal': False,
                'source_review': {'first_pass_result': spec['first_pass_result'], 'first_pass_result_sha256': spec['first_pass_result_sha256'],
                    'first_pass_packet': spec['first_pass_packet'], 'first_pass_packet_sha256': spec['first_pass_packet_sha256'],
                    'review_plan': str((root / 'plan.json').resolve()), 'review_plan_sha256': sha(root / 'plan.json'),
                    'final_packet': str((folder / 'packet.json').resolve()), 'final_packet_sha256': sha(folder / 'packet.json'), 'parts': receipts}}
            result['result_identity'] = digest(result)
            write(folder / 'result.json', result)
            write(folder / 'status.json', {'status': 'resolved' if not checked['unresolved_items'] else 'source_review_queue', 'unresolved_items': checked['unresolved_items']})
    return overlay_index(root)


def validate_review_native(result_path, result):
    if result.get('result_identity') != digest({k: v for k, v in result.items() if k != 'result_identity'}):
        raise ValueError('Source-review result identity mismatch')
    receipt = result['source_review']; files = {}
    for name in ('first_pass_result', 'first_pass_packet', 'review_plan', 'final_packet'):
        if sha(receipt[name]) != receipt[name + '_sha256']: raise ValueError('Source-review binding changed: ' + name)
        files[receipt[name]] = receipt[name + '_sha256']
    first, packet = read(receipt['first_pass_result']), read(receipt['first_pass_packet'])
    plan = read(receipt['review_plan'])
    if plan['identity'] != digest({k: v for k, v in plan.items() if k != 'identity'}):
        raise ValueError('Source-review plan identity differs')
    specs = [s for s in plan['jobs'].values() if s['first_pass_result_sha256'] == receipt['first_pass_result_sha256']
             and s['first_pass_packet_sha256'] == receipt['first_pass_packet_sha256']]
    if len(specs) != 1: raise ValueError('Source-review predecessor is not uniquely bound by its plan')
    spec = specs[0]; catalog_path = Path(receipt['review_plan']).parent / 'catalog' / spec['catalog']
    catalog = read(catalog_path)
    if digest(catalog) != spec['catalog_sha256']: raise ValueError('Source-review evidence catalog changed')
    files[str(catalog_path)] = sha(catalog_path)
    allowed = {s['id']: s for s in packet['payload']['sources']}
    for source in catalog:
        if source['id'] in allowed and allowed[source['id']] != source:
            raise ValueError('One source ID has conflicting frozen content')
        allowed[source['id']] = source
    image_map = {image['id']: image for image in spec['images']}
    for image in spec['images']:
        allowed[image['id']] = {'id': image['id'], 'source': image['source'], 'locator': image.get('locator', image['source']),
            'text': 'Attached original figure; inspect its pixels. SHA-256 ' + image['sha256']}
    supplied = {s['id']: s for s in packet['payload']['sources']}
    current = copy.deepcopy(first['marking']); phases = []; models = set()
    for part in receipt['parts']:
        for name in ('request', 'reply', 'accepted'):
            if sha(part[name]) != part[name + '_sha256']: raise ValueError('Source-review native phase changed')
            files[part[name]] = part[name + '_sha256']
        if digest(current) != part['before_marking_identity']: raise ValueError('Source-review predecessor marking changed')
        request, raw_reply, accepted = read(part['request']), read(part['reply']), read(part['accepted'])
        if digest(request) != part['request_identity'] or digest(raw_reply) != part['reply_identity'] or accepted != {'request_identity': part['request_identity'], 'reply_identity': part['reply_identity'], 'reply': raw_reply}:
            raise ValueError('Source-review accepted request/reply identity mismatch')
        if request['payload']['inventory'] != packet['payload']['inventory']: raise ValueError('Source review modified the scientific inventory')
        if any(request['payload'][name] != packet['payload'][name] for name in ('task_definition', 'dictionary', 'policy', 'semantic_definition')):
            raise ValueError('Source review changed the task or scientific policy')
        for source in request['payload']['sources']:
            if allowed.get(source['id']) != source: raise ValueError('Review request contains unbound scientific evidence')
            supplied[source['id']] = source
        if part['scope'] is not None and (request['payload'].get('batch_scope') != part['scope'] or
                request['payload'].get('frozen_record_pairs') != current['records']):
            raise ValueError('Source-review request differs from its frozen mapping or scope')
        for image in part['images']:
            if image_map.get(image['id']) != image or sha(image['path']) != image['sha256']: raise ValueError('Original review figure changed')
            files[image['path']] = image['sha256']
        transport_path = Path(part['request']).parent / 'transport.json'; transport = read(transport_path)
        if transport.get('tool_events') != 0: raise ValueError('Source review used undeclared tools')
        attachments = transport.get('image_attachments', [])
        if len(attachments) != len(part['images']): raise ValueError('Native review image coverage differs')
        for attachment, image in zip(attachments, part['images']):
            if attachment['source'] != image['source'] or attachment['sha256'] != image['sha256'] or sha(attachment['attachment']) != image['sha256']:
                raise ValueError('Native review image binding differs')
            files[attachment['attachment']] = image['sha256']
        response_path = transport_path.parent / 'response.txt'
        if (not response_path.is_file() or transport.get('response_sha256') != sha(response_path)
                or digest(native.exact_json(response_path.read_text())) != part['reply_identity']):
            raise ValueError('Source-review native response binding differs')
        files[str(transport_path)] = sha(transport_path)
        files[str(response_path)] = sha(response_path)
        models.update(m['model'] for m in transport.get('actual_model_metadata', []))
        pseudo = {'payload': request['payload'], 'reply_encoding': request['reply_encoding']}
        reply = native.expand_reply(pseudo, 'whole', raw_reply) if part['scope'] is None else raw_reply
        current = _merge(packet['payload']['inventory'], current, reply, part['scope'])
        phases.append({'request_identity': part['request_identity'], 'reply_identity': part['reply_identity'], 'request_sha256': part['request_sha256'], 'reply_sha256': part['reply_sha256']})
    if current != result['marking'] or sorted(models) != result['actual_models'] or len(models) != 1:
        raise ValueError('Published source review differs from native revisions')
    final_packet = read(receipt['final_packet'])
    if {s['id']: s for s in final_packet['payload']['sources']} != supplied:
        raise ValueError('Final review source context differs from actual supplied evidence')
    if final_packet['input_identity'] != digest({'payload': final_packet['payload'], 'local_terminal': False}):
        raise ValueError('Final review packet identity differs')
    if final_packet['input_identity'] != result['input_identity'] or result['plan_identity'] != read(receipt['review_plan'])['identity']:
        raise ValueError('Source-review plan/input binding differs')
    checked = mark_all(packet['payload']['inventory'], current)
    if any(checked[level] != result['score'][level] for level in ('field', 'record')): raise ValueError('Source-review score does not replay')
    return {'request_identity': digest(phases), 'actual_model': next(iter(models)),
            'origin_type': 'native_codex_source_review', 'phases': phases}, files


def _overlay_index(root):
    root = Path(root); plan = read(root / 'plan.json'); base = read(plan['index'])
    positions = []
    for route in base['positions']:
        row = copy.deepcopy(route); row['plan_identity'] = route.get('plan_identity', base['plan_identity'])
        row['result'] = str(_path(Path(plan['index']).parent, route['result']).resolve())
        row['packet'] = str(_path(Path(plan['index']).parent, route['packet']).resolve())
        folder = root / 'jobs' / route['job_id']
        if (folder / 'result.json').exists():
            spec = plan['jobs'][route['job_id']]
            if sha(row['result']) != spec['first_pass_result_sha256'] or sha(row['packet']) != spec['first_pass_packet_sha256']:
                raise ValueError('Final overlay predecessor differs from the reviewed first pass')
            result = read(folder / 'result.json'); validate_review_native(folder / 'result.json', result)
            row.update(result=str((folder / 'result.json').resolve()), packet=str((folder / 'packet.json').resolve()),
                       score=result['score'], status='complete', plan_identity=result['plan_identity'], reviewer_type='codex_source_review')
        positions.append(row)
    identity = digest({'first_index': sha(plan['index']), 'review_plan': plan['identity'],
                       'reviewed_results': {job: sha(root / 'jobs' / job / 'result.json') for job in plan['jobs'] if (root / 'jobs' / job / 'result.json').exists()}})
    index = {'protocol': PROTOCOL, 'plan_identity': identity, 'positions': positions,
             'first_pass_index': plan['index'], 'review_plan_identity': plan['identity']}
    write(root / 'final-index.json', index)
    return {'final_index': str(root / 'final-index.json'), 'review_jobs': len(plan['jobs']),
            'resolved': sum(read(root / 'jobs' / job / 'result.json')['score']['unresolved_items'] == 0 for job in plan['jobs'] if (root / 'jobs' / job / 'result.json').exists())}


def overlay_index(root):
    root = Path(root)
    with (root / '.index.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _overlay_index(root)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare', action='store_true'); action.add_argument('--execute', action='store_true'); action.add_argument('--recover', action='store_true')
    parser.add_argument('--index'); parser.add_argument('--plan-root'); parser.add_argument('--catalog-dir'); parser.add_argument('--out')
    parser.add_argument('--conflicts'); parser.add_argument('--image-manifest'); parser.add_argument('--review-root'); parser.add_argument('--job-id')
    args = parser.parse_args(argv)
    if args.prepare:
        if not all((args.index, args.plan_root, args.catalog_dir, args.out)): parser.error('Preparation needs index, plan-root, catalog-dir and out')
        result = prepare_review(args.index, args.plan_root, args.catalog_dir, args.out, conflicts=args.conflicts, image_manifest=args.image_manifest)
    else:
        if not args.review_root: parser.error('Execution/recovery needs review-root')
        result = execute_review(args.review_root, job_id=args.job_id, offline=args.recover)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__': main()
