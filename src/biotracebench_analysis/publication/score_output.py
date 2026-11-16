"""Prepare source-bound scientific reviews and apply the published scoring contract."""
from copy import deepcopy
from pathlib import Path
import argparse
import json
from .io import Artifact, read, write, digest
from .scoring import projected
from .review_contract import (ANNOTATIONS, field_states, source_registry,
                              validate_identity_evidence, pending_applicable)
from model_conversation.archive import read_exact, encoded
from biotracebench_scoring.task_grading_contract import inventory, mark_all, PROMPT, RESPONSE_SCHEMA

LEGACY_CONTRACT = 'biotracebench-publication-v16-i0-1'
CONTRACT = 'biotracebench-publication-review-2'
BASE_SECTIONS = ('records', 'cells', 'reference_issues')

def _paths(artifact, case):
    domain = 'basic' if case.startswith('B') else 'clinical'
    return (artifact.published / 'projection/references' / (case + '.json'),
            artifact.materials / 'tasks' / domain / case / 'task.json',
            artifact.materials / 'metadata/manifests' / domain / (case + '.json'))

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
    states, annotations_hash = field_states(artifact, a.case, inv, digest(ref), masks)
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
    domain = 'basic' if a.case.startswith('B') else 'clinical'
    packet = {
        'contract':CONTRACT, 'stage':'i0', 'case':a.case, 'inventory':inv,
        'submitted_json':encoded(original_submission).decode('utf-8'),
        'reference_json':encoded(read_exact(ref)).decode('utf-8'),
        'task_definition':read(task), 'field_dictionary':dic, 'policy':policy,
        'reference_sha256':digest(ref), 'task_sha256':digest(task),
        'eligibility_sha256':digest(artifact.published / 'source-dispositions.json'),
        'submitted_sha256':digest(a.database), 'source_manifest':manifest,
        'source_manifest_sha256':digest(sources), 'source_identities':source_ids,
        'annotations_sha256':annotations_hash, 'information_states':states,
        'eligibility':[d for d in masks if d['case'] == a.case],
        'source_base':str(Path('03_Benchmark_Data/01_Task_Materials/materials') / domain / a.case),
        'actor_required':'Record the actual scientific reviewer and supporting evidence.',
        'instruction':PROMPT.replace(
            'Do not browse, use tools, consult ontologies, amend gold, repair the answer, or invent missing facts.',
            'Use the supplied task and declared local study files. Preserve the reference and answer. Do not retrieve external material, repair the answer, or invent missing facts.'
        ).replace('Return exactly records, cells, reference_issues',
                  'Return exactly records, cells, reference_issues, identity_evidence') + '\n'
        'Read information_states, eligibility and the full submitted_json/reference_json before reviewing. '
        'The full JSON preserves annotations, including annotations outside a database wrapper; apply them only through their explicit object/field scope. '
        'A blank reference never becomes a scored item through an annotation, and annotations do not supply missing required scientific field content. '
        'Keep raw uncertainty and reference issues visible, including excluded items. For every record disposition provide identity_evidence '
        'with the same row IDs, a scientific basis and source/locator entries. Use prediction or reference with exact supporting inventory cell IDs; '
        'source document paths come from source_manifest. Local primary IDs and result numbers alone cannot establish identity. '
        'Use row:<inventory-row-id> only for unmatched or uncertain dispositions. Excluded objects may cite eligibility with an excluded row ID. '
        'The program checks evidence locations, active dependencies and applicable uncertainty before counting.',
        'response_schema':schema,
    }
    out.mkdir(parents=True)
    write(out / 'packet.json', packet)
    write(out / 'binding.json', {'contract':CONTRACT, 'case':a.case, 'packet_sha256':digest(out / 'packet.json')})
    print(json.dumps({'status':'ready_for_scientific_review', 'cells':len(inv['cells']), 'contract':CONTRACT}))

def finalize(a):
    artifact = Artifact(a.artifact_root)
    packet = read(Path(a.plan) / 'packet.json')
    binding = read(Path(a.plan) / 'binding.json')
    legacy = packet.get('contract') == LEGACY_CONTRACT
    if binding['packet_sha256'] != digest(Path(a.plan) / 'packet.json') or packet.get('contract') not in {CONTRACT, LEGACY_CONTRACT}:
        raise ValueError('Scoring packet binding changed')
    if legacy and not getattr(a, 'legacy_plan', False):
        raise ValueError('Historical packets require explicit --legacy-plan replay')
    ref, task, sources = _paths(artifact, packet['case'])
    masks = artifact.published / 'source-dispositions.json'
    if packet['reference_sha256'] != digest(ref) or packet['eligibility_sha256'] != digest(masks):
        raise ValueError('Reference or eligibility identity changed')
    reply = read(a.judgment)
    expected = set(BASE_SECTIONS) if legacy else set(BASE_SECTIONS) | {'identity_evidence'}
    if not isinstance(reply, dict) or set(reply) != expected:
        raise ValueError('Review envelope does not match the packet protocol')
    base = {k:reply[k] for k in BASE_SECTIONS}
    valid = mark_all(packet['inventory'], base)
    ignored = []
    if legacy:
        if valid['unresolved_items']:
            raise ValueError('Resolve scientific uncertainty before historical scoring')
    else:
        annotations = artifact.root / ANNOTATIONS
        if (packet['task_sha256'] != digest(task) or packet['source_manifest_sha256'] != digest(sources)
                or packet['annotations_sha256'] != (digest(annotations) if annotations.exists() else None)
                or packet['source_identities'] != source_registry(artifact, packet['case'], read(sources))):
            raise ValueError('Task, source or state-annotation identity changed')
        er, ec, dependencies = validate_identity_evidence(packet, reply, read(masks))
        unresolved, ignored = pending_applicable(packet['inventory'], base, er, ec, dependencies, packet['information_states'])
        if unresolved:
            raise ValueError('Resolve applicable scientific uncertainty before final scoring')
    out = Path(a.out)
    if out.resolve().is_relative_to(artifact.root):
        raise ValueError('Write results outside the immutable material bundle')
    if out.exists():
        raise FileExistsError('Output directory must not exist')
    result = {'contract':packet['contract'], 'case':packet['case'], 'actor':a.actor,
              'packet_sha256':binding['packet_sha256'], 'judgment_sha256':digest(a.judgment),
              'metrics':projected(packet['inventory'], base, packet['case'], read(masks)),
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
    q.add_argument('--out',type=Path,required=True); q.add_argument('--legacy-plan',action='store_true',help='Replay an explicitly versioned historical packet')
    a = p.parse_args(argv)
    {'prepare':prepare, 'finalize':finalize}[a.command](a)

if __name__ == '__main__':
    main()
