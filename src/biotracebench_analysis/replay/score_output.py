"""Prepare source-bound scientific reviews and apply the published scoring contract."""
from copy import deepcopy
from pathlib import Path
import argparse
import json
import re
from .eligibility import exclusions
from .io import Artifact, read, write, digest
from .scoring import projected
from .review_contract import (annotations_path, field_states, source_registry,
                              validate_identity_evidence, pending_applicable, EXPLICIT_NULL_STATES)
from model_conversation.archive import digest as content_digest, encoded, read_exact
from biotracebench_scoring.task_grading_contract import inventory, mark_all, PROMPT, RESPONSE_SCHEMA

# Frozen protocol/format version identifiers.
# "publication" is the serialized protocol namespace.
LEGACY_CONTRACT = 'biotracebench-publication-i0-1'
PREVIOUS_CONTRACT = 'biotracebench-publication-review-2'
STATE_CONTRACT = 'biotracebench-publication-review-3'
CONTRACT = 'biotracebench-publication-review-4'
STATE_CONTRACTS = {STATE_CONTRACT, CONTRACT}
BASE_SECTIONS = ('records', 'cells', 'reference_issues')

# Exact identities for the decision-authority metadata rename only.
_RULE_BINDING_ALIASES = {'dbbbfe48d6683a22264cae1ed427a44ea1b7374fb8d686777ba3b16eb3b240c6': 'e2fcc59b6b4dfc1fea6ea3ad0c7350c5c88c95333701810d13b8e828eae1c8d3', '9a0d76ff5a0395bc870e4c7a0f91fc78b7e05e605df592bd8a7160f845da894f': '080b1e90d1f10410c5b012a8fd22ca8d69dfb79ca05e11ea3e8b2bc1387b51c2'}

def _compatible_rule_binding(packet, current_fingerprint):
    recorded = packet['study_bindings'].get('scoring rules')
    return (_RULE_BINDING_ALIASES.get(recorded) == current_fingerprint
            and content_digest([packet.get('policy'), packet.get('field_dictionary')]) == recorded)


def _paths(artifact, case):
    if not re.fullmatch(r'[BC][0-9]+', case):
        raise ValueError(f'Invalid study ID: {case}')
    domain = 'basic' if case.startswith('B') else 'clinical'
    return (artifact.published / 'projection/references' / (case + '.json'),
            artifact.materials / 'tasks' / domain / case / 'task.json',
            artifact.materials / 'metadata/manifests' / domain / (case + '.json'))

def _study_bindings(artifact, case, ref, task, sources, dispositions):
    annotations = annotations_path(artifact)
    case_states = read_exact(annotations)['cases'].get(case, {}) if annotations.is_file() else {}
    policy, dictionary = artifact.policy(case)
    return {
        'reference': content_digest(read_exact(ref)),
        'task': content_digest(read_exact(task)),
        'source manifest': content_digest(read_exact(sources)),
        'eligibility': content_digest([item for item in dispositions if item['case'] == case]),
        'annotation': content_digest(case_states),
        'scoring rules': content_digest([policy, dictionary]),
    }


def prepare(a):
    artifact = Artifact(a.artifact_root)
    out = Path(a.out)
    if out.resolve().is_relative_to(artifact.root):
        raise ValueError('Write results outside the immutable material bundle')
    if out.exists():
        raise FileExistsError('Output directory must not exist')
    ref, task, sources = _paths(artifact, a.case)
    policy, dic = artifact.policy(a.case)
    submitted = read_exact(a.database)
    original_submission = submitted
    if isinstance(submitted, dict) and isinstance(submitted.get('database'), dict):
        submitted = submitted['database']
    inv = inventory(submitted, read_exact(ref), dic, policy)
    if inv['diagnostics']:
        raise ValueError('Malformed fragments require a reviewed partial inventory; preserve original text before scientific grading')
    manifest = read(sources)
    source_ids = source_registry(artifact, a.case, manifest)
    masks = read(artifact.published / 'source-dispositions.json')
    study_bindings = _study_bindings(artifact, a.case, ref, task, sources, masks)
    states, _ = field_states(artifact, a.case, inv, digest(ref), masks,
                             reference_content_digest=study_bindings['reference'])
    schema = deepcopy(RESPONSE_SCHEMA)
    schema['properties']['identity_evidence'] = {
        'type':'array', 'items':{'type':'object', 'additionalProperties':False,
        'required':['prediction_row','reference_row','basis','evidence'],
        'properties':{'prediction_row':{'type':['string','null']},
                      'reference_row':{'type':['string','null']}, 'basis':{'type':'string'},
                      'evidence':{'type':'array','minItems':1,'items':{
                          'type':'object','additionalProperties':False,'required':['source','locator'],
                          'properties':{'source':{'type':'string'},'locator':{'type':'string'}}}}}}}
    schema['required'].append('identity_evidence')
    check_states = any(not state['nonempty'] and state['state'] in EXPLICIT_NULL_STATES for state in states)
    if check_states:
        schema['properties']['state_assessments'] = {
            'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
                'required': ['reference_cell', 'state', 'locator'],
                'properties': {'reference_cell': {'type': 'string'},
                    'state': {'enum': sorted(EXPLICIT_NULL_STATES | {'unspecified'})},
                    'locator': {'type': ['string', 'null']}}}}
        schema['required'].append('state_assessments')
    domain = 'basic' if a.case.startswith('B') else 'clinical'
    packet = {
        'contract':CONTRACT, 'stage':'i0', 'case':a.case, 'inventory':inv,
        'submitted_json':encoded(original_submission).decode('utf-8'),
        'reference_json':encoded(read_exact(ref)).decode('utf-8'),
        'task_definition':read(task), 'field_dictionary':dic, 'policy':policy,
        'study_bindings': study_bindings,
        'source_manifest':manifest, 'source_identities':source_ids,
        'information_states':states,
        'eligibility':[d for d in masks if d['case'] == a.case],
        'source_base':str(artifact.materials.relative_to(artifact.root) / 'materials' / domain / a.case),
        'actor_required':'Record the actual scientific reviewer and supporting evidence.',
        'instruction':PROMPT.replace(
            'Do not browse, use tools, consult ontologies, amend gold, repair the answer, or invent missing facts.',
            'Use the supplied task and declared local study files. Preserve the reference and answer. Do not retrieve external material, repair the answer, or invent missing facts.'
        ).replace('Return exactly records, cells, reference_issues',
                  'Return exactly ' + ', '.join(schema['required'])) + '\n'
        'Read information_states, eligibility and the full submitted_json/reference_json before reviewing. '
        'The full JSON preserves annotations, including annotations outside a database wrapper; apply them only through their explicit object/field scope. '
        'A blank reference never becomes a scored item through an annotation, and annotations do not supply missing required scientific field content. '
        'Keep raw uncertainty and reference issues visible, including excluded items. For every record disposition provide identity_evidence '
        'with the same row IDs, a scientific basis and source/locator entries. Use prediction or reference with exact supporting inventory cell IDs; '
        'source document paths come from source_manifest. Local primary IDs and result numbers alone cannot establish identity. '
        'Use row:<inventory-row-id> only for unmatched or uncertain dispositions. Excluded objects may cite eligibility with an excluded row ID. ' +
        ('For each matched, eligible double-empty cell with an annotated not_reported or not_applicable reference state, '
         'include its reference_cell in state_assessments. Report only the state actually asserted for that paired '
         'object and field, with a locator in the submitted answer. If the prediction is silent, report unspecified '
         'with a null locator. When requires_explicit is true, silence fails the record-level check. Otherwise '
         'silence is allowed. Exclude rows or cells removed by eligibility. ' if check_states else '') +
        'The program checks evidence locations, active dependencies and applicable uncertainty before counting.',
        'response_schema':schema,
    }
    out.mkdir(parents=True)
    write(out / 'packet.json', packet)
    write(out / 'binding.json', {'contract':CONTRACT, 'case':a.case, 'packet_sha256':content_digest(read_exact(out / 'packet.json'))})
    print(json.dumps({'status':'ready_for_scientific_review', 'cells':len(inv['cells']), 'contract':CONTRACT}))

def finalize(a):
    artifact = Artifact(a.artifact_root)
    packet_path = Path(a.plan) / 'packet.json'
    packet = read(packet_path)
    binding = read(Path(a.plan) / 'binding.json')
    protocol = packet.get('contract')
    legacy = protocol == LEGACY_CONTRACT
    current = protocol == CONTRACT
    if protocol not in STATE_CONTRACTS | {PREVIOUS_CONTRACT, LEGACY_CONTRACT}:
        raise ValueError(f'Unsupported review packet protocol: {protocol}')
    packet_digest = content_digest(read_exact(packet_path)) if current else digest(packet_path)
    if binding['packet_sha256'] != packet_digest:
        raise ValueError('Scoring packet contents changed. Prepare a new review packet.')
    if legacy and not getattr(a, 'legacy_plan', False):
        raise ValueError('Historical packets require explicit --legacy-plan replay')
    case = packet['case']
    ref, task, sources = _paths(artifact, case)
    masks = artifact.published / 'source-dispositions.json'
    dispositions = read(masks)
    if current:
        actual = _study_bindings(artifact, case, ref, task, sources, dispositions)
        for name, fingerprint in actual.items():
            if packet['study_bindings'].get(name) != fingerprint:
                if name == 'scoring rules' and _compatible_rule_binding(packet, fingerprint):
                    continue
                raise ValueError(f'{case}: {name} identity changed. Prepare a new review packet.')
        try:
            source_registry(artifact, case, read(sources))
        except ValueError as error:
            raise ValueError(f'{case}: {error}. Prepare a new review packet after updating the source manifest.') from error
    elif packet['reference_sha256'] != digest(ref) or packet['eligibility_sha256'] != digest(masks):
        raise ValueError('Reference or eligibility identity changed')
    reply = read(a.judgment)
    expected = set(BASE_SECTIONS) if legacy else set(BASE_SECTIONS) | {'identity_evidence'}
    if protocol in STATE_CONTRACTS and 'state_assessments' in packet['response_schema']['required']:
        expected.add('state_assessments')
    if not isinstance(reply, dict) or set(reply) != expected:
        raise ValueError('Review envelope does not match the packet protocol')
    base = {k:reply[k] for k in BASE_SECTIONS}
    valid = mark_all(packet['inventory'], base)
    ignored = []
    if legacy:
        if valid['unresolved_items']:
            raise ValueError('Resolve scientific uncertainty before historical scoring')
    else:
        if not current:
            annotations = annotations_path(artifact)
            if (packet['task_sha256'] != digest(task) or packet['source_manifest_sha256'] != digest(sources)
                    or packet['annotations_sha256'] != (digest(annotations) if annotations.exists() else None)
                    or packet['source_identities'] != source_registry(artifact, case, read(sources))):
                raise ValueError('Task, source or state-annotation identity changed')
        _, _, dependencies = validate_identity_evidence(packet, reply, dispositions)
        _, _, excluded_cells, excluded_rows = exclusions(packet['inventory'], base, packet['case'], dispositions)
        unresolved, ignored = pending_applicable(packet['inventory'], base, excluded_rows, excluded_cells,
                                                 dependencies, packet['information_states'])
        if unresolved:
            raise ValueError('Resolve applicable scientific uncertainty before final scoring')
    out = Path(a.out)
    if out.resolve().is_relative_to(artifact.root):
        raise ValueError('Write results outside the immutable material bundle')
    if out.exists():
        raise FileExistsError('Output directory must not exist')
    result = {'contract':packet['contract'], 'case':packet['case'], 'actor':a.actor,
              'packet_sha256':binding['packet_sha256'], 'judgment_sha256':digest(a.judgment),
              'metrics':projected(packet['inventory'], base, packet['case'], dispositions,
                                  source_states=packet['information_states'] if protocol in STATE_CONTRACTS else (),
                                  state_assessments=reply.get('state_assessments', ()),
                                  submitted=json.loads(packet['submitted_json'])),
              'reference_issues':reply['reference_issues'], 'excluded_review_items':ignored,
              'validation':{'identity_evidence':'historical replay' if legacy else 'passed',
                            'applicable_unresolved_items':0, 'excluded_items_retained':len(ignored)}}
    out.mkdir(parents=True)
    write(out / 'score.json', result)
    write(out / 'judgment.json', reply)
    print(json.dumps(result, ensure_ascii=False, indent=2))

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    q = sub.add_parser('prepare')
    q.add_argument('--artifact-root',type=Path,required=True); q.add_argument('--case',required=True)
    q.add_argument('--database',type=Path,required=True); q.add_argument('--out',type=Path,required=True)
    q = sub.add_parser('finalize')
    q.add_argument('--artifact-root',type=Path,required=True); q.add_argument('--plan',type=Path,required=True)
    q.add_argument('--judgment',type=Path,required=True); q.add_argument('--actor',required=True)
    q.add_argument('--out',type=Path,required=True); q.add_argument('--legacy-plan',action='store_true',help='Replay an explicitly versioned packet (reproduction only)')
    a = p.parse_args(argv)
    {'prepare':prepare, 'finalize':finalize}[a.command](a)

if __name__ == '__main__':
    main()
