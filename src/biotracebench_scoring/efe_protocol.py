"""Executable evidence contract for new EFE record correspondences.

The contract validates provenance and bookkeeping. Scientific equivalence is
decided by the declared judge or source reviewer, never by maximizing matches.
Historical whole-task replies keep their original protocol and scores.
"""
import copy
from pathlib import Path

from model_conversation.archive import digest, read, write, seal
from .task_grading_contract import RESPONSE_SCHEMA, mark_all

CONTRACT = 'biotracebench-efe-alignment-1'
OUTCOME_FIELDS = {'population_size', 'result_value', 'factor_value',
                  'supplementary_statistics'}
RULES = {
    'source_identity': 'Use source-native object labels or object-level identifiers and the task scope.',
    'context_identity': 'Use the source-grounded combination of membership, experimental material, roles and context.',
    'attribute_error': 'Independent evidence identifies the object; judge the incorrect attribute separately.',
    'equivalent_objects': 'Source evidence establishes interchangeability, preserving multiplicity and relationship roles.',
    'merged_or_missing': 'A merged submission receives at most one independently supported correspondence; remaining references stay missing.',
    'surplus_or_nonmatch': 'Keep extra, duplicate and scientifically different submitted objects in prediction counts.',
    'unresolved': 'Retain genuine identity uncertainty and its known denominators until source review resolves it.',
}
RESOLUTIONS = {'same_object', 'equivalent_objects', 'not_submitted',
               'surplus_prediction', 'unresolved'}

INSTRUCTION = '''Apply the supplied EFE alignment protocol before judging fields. For each record, return identity_basis with a declared rule_id, resolution, supporting_cells, source_evidence and conflicts. supporting_cells are actual scientific inventory cell IDs from the declared row pair, not local biomedical IDs. Use object descriptors and source-native labels; counts, outcomes and supplementary statistics alone cannot establish identity. source_evidence contains IDs from the supplied frozen sources, when the decision depends on source interpretation.
Names and local IDs may differ. Establish identity from source-supported membership or experimental material, roles, native identifiers and task scope. A wrong attribute does not destroy correspondence when independent identity evidence remains. Time, method or population differences that denote a different requested object or analysis require a nonmatch; describe the distinction. Never use the resulting field score to select a correspondence. Resolve scientific objects before comparing association targets under that same mapping. A wrong result link can be judged separately when other evidence identifies the intended result. An unrelated error in a target object's attributes does not automatically invalidate a correct association.
Keep one-to-one correspondence and all submitted multiplicities. Do not split or repair a merged record. Match it to at most one reference only with independent identity evidence; record other references as missing. Treat duplicate submitted objects as surplus. Equal visible attributes alone do not establish scientific interchangeability. equivalent_objects requires supplied source evidence, preservation of multiplicity and compatible relationship roles. Missing evidence stays unresolved; never invent an arbitrary row-order or maximum-score tie-break.
For a matched pair include nonempty supporting scientific cells from BOTH rows. For source-dependent interpretation, resolved conflicts or equivalent objects include source_evidence. Each conflict lists its actual field, handling (attribute_error or identity_conflict) and reason. same_object may retain attribute_error conflicts; an unresolved identity_conflict cannot be a matched pair. Missing, extra and uncertain records retain their appropriate resolutions. Local identifiers themselves remain unscored. Field and complete-record metrics use exactly this correspondence. The program validates evidence pointers and counting; it does not certify the scientific truth of a supplied rationale.'''

INSTRUCTION += ''' For a comparative result, interpret population_id jointly with the submitted comparison and analysis context. A source-supported subject-arm or combined-analysis anchor can express the same comparison when both treatment or period roles, direction and the actual analysis set are explicit and correct. Preserve distinctions between randomized, evaluable and endpoint-specific sets. Equal counts or shared parentage alone cannot establish this equivalence. Retain all submitted records and the fixed counting convention. Missing task-required population rows remain missing and surplus rows remain predictions.'''


def definition(path):
    value = read(path)
    if (not isinstance(value, dict) or set(value) != {'contract', 'rules', 'association_semantics'}
            or value['contract'] != CONTRACT or value['rules'] != RULES
            or not isinstance(value['association_semantics'], str)
            or not value['association_semantics'].strip()):
        raise ValueError('Unknown or incomplete EFE alignment definition')
    return value


def schema():
    result = copy.deepcopy(RESPONSE_SCHEMA)
    record = result['properties']['records']['items']
    text = {'type': 'string'}
    basis = {'type': 'object', 'additionalProperties': False,
             'required': ['rule_id', 'resolution', 'supporting_cells', 'source_evidence', 'conflicts'],
             'properties': {
                 'rule_id': {'type': 'string', 'enum': sorted(RULES)},
                 'resolution': {'type': 'string', 'enum': sorted(RESOLUTIONS)},
                 'supporting_cells': {'type': 'array', 'items': text},
                 'source_evidence': {'type': 'array', 'items': text},
                 'conflicts': {'type': 'array', 'items': {
                     'type': 'object', 'additionalProperties': False,
                     'required': ['field', 'handling', 'reason'],
                     'properties': {'field': text, 'reason': text,
                                    'handling': {'type': 'string', 'enum': ['attribute_error', 'identity_conflict']}}}}}}
    record['properties']['identity_basis'] = basis
    record['required'].append('identity_basis')
    return result


def _unique_strings(value, label):
    if (not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value)
            or len(value) != len(set(value))):
        raise ValueError(label + ' must be unique nonempty strings')
    return value


def mark(inv, reply, protocol, sources):
    """Validate explicit record evidence, then use the existing count engine."""
    if protocol.get('contract') != CONTRACT or protocol.get('rules') != RULES:
        raise ValueError('Unknown EFE alignment protocol')
    if (not isinstance(reply, dict) or set(reply) != {'records', 'cells', 'reference_issues'}
            or any(not isinstance(reply[k], list) for k in reply)
            or any(not isinstance(r, dict) for r in reply['records'])):
        raise ValueError('Invalid EFE whole-task marking envelope')
    rows = {r['id']: r for r in inv['rows']}
    cells = {c['id']: c for c in inv['cells']}
    if (not isinstance(sources, list) or any(not isinstance(s, dict) or
            set(s) != {'id', 'source', 'locator', 'text'} or
            any(not isinstance(v, str) or not v.strip() for v in s.values()) for s in sources)):
        raise ValueError('EFE sources require nonempty ID, source, locator and text')
    source_ids = {s['id'] for s in sources}
    if len(source_ids) != len(sources):
        raise ValueError('EFE source evidence IDs must be unique')
    legacy = copy.deepcopy(reply)
    audits = []
    for record in legacy['records']:
        basis = record.pop('identity_basis', None)
        if (not isinstance(basis, dict) or set(basis) != {
                'rule_id', 'resolution', 'supporting_cells', 'source_evidence', 'conflicts'}
                or basis['rule_id'] not in RULES or basis['resolution'] not in RESOLUTIONS):
            raise ValueError('Each EFE record requires a complete identity basis')
        p, g = record.get('prediction_row'), record.get('reference_row')
        verdict = record.get('verdict')
        resolution = basis['resolution']
        allowed = {'matched': {'same_object', 'equivalent_objects'}, 'missing': {'not_submitted'},
                   'extra': {'surplus_prediction'}, 'uncertain': {'unresolved'}}
        if resolution not in allowed.get(verdict, set()):
            raise ValueError('EFE identity resolution contradicts the record verdict')
        rule_verdicts = {'source_identity': {'matched'}, 'context_identity': {'matched'},
                         'attribute_error': {'matched'}, 'equivalent_objects': {'matched'},
                         'merged_or_missing': {'matched', 'missing'},
                         'surplus_or_nonmatch': {'extra'}, 'unresolved': {'uncertain'}}
        if verdict not in rule_verdicts[basis['rule_id']]:
            raise ValueError('EFE rule contradicts the record verdict')
        support = _unique_strings(basis['supporting_cells'], 'Identity support')
        evidence = _unique_strings(basis['source_evidence'], 'Source evidence')
        if not set(evidence) <= source_ids:
            raise ValueError('Identity evidence must point to supplied frozen sources')
        for cid in support:
            c = cells.get(cid)
            if (c is None or c['row'] not in {p, g} or c['role'] != 'scientific'
                    or not c['nonempty'] or c['field'] in OUTCOME_FIELDS):
                raise ValueError('Identity support requires non-outcome scientific cells in its row pair')
        if verdict == 'matched' and {cells[c]['side'] for c in support} != {'prediction', 'reference'}:
            raise ValueError('Matched identity needs scientific support from both rows')
        conflicts = basis['conflicts']
        if not isinstance(conflicts, list):
            raise ValueError('Identity conflicts must be an explicit list')
        if basis['rule_id'] == 'attribute_error' and not conflicts:
            raise ValueError('The attribute-error rule requires an explicit conflict')
        known = {c['field'] for c in cells.values() if c['row'] in {p, g}}
        seen = set()
        for conflict in conflicts:
            if (not isinstance(conflict, dict) or set(conflict) != {'field', 'handling', 'reason'}
                    or conflict['field'] not in known or conflict['field'] in seen
                    or conflict['handling'] not in {'attribute_error', 'identity_conflict'}
                    or not isinstance(conflict['reason'], str) or not conflict['reason'].strip()):
                raise ValueError('Invalid or repeated identity conflict')
            seen.add(conflict['field'])
            if verdict == 'matched' and conflict['handling'] == 'identity_conflict':
                raise ValueError('An unresolved identity conflict cannot establish a matched object')
            if verdict == 'matched' and conflict['handling'] == 'attribute_error':
                for judgment in reply['cells']:
                    ids = [judgment.get('prediction_cell'), judgment.get('reference_cell')]
                    if any(cid in cells and cells[cid]['row'] in {p, g} and
                           cells[cid]['field'] == conflict['field'] for cid in ids):
                        if judgment.get('verdict') == 'correct':
                            raise ValueError('A declared attribute error cannot receive correct field credit')
        if (resolution == 'equivalent_objects' or verdict == 'matched' and conflicts) and not evidence:
            raise ValueError('Equivalent objects and source-resolved conflicts require source evidence')
        if resolution == 'equivalent_objects' and basis['rule_id'] != 'equivalent_objects':
            raise ValueError('Equivalent objects require their declared rule')
        audits.append({'prediction_row': p, 'reference_row': g,
                       'table': rows.get(p or g, {}).get('table'),
                       **copy.deepcopy(basis), 'reason': record.get('reason'),
                       'evidence_status': 'judge_or_reviewer_assertion_with_validated_pointers'})
    result = mark_all(inv, legacy)
    result['alignment_protocol'] = CONTRACT
    result['alignment_audit'] = audits
    result['alignment_binding'] = {'definition_identity': digest(protocol),
                                   'inventory_identity': digest(inv), 'sources_identity': digest(sources)}
    result['alignment_evidence_validation'] = 'pointer_and_coverage_checks; scientific claims remain reviewable'
    return result


def terminal(inv, protocol, sources):
    """Give terminal empty submissions the existing six-zero treatment."""
    from .task_grading_contract import zero_result
    old = zero_result(inv)
    reply = {'records': copy.deepcopy(old['records']), 'reference_issues': [],
             'cells': [{k: c[k] for k in ('prediction_cell', 'reference_cell', 'category', 'verdict', 'reason')}
                       for c in old['cells']]}
    for r in reply['records']:
        extra = r['verdict'] == 'extra'
        r['identity_basis'] = {'rule_id': 'surplus_or_nonmatch' if extra else 'merged_or_missing',
                               'resolution': 'surplus_prediction' if extra else 'not_submitted',
                               'supporting_cells': [], 'source_evidence': [], 'conflicts': []}
    result = mark(inv, reply, protocol, sources)
    for key in ('field', 'record', 'score_basis', 'grading_method'):
        result[key] = old[key]
    return result


def bundle(packet, result):
    """Export a self-contained, reviewable reply without altering legacy marks."""
    if not packet.get('alignment_definition'):
        return None
    records = copy.deepcopy(result['records'])
    for record, audit in zip(records, result['alignment_audit']):
        record['identity_basis'] = {k: copy.deepcopy(audit[k]) for k in (
            'rule_id', 'resolution', 'supporting_cells', 'source_evidence', 'conflicts')}
    reply = {'records': records, 'reference_issues': copy.deepcopy(result['reference_issues']),
             'cells': [{k: c[k] for k in ('prediction_cell', 'reference_cell', 'category', 'verdict', 'reason')}
                       for c in result['cells']]}
    return {'protocol': CONTRACT, 'inventory': packet['inventory'],
            'alignment_definition': packet['alignment_definition'], 'sources': packet['sources'],
            'reply': reply, 'score_binding': result.get('score_binding'),
            'result_identity': digest(result)}


def review(bundle_path, review_path, out):
    """Apply a complete source-grounded replacement in a new, sealed artifact."""
    from .scoring_input import strict_json
    bundle = strict_json(Path(bundle_path).read_text())
    revision = strict_json(Path(review_path).read_text())
    required = {'prior_bundle_identity', 'reviewer', 'reviewer_type', 'basis', 'reply'}
    if (set(revision) != required or revision['prior_bundle_identity'] != digest(bundle)
            or revision['reviewer_type'] not in {'human', 'codex_source_review', 'automated_judge'}
            or any(not isinstance(revision[k], str) or not revision[k].strip()
                   for k in ('reviewer', 'basis'))):
        raise ValueError('Review must bind the original bundle, actor and source-based rationale')
    result = mark(bundle['inventory'], revision['reply'], bundle['alignment_definition'], bundle['sources'])
    folder = Path(out)
    roots = [Path(bundle_path).resolve().parent, Path(review_path).resolve().parent,
             Path(__file__).resolve().parents[2]]
    if any(folder.resolve().is_relative_to(p) for p in roots):
        raise ValueError('Store protocol reviews outside source and original input directories')
    folder.mkdir(parents=True, exist_ok=False)
    write(folder/'prior.json', bundle)
    write(folder/'review.json', revision)
    write(folder/'result.json', result)
    write(folder/'bundle.json', {**bundle, 'reply': revision['reply'],
                                'prior_bundle_identity': digest(bundle), 'review_identity': digest(revision)})
    seal(folder)
    return {'result': str(folder/'result.json'), 'model_calls': 0,
            'score_basis': result['score_basis'], 'unresolved_items': result['unresolved_items']}
