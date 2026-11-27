"""Reuse explicit model decisions only under an identical scientific context.

The host validates agreement; it never chooses a verdict or rewrites a reply.
Source-backed accession aliases normalize context only, not the scored cell.
"""
import copy
import json
from model_conversation.archive import digest
from .grading_context import Context
from .scoring_input import strict_json
from .reference_policy import blank

VERSION = 'biotracebench-context-decisions-2'
MEMORY_CATEGORIES = {'scientific', 'identifier', 'provenance', 'out_of_scope', 'uncertain'}
MEMORY_VERDICTS = {'correct', 'incorrect', 'missing', 'extra', 'not_scored', 'uncertain'}
INSTRUCTION = '''Use the supplied frozen source excerpts to assess scientific equivalence. A correct, source-supported alias added inside an already nonempty scientific field is not erroneous merely because the fixed reference did not enumerate that alias. It earns no extra item credit and does not become required in other answers. Verify the same object, accession level, time and relationship; unsupported or contradictory additions remain errors or genuinely unresolved. Preserve every required reference assertion and explicit scientific state. Do not amend reference values or treat content at a blank reference field as a match. Content in a different field does not supply a missing assertion in the evaluated field.
The optional consistency memory contains archived model decisions, not scores, condition labels or human approvals. Apply a decision only to the identical reference object, exact compared cell values and identical scientific context, including relevant conditions and relationships. Context accession aliases are source-backed identity annotations, not replacements for submitted values or judgments of the accession cell itself. Different objects, time, direction, states or context require independent judgment. Never choose the more favorable historical verdict. The host rejects conflicting repeated decisions without changing your response.'''
INSTRUCTION += '''
When frozen_record_alignment is supplied, it restores a previous actual model alignment for the identical complete scientific input into CURRENT inventory row IDs. Copy those row pairs and record verdicts; changing the mapping cannot evade an archived field decision. Reasons may explain the evidence, but neither the host nor the grader may substitute a more favorable historical mapping. Ambiguous object identities do not establish a reusable alignment.
Field consistency is scoped to the complete aligned object row, directly linked objects, and relevant condition/relation rows. An unrelated downstream measurement or another object's edit alone does not change this local scientific context. Related objects, times, directions and association targets remain independent when changed. Do not use another field to fill a missing assertion. Canonical comparison values normalize only declared internal foreign-key targets; the original compared values are retained. Native accession additions remain separately judged. The host checks both classification and verdict, including uncertainty, without rewriting either.'''


def checked_memory(value, sources):
    if value is None:
        return {'version': VERSION, 'context_aliases': [], 'decisions': [], 'alignments': []}
    if (isinstance(value, dict) and value.get('version') == 'biotracebench-context-decisions-1'
            and set(value) == {'version', 'context_aliases', 'decisions'}):
        if value['decisions']:
            raise ValueError('Legacy scientific decisions require recomputation under object context')
        value = {**copy.deepcopy(value), 'version': VERSION, 'alignments': []}
    if (not isinstance(value, dict) or set(value) != {'version', 'context_aliases', 'decisions', 'alignments'}
            or value['version'] != VERSION or not isinstance(value['decisions'], list)
            or not isinstance(value['context_aliases'], list) or not isinstance(value['alignments'], list)):
        raise ValueError('Invalid scientific consistency memory')
    source_ids = {s['id'] for s in sources}
    used = {}
    for alias in value['context_aliases']:
        if (not isinstance(alias, dict) or set(alias) != {'table', 'field', 'values', 'source_ids'}
                or not all(isinstance(alias[k], str) and alias[k] for k in ('table', 'field'))
                or (alias['table'], alias['field']) not in {
                    ('sample', 'sample_accession'), ('assay_run', 'experiment_run_accession')}
                or not isinstance(alias['values'], list) or len(alias['values']) < 2
                or any(not isinstance(v, str) for v in alias['values'])
                or len(set(alias['values'])) != len(alias['values'])
                or not isinstance(alias['source_ids'], list) or not alias['source_ids']
                or any(not isinstance(s,str) or s not in source_ids for s in alias['source_ids'])):
            raise ValueError('Context aliases need explicit values and supplied source evidence')
        for text in alias['values']:
            if not isinstance(json.loads(text), str):
                raise ValueError('Context accession aliases must be text values')
            key = (alias['table'], alias['field'], text)
            group = tuple(sorted(alias['values']))
            if key in used and used[key] != group:
                raise ValueError('Overlapping context alias groups')
            used[key] = group
    seen = set()
    keys = {'key', 'context_identity', 'table', 'reference_row_index', 'field',
            'prediction_value_json', 'reference_value_json', 'prediction_match_json',
            'reference_match_json', 'category', 'verdict', 'reason', 'origin'}
    nullable = {'prediction_value_json', 'reference_value_json',
                'prediction_match_json', 'reference_match_json'}
    for decision in value['decisions']:
        if (not isinstance(decision, dict) or set(decision) != keys
                or decision['verdict'] not in MEMORY_VERDICTS
                or decision['category'] not in MEMORY_CATEGORIES
                or type(decision['reference_row_index']) is not int
                or decision['reference_row_index'] < 0
                or any(not isinstance(decision[k], str) or not decision[k]
                       for k in keys - {'reference_row_index', 'origin'} - nullable)
                or any(decision[k] is not None and not isinstance(decision[k], str) for k in nullable)
                or not isinstance(decision['origin'], dict)
                or set(decision['origin']) != {'request_identity', 'actual_model'}
                or any(not isinstance(v,str) or not v for v in decision['origin'].values())
                or decision['key'] in seen):
            raise ValueError('Invalid or duplicate archived scientific decision')
        expected = digest({k: decision[k] for k in ('context_identity', 'table',
            'reference_row_index', 'field', 'prediction_match_json', 'reference_match_json')})
        if decision['key'] != expected:
            raise ValueError('Scientific decision identity mismatch')
        values = {k: strict_json(decision[k]) if decision[k] is not None else None for k in nullable}
        category, verdict = decision['category'], decision['verdict']
        if category == 'uncertain':
            valid = verdict == 'uncertain'
        elif category != 'scientific':
            valid = verdict == 'not_scored'
        else:
            p, g = (not blank(values[k]) for k in ('prediction_value_json', 'reference_value_json'))
            valid = verdict in ({'correct', 'incorrect', 'uncertain'} if p and g else
                                {'extra'} if p else {'missing'} if g else {'not_scored'})
        if not valid:
            raise ValueError('Archived scientific decision contradicts fixed presence rules')
        seen.add(decision['key'])
    inputs = set()
    for alignment in value['alignments']:
        if (not isinstance(alignment, dict) or set(alignment) != {'input_identity', 'pairs', 'origin'}
                or not isinstance(alignment['input_identity'], str) or not alignment['input_identity']
                or alignment['input_identity'] in inputs or not isinstance(alignment['pairs'], list)
                or not isinstance(alignment['origin'], dict)
                or set(alignment['origin']) != {'request_identity', 'actual_model'}
                or any(not isinstance(x, str) or not x for x in alignment['origin'].values())):
            raise ValueError('Invalid or duplicate archived record alignment')
        used = {'prediction_object': set(), 'reference_object': set()}
        for pair in alignment['pairs']:
            if (not isinstance(pair, dict) or set(pair) != {
                    'prediction_object', 'reference_object', 'verdict', 'reason'}
                    or pair['verdict'] not in {'matched', 'missing', 'extra', 'uncertain'}
                    or not isinstance(pair['reason'], str) or not pair['reason'].strip()):
                raise ValueError('Invalid archived record pair')
            p, g = pair['prediction_object'], pair['reference_object']
            if (p is None and g is None or pair['verdict'] == 'matched' and not (p and g)
                    or pair['verdict'] == 'missing' and (p or not g)
                    or pair['verdict'] == 'extra' and (g or not p)):
                raise ValueError('Archived record verdict contradicts its objects')
            for side in used:
                token = pair[side]
                if token is not None:
                    if not isinstance(token, str) or not token or token in used[side]:
                        raise ValueError('Archived record objects must be unique')
                    used[side].add(token)
        inputs.add(alignment['input_identity'])
    return copy.deepcopy(value)


def context_identity(packet, records=None):
    """Complete scientific input identity, independent of proposed record pairs."""
    if packet.get('request') is None:
        return None
    return Context(packet).input_identity()


def alignment_hint(packet):
    """Restore actual historical model pairs into current IDs, without judging."""
    if packet.get('request') is None:
        return None
    context = Context(packet)
    identity = context.input_identity()
    if identity is None:
        return None
    prior = next((a for a in packet['request']['payload'].get(
        'consistency_memory', {}).get('alignments', []) if a['input_identity'] == identity), None)
    if prior is None:
        return None
    return {'input_identity': identity, 'records': context.restore(prior),
            'origin': copy.deepcopy(prior['origin'])}


def record_alignments(packet, result, context=None):
    if packet.get('request') is None:
        return []
    context = context or Context(packet, result['records'])
    value = context.alignment(result['records'])
    if value is None:
        return []
    value['origin'] = {'request_identity': result.get('request_identity'),
                       'actual_model': result.get('grading_model')}
    return [value]


def decisions(packet, result, context=None):
    if packet.get('request') is None:
        return []
    context = context or Context(packet, result['records'])
    inverse = {g: p for p, g in context.mapped.items()}
    identities = {}
    answer = []
    fixed_non_scientific = {'identifier', 'provenance', 'out_of_scope'}
    for mark in result['cells']:
        p, g = mark['prediction'], mark['reference']
        cells = [c for c in (p, g) if c]
        if not cells or all(c['role'] in fixed_non_scientific for c in cells):
            continue
        # Presence/category rules for declared scientific empty cells are fixed
        # by mark_all. Undeclared classifications also need consistency checks.
        if (all(c['role'] == 'scientific' for c in cells)
                and (not p or not g or not p['nonempty'] or not g['nonempty'])):
            continue
        pr = p['row'] if p else inverse.get(g['row'])
        gr = g['row'] if g else context.mapped.get(p['row'])
        pair = (pr, gr)
        if not pr or not gr:
            continue
        if pair not in identities:
            identities[pair] = context.local_identity(pr, gr)
        identity = identities[pair]
        if identity is None:
            continue
        value = {'context_identity': identity, 'table': context.rows[gr]['table'],
                 'reference_row_index': context.rows[gr]['row_index'], 'field': (g or p)['field'],
                 'prediction_match_json': context.comparison_value(p) if p else None,
                 'reference_match_json': context.comparison_value(g) if g else None}
        value.update(key=digest(value),
                     prediction_value_json=p['value_json'] if p else None,
                     reference_value_json=g['value_json'] if g else None,
                     category=mark['category'], verdict=mark['verdict'], reason=mark['reason'],
                     origin={'request_identity': result.get('request_identity'),
                             'actual_model': result.get('grading_model')})
        answer.append(value)
    return answer


def validate_alignment(packet, records, context=None):
    """Reject changed pairs before cell batches, without selecting new pairs."""
    if packet.get('request') is None:
        return
    context = context or Context(packet, records)
    memory = packet['request']['payload'].get('consistency_memory', {})
    identity = context.input_identity()
    prior_alignment = next((a for a in memory.get('alignments', [])
                            if identity is not None and a['input_identity'] == identity), None)
    if prior_alignment is not None:
        actual = context.alignment(records)
        signature = lambda pairs: sorted((
            {k: p[k] for k in ('prediction_object', 'reference_object', 'verdict')}
            for p in pairs), key=digest)
        if actual is None or signature(actual['pairs']) != signature(prior_alignment['pairs']):
            raise ValueError('Inconsistent repeated scientific record alignment: ' + identity)


def validate_decisions(packet, result):
    """Reject a contradiction; never replace the model's scientific judgment."""
    if packet.get('request') is None:
        return
    context = Context(packet, result['records'])
    validate_alignment(packet, result['records'], context)
    expected = {d['key']: d for d in packet['request']['payload'].get(
        'consistency_memory', {}).get('decisions', [])}
    for actual in decisions(packet, result, context):
        prior = expected.get(actual['key'])
        if prior and (prior['category'], prior['verdict']) != (actual['category'], actual['verdict']):
            raise ValueError('Inconsistent repeated scientific judgment: ' + actual['key'])


def extend_memory(packet, result, memory=None, *, actual_requests=None):
    """Export actual model decisions with provenance after strict marking."""
    from .task_grading_contract import mark_all
    expected_request = digest(packet['request'])
    excluded_binding = set()
    if actual_requests is not None:
        from .task_grading_batches import (PROTOCOL, pair_request, cell_request,
            batches, PAIR_INSTRUCTION, CELL_INSTRUCTION)
        scopes = batches(packet['inventory'], result['records'])
        expected = [pair_request(packet['request']), *[
            cell_request(packet['request'], result['records'], batch) for batch in scopes]]
        if (actual_requests != expected or result.get('grading_method') != PROTOCOL
                or result.get('score_binding', {}).get('prompt_identity') != digest({
                    'records': PAIR_INSTRUCTION, 'cells': CELL_INSTRUCTION})):
            raise ValueError('Staged scientific decisions must bind the exact actual phase requests')
        expected_request = digest(actual_requests)
        excluded_binding.add('prompt_identity')
    if result.get('request_identity') != expected_request:
        raise ValueError('Scientific decisions must bind the exact archived request')
    if any(result.get('score_binding', {}).get(k) != v
           for k,v in packet.get('consistency_scope', {}).items() if k not in excluded_binding):
        raise ValueError('Scientific decision scoring context changed')
    reply = {'records': result['records'], 'reference_issues': result['reference_issues'],
        'cells': [{k:c[k] for k in ('prediction_cell','reference_cell','category','verdict','reason')}
                  for c in result['cells']]}
    checked = mark_all(packet['inventory'], reply)
    if any(checked[k] != result[k] for k in ('cells','records','field','record')):
        raise ValueError('Scientific decisions differ from strict archived marking')
    payload = packet['request']['payload']
    memory = checked_memory(payload.get('consistency_memory') if memory is None else memory,
                            payload['sources'])
    validate_decisions(packet, result)
    known = {d['key']: d for d in memory['decisions']}
    for decision in decisions(packet, result):
        if not all(decision['origin'].values()):
            raise ValueError('Only archived model judgments with request provenance can be shared')
        old = known.get(decision['key'])
        if old and (old['category'], old['verdict']) != (decision['category'], decision['verdict']):
            raise ValueError('Conflicting scientific decisions cannot be merged')
        known.setdefault(decision['key'], decision)
    memory['decisions'] = list(known.values())
    alignments = {a['input_identity']: a for a in memory['alignments']}
    for alignment in record_alignments(packet, result):
        if not all(alignment['origin'].values()):
            raise ValueError('Only actual model alignments with request provenance can be shared')
        old = alignments.get(alignment['input_identity'])
        signature = lambda pairs: sorted((
            {k: p[k] for k in ('prediction_object', 'reference_object', 'verdict')}
            for p in pairs), key=digest)
        if old and signature(old['pairs']) != signature(alignment['pairs']):
            raise ValueError('Conflicting record alignments cannot be merged')
        alignments.setdefault(alignment['input_identity'], alignment)
    memory['alignments'] = list(alignments.values())
    return checked_memory(memory, payload['sources'])
