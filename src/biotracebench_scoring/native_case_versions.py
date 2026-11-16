"""Compose frozen native plans with explicit, uniform applicability amendments.

Scientific authors select and justify exclusions. This module verifies that
only those field policies changed and replays each component through the native
exporter. It never edits an input, imports a judgment, or chooses a verdict.
"""
import copy
from pathlib import Path

from model_conversation.archive import digest, sha
from . import native_codex as native
from .native_adjudication import export_view

FORMAT = 'biotracebench-native-applicability-amendment-1'


def _key(row):
    identity = row.get('identity', row)
    return tuple(identity[k] for k in ('case', 'model', 'condition'))


def _case_routes(root, case):
    frozen = native._json(Path(root) / 'plan.json')
    routes = native._json(Path(root) / 'private' / 'routes.json')
    if digest(routes) != frozen['routes_identity']:
        raise ValueError('Case version route identity mismatch')
    selected = [r for r in routes if r['case'] == case]
    if not selected:
        raise ValueError('Applicability amendment names an unknown case')
    frozen = native._verify_plan(root, list({r['job_id'] for r in selected}))
    if digest(routes) != frozen['routes_identity']:
        raise ValueError('Case version routing changed during verification')
    return frozen, selected, routes


def verify_amendment(base_plan, amendment_plan, manifest):
    """Verify an authored applicability-only change over an entire case grid."""
    value = native._json(manifest)
    if value.get('format') != FORMAT:
        raise ValueError('A versioned native applicability manifest is required')
    for name in ('case', 'basis', 'task_quote'):
        if not isinstance(value.get(name), str) or not value[name].strip():
            raise ValueError('Applicability amendment lacks its explicit task basis')
    ids = value.get('excluded_fields')
    if (not isinstance(ids, list) or not ids or
            any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids)):
        raise ValueError('Applicability amendment needs unique field identities')
    old, old_routes, _ = _case_routes(base_plan, value['case'])
    new, new_routes, all_new_routes = _case_routes(amendment_plan, value['case'])
    if len(new_routes) != len(all_new_routes):
        raise ValueError('An applicability amendment plan must contain exactly its declared case')
    if (value.get('base_plan_identity') != old['identity'] or
            value.get('amendment_plan_identity') != new['identity']):
        raise ValueError('Applicability amendment plan identity mismatch')
    old_by_key = {_key(r): r for r in old_routes}
    if len(old_by_key) != len(old_routes) or {_key(r) for r in new_routes} != set(old_by_key):
        raise ValueError('Applicability amendment must cover every case model/stage position')
    policy_pair = None
    for route in new_routes:
        previous = old_by_key[_key(route)]
        if any(previous.get(k) != route.get(k) for k in ('domain', 'zero_cause', 'original_packet_sha256')):
            raise ValueError('Applicability amendment changed domain or original execution provenance')
        a, ca = native._inputs(base_plan, previous['job_id'], old)
        b, cb = native._inputs(amendment_plan, route['job_id'], new)
        if (digest(a['inventory']) != digest(b['inventory']) or
                a['local_terminal'] != b['local_terminal']):
            raise ValueError('Applicability amendment changed a submitted/reference input')
        if digest({k: v for k, v in ca.items() if k != 'task_policy'}) != digest(
                {k: v for k, v in cb.items() if k != 'task_policy'}):
            raise ValueError('Applicability amendment changed task, sources or numerical rules')
        if value['task_quote'] not in ca['task_definition']:
            raise ValueError('Applicability task basis is not a literal frozen task excerpt')
        pair = ca['task_policy'], cb['task_policy']
        if policy_pair is not None and digest(pair) != digest(policy_pair):
            raise ValueError('Applicability amendment differs across models or stages')
        policy_pair = pair
    before, after = policy_pair
    expected = copy.deepcopy(before)
    old_fields = {f['id']: f for f in before['fields']}
    new_fields = {f['id']: f for f in after['fields']}
    if not set(ids) <= set(old_fields) or set(old_fields) != set(new_fields):
        raise ValueError('Applicability amendment changed the field inventory')
    for field in expected['fields']:
        if field['id'] not in ids:
            continue
        changed = new_fields[field['id']]
        if (not field.get('applicable', True) or not field['required_assertions'] or
                changed.get('applicable') is not False or changed['required_assertions'] or
                not isinstance(changed.get('applicability'), dict)):
            raise ValueError('Only explicitly justified applicable-to-inapplicable fields may change')
        field.update(applicable=False, required_assertions=[],
                     applicability=copy.deepcopy(changed['applicability']))
    if digest(expected) != digest(after):
        raise ValueError('Applicability amendment changed undeclared scientific requirements')
    return {'case': value['case'], 'positions': len(new_routes),
            'base_plan_identity': old['identity'], 'amendment_plan_identity': new['identity'],
            'base_policy_identity': digest(before), 'amendment_policy_identity': digest(after),
            'excluded_fields': ids, 'basis': value['basis'], 'task_quote': value['task_quote']}


def compose_native(base_plan, amendments, out, *, base_adjudications=None,
                   historical=None, audit=None, audit_provenance=None,
                   require_complete=False):
    """Replay component plans and select one declared version per whole case.

    Each amendment is ``{plan, manifest, adjudications?}``. Pending amendment
    positions remain pending; completed base scores are never used as fallback.
    ``require_complete`` applies to the composed active grid, which excludes
    superseded case positions but preserves their source artifacts and scores.
    """
    if not isinstance(amendments, list):
        raise ValueError('Applicability amendments must be an explicit list')
    checked, cases = [], set()
    for amendment in amendments:
        proof = verify_amendment(base_plan, amendment['plan'], amendment['manifest'])
        if proof['case'] in cases:
            raise ValueError('Duplicate applicability amendment for one case')
        cases.add(proof['case']); checked.append((amendment, proof))
    out = Path(out)
    exported = export_view(base_plan, out/'base', adjudications=base_adjudications,
                           historical=historical, audit=audit, audit_provenance=audit_provenance)
    data = native._json(exported['path'])
    positions = {_key(r): r for r in data['positions']}
    components = [{'role': 'base', **exported}]
    data['source_sha256'][exported['path']] = sha(exported['path'])
    for number, (amendment, proof) in enumerate(checked):
        child = export_view(amendment['plan'], out/('amendment-'+str(number)),
                            adjudications=amendment.get('adjudications'))
        child_data = native._json(child['path'])
        expected = {key for key in positions if key[0] == proof['case']}
        replacement = {_key(row): row for row in child_data['positions']}
        if set(replacement) != expected:
            raise ValueError('Replayed applicability amendment position coverage mismatch')
        for key, row in replacement.items():
            row['superseded_version'] = {'input_identity': positions[key]['input_identity'],
                                         'packet_path': positions[key]['packet_path'],
                                         'result_path': positions[key]['result_path'],
                                         'score': positions[key]['score'], 'status': positions[key]['status']}
            row['applicability_amendment'] = copy.deepcopy(proof)
            positions[key] = row
        for path, expected_hash in child_data['source_sha256'].items():
            if path in data['source_sha256'] and data['source_sha256'][path] != expected_hash:
                raise ValueError('Component source identities differ')
            data['source_sha256'][path] = expected_hash
        data['source_sha256'][child['path']] = sha(child['path'])
        manifest = str(Path(amendment['manifest']).resolve())
        data['source_sha256'][manifest] = sha(manifest)
        components.append({'role': 'case_applicability_amendment', **proof, **child})
    data['positions'] = [positions[_key(r)] for r in data['positions']]
    if require_complete and any(r['status'] != 'complete' for r in data['positions']):
        raise ValueError('Composed active native position grid is incomplete')
    data['case_version_composition'] = {'format': FORMAT, 'components': components,
        'positions': len(positions), 'coverage': 'complete' if all(
            r['status'] == 'complete' for r in data['positions']) else 'incomplete'}
    data['source_sha256'][str(Path(__file__).resolve())] = sha(__file__)
    for path, expected_hash in data['source_sha256'].items():
        if sha(path) != expected_hash:
            raise ValueError('Composed native source artifact changed')
    path = out / 'exports' / digest(data) / 'comparison-input.json'
    native._write_once(path, data)
    return {'path': str(path.resolve()), 'sha256': sha(path), 'positions': len(positions),
            'coverage': data['case_version_composition']['coverage'],
            'amended_cases': sorted(cases), 'validation_status': data['validation_status']}
