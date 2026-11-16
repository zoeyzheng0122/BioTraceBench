"""Validate an I0-only revised-reference native plan before composition.

Reference and policy changes are authored decisions. This module verifies
their identities, source evidence and complete position coverage; it does not
import or reuse scoring judgments.
"""
import copy
from pathlib import Path
from model_conversation.archive import digest, sha
from . import native_codex as native
from .native_case_versions import _case_routes, _key
from .native_adjudication import export_view
from .native_i0_export import export_i0
from .reference_identity_bridge import validate_reference_bridge

FORMAT = 'biotracebench-native-reference-version-1'


def replace_reference_inventory(original, reference_only):
    """Build a new inventory while preserving every submitted cell and diagnostic.

    ``reference_only`` must be built from the new reference using the same
    dictionary and fixed-role policy, with no submitted data. It is still the
    caller's responsibility to author and validate the scientific bridge.
    """
    original = native._inventory(original)
    reference_only = native._inventory(reference_only)
    if (any(r['side'] != 'reference' for r in reference_only['rows']) or
            any(c['side'] != 'reference' for c in reference_only['cells']) or
            reference_only['diagnostics']):
        raise ValueError('New reference inventory must not contain submitted content or diagnostics')
    pred_rows = [copy.deepcopy(r) for r in original['rows'] if r['side'] == 'prediction']
    pred_cells = [copy.deepcopy(c) for c in original['cells'] if c['side'] == 'prediction']
    if [r['id'] for r in pred_rows] != ['p'+str(i) for i in range(len(pred_rows))] or [
            c['id'] for c in pred_cells] != ['c'+str(i) for i in range(len(pred_cells))]:
        raise ValueError('Original submission inventory is not in canonical input order')
    mapping = {}; prediction_count = len(pred_rows)
    for row in reference_only['rows']:
        new = copy.deepcopy(row); mapping[row['id']] = 'r'+str(prediction_count+len(mapping))
        new['id'] = mapping[row['id']]; pred_rows.append(new)
    for cell in reference_only['cells']:
        new = copy.deepcopy(cell); new['id'] = 'c'+str(len(pred_cells)); new['row'] = mapping[cell['row']]
        pred_cells.append(new)
    return native._inventory({'rows':pred_rows,'cells':pred_cells,
                              'diagnostics':copy.deepcopy(original['diagnostics'])})


def _policy_changes(before, after, path=''):
    if isinstance(before, dict) and isinstance(after, dict) and set(before) == set(after):
        for key in sorted(before):
            escaped = str(key).replace('~', '~0').replace('/', '~1')
            yield from _policy_changes(before[key], after[key], path+'/'+escaped)
    elif before != after:
        # Lists are reviewed as a whole to prevent row-order based identity guesses.
        yield {'path':path or '/', 'before':before, 'after':after}


def _validate_blank_transitions(before, after):
    """Require an explicit handling choice for newly blank reference fields."""
    old = {field['id']:field for field in before['fields']}
    for field in after['fields']:
        previous = old.get(field['id'])
        if (previous and previous['required_assertions'] and not field['required_assertions']
                and field.get('applicable', True) and 'optional_context_allowed' not in field):
            raise ValueError('Newly blank reference field needs an explicit optional-context decision')


def verify_reference_version(base_plan, revised_plan, manifest):
    """Check every I0 position and every declared reference/policy change."""
    value = native._json(manifest)
    if value.get('format') != FORMAT or not isinstance(value.get('case'), str):
        raise ValueError('A versioned reference plan manifest is required')
    old, old_routes, _ = _case_routes(base_plan, value['case'])
    new, new_routes, all_new = _case_routes(revised_plan, value['case'])
    old_routes = [r for r in old_routes if r['condition'] == 'i0']
    if len(new_routes) != len(all_new) or any(r['condition'] != 'i0' for r in new_routes):
        raise ValueError('Revised reference plan must contain only its declared case I0 positions')
    if value.get('base_plan_identity') != old['identity'] or value.get('revised_plan_identity') != new['identity']:
        raise ValueError('Reference plan identity mismatch')
    old_by_key = {_key(r):r for r in old_routes}
    new_keys = {_key(r) for r in new_routes}
    if len(old_by_key) != len(old_routes) or len(new_keys) != len(new_routes) or new_keys != set(old_by_key):
        raise ValueError('Revised reference plan must cover every I0 model position')
    bridges = value.get('bridges', [])
    bridge_map = {(b['old_job'],b['new_job']):b for b in bridges}
    if len(bridge_map) != len(bridges):
        raise ValueError('Duplicate reference bridge job pair')
    seen, policy_pair, source_map = set(), None, None
    for route in new_routes:
        previous = old_by_key[_key(route)]
        if any(previous.get(k) != route.get(k) for k in ('domain', 'zero_cause')):
            raise ValueError('Revised reference plan changed domain or terminal cause')
        a, ca = native._inputs(base_plan, previous['job_id'], old)
        b, cb = native._inputs(revised_plan, route['job_id'], new)
        if a['local_terminal'] != b['local_terminal']:
            raise ValueError('Revised reference plan changed terminal status')
        if digest({k:v for k,v in ca.items() if k != 'task_policy'}) != digest(
                {k:v for k,v in cb.items() if k != 'task_policy'}):
            raise ValueError('Revised reference plan changed task or frozen sources')
        key = (previous['job_id'],route['job_id']); seen.add(key)
        if key not in bridge_map:
            raise ValueError('Missing source-authored reference bridge for position')
        item = bridge_map[key]
        if item.get('old_packet_sha256') != previous.get('original_packet_sha256') or item.get('new_packet_sha256') != route.get('original_packet_sha256'):
            raise ValueError('Reference bridge packet provenance mismatch')
        validate_reference_bridge(a['inventory'],b['inventory'],ca['sources'],item['bridge'])
        pair = ca['task_policy'],cb['task_policy']
        if policy_pair is not None and digest(pair) != digest(policy_pair):
            raise ValueError('Reference policy must be uniform across the case')
        policy_pair = pair
        source_map = {s['id']:s['text'] for s in ca['sources']}
    if set(bridge_map) != seen:
        raise ValueError('Reference manifest contains an unrelated bridge')
    _validate_blank_transitions(*policy_pair)
    actual = list(_policy_changes(*policy_pair)); declared = value.get('policy_changes', [])
    if [{k:x[k] for k in ('path','before','after')} for x in declared] != actual:
        raise ValueError('Reference policy changes must be declared exactly')
    for change in declared:
        quote, source_id, reason = change.get('quote'),change.get('source_id'),change.get('reason')
        if (not isinstance(quote,str) or not quote.strip() or source_id not in source_map
                or quote not in source_map[source_id] or not isinstance(reason,str) or not reason.strip()):
            raise ValueError('Policy change requires exact frozen source evidence')
    return {'case':value['case'], 'positions':len(new_routes), 'condition':'i0',
            'base_plan_identity':old['identity'], 'revised_plan_identity':new['identity'],
            'reference_bridges':len(seen), 'policy_changes':len(actual)}


def compose_reference_i0(base_plan, revisions, out, *, base_adjudications=None,
                         required_revised_cases, require_complete=False):
    """Replay one active I0 reference version per case, never using old fallback."""
    if not isinstance(revisions, list):
        raise ValueError('Reference revisions must be an explicit list')
    if (not isinstance(required_revised_cases, list) or
            any(not isinstance(case, str) or not case.strip() for case in required_revised_cases) or
            len(set(required_revised_cases)) != len(required_revised_cases)):
        raise ValueError('Expected revised cases must be an explicit unique list')
    checked, cases = [], set()
    for revision in revisions:
        proof = verify_reference_version(base_plan, revision['plan'], revision['manifest'])
        if proof['case'] in cases:
            raise ValueError('Duplicate reference revision for one case')
        cases.add(proof['case']); checked.append((revision, proof))
    if cases != set(required_revised_cases):
        raise ValueError('Every expected revised case must have exactly one verified plan')
    out = Path(out)
    base = export_i0(base_plan, out/'base', adjudications=base_adjudications)
    data = native._json(base['path'])
    initial = [r for r in data['positions'] if _key(r)[2] == 'i0']
    positions = {_key(r):r for r in initial}
    if not positions or len(positions) != len(initial):
        raise ValueError('Duplicate base I0 position')
    components = [{'role':'base', **base}]
    data['source_sha256'][base['path']] = sha(base['path'])
    for index, (revision, proof) in enumerate(checked):
        child = export_view(revision['plan'], out/('reference-'+str(index)),
                            adjudications=revision.get('adjudications'))
        child_data = native._json(child['path'])
        expected = {k for k in positions if k[0] == proof['case']}
        replacement = {_key(r):r for r in child_data['positions']}
        if not expected or len(replacement) != len(child_data['positions']) or set(replacement) != expected:
            raise ValueError('Replayed revised reference position coverage mismatch')
        for key, row in replacement.items():
            old = positions[key]
            row['superseded_version'] = {k:old.get(k) for k in
                ('input_identity','packet_path','result_path','score','status')}
            row['reference_revision'] = copy.deepcopy(proof)
            positions[key] = row
        for path, expected_hash in child_data['source_sha256'].items():
            if path in data['source_sha256'] and data['source_sha256'][path] != expected_hash:
                raise ValueError('Reference plan source artifact identities differ')
            data['source_sha256'][path] = expected_hash
        data['source_sha256'][child['path']] = sha(child['path'])
        manifest = str(Path(revision['manifest']).resolve())
        data['source_sha256'][manifest] = sha(manifest)
        components.append({'role':'case_reference_revision', **proof, **child})
    data['positions'] = [positions[_key(r)] for r in initial]
    complete = all(r['status'] == 'complete' for r in data['positions'])
    if require_complete and not complete:
        raise ValueError('Composed active I0 position grid is incomplete')
    data['reference_version_composition'] = {'format':FORMAT,'condition':'i0',
        'components':components,'positions':len(positions),
        'coverage':'complete' if complete else 'incomplete'}
    data['source_sha256'][str(Path(__file__).resolve())] = sha(__file__)
    for path, expected_hash in data['source_sha256'].items():
        if sha(path) != expected_hash:
            raise ValueError('Composed reference source artifact changed')
    path = out/'exports'/digest(data)/'comparison-input.json'
    native._write_once(path,data)
    return {'path':str(path.resolve()),'sha256':sha(path),'positions':len(positions),
            'coverage':data['reference_version_composition']['coverage'],
            'revised_cases':sorted(cases),'validation_status':data['validation_status']}
