"""Account for partially valid contextual records without erasing errors."""
from collections import Counter
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from model_conversation.archive import digest
from biotracebench_scoring.evaluation import metrics

FORMAT = 'biotracebench-partial-context-accounting-1'


def apply_partial_context_accounting(score, inventory, sources, decision):
    """Exclude individually reviewed valid context cells, retaining wrong cells.

    The reviewer explicitly partitions every scientific cell of each unmatched
    record into valid context and incorrect content. The record and incorrect
    residual cells continue to count as predictions. A cell already consumed as
    evidence is not removed from another field and cannot be called an extra.
    """
    if decision.get('format') != FORMAT or decision.get('base_score_identity') != digest(score):
        raise ValueError('Decision does not bind the exact base score')
    actor = decision.get('actor')
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError('Decision maker is required')
    if score.get('status') != 'native_scoring_completed' or score.get('unresolved_items') != 0:
        raise ValueError('A complete native or context score is required')
    source_text = {s['id']: s.get('text', '') for s in sources}
    if len(source_text) != len(sources):
        raise ValueError('Source identities must be unique')
    cells = {c['id']: c for c in inventory['cells']}
    rows = {r['id']: r for r in inventory['rows']}
    records = {r['prediction_row']: r for r in score['record_items'] if r['prediction_row']}
    residual = {e['cell']: e for e in score['residual_extras']}
    chosen, seen, changes = set(), set(), []
    for item in decision.get('partial_context_records', []):
        row = item.get('prediction_row')
        if row in seen or row not in rows or row not in records:
            raise ValueError('Unknown or duplicate context record')
        seen.add(row)
        if rows[row]['side'] != 'prediction' or records[row]['verdict'] != 'extra':
            raise ValueError('Partially valid context must be an unmatched prediction')
        if not isinstance(item.get('reason'), str) or not item['reason'].strip():
            raise ValueError('Context classification requires a reason')
        proofs = item.get('evidence')
        if not isinstance(proofs, list) or not proofs:
            raise ValueError('Source evidence is required')
        for proof in proofs:
            text = source_text.get(proof.get('source_id'))
            quote = proof.get('quote')
            if not text or not isinstance(quote, str) or not quote.strip() or quote not in text:
                raise ValueError('Evidence must quote an actual source')
        owner = {c['id'] for c in cells.values() if c['row'] == row
                 and c['role'] in {'scientific', 'unclassified'} and c['nonempty']}
        if any(cells[c]['role'] == 'unclassified' for c in owner):
            raise ValueError('Unclassified content cannot be discarded')
        valid, wrong = item.get('valid_context_cells'), item.get('incorrect_cells')
        if (not isinstance(valid, list) or not isinstance(wrong, list) or not wrong
                or len(valid) != len(set(valid)) or len(wrong) != len(set(wrong))
                or set(valid) & set(wrong) or set(valid) | set(wrong) != owner):
            raise ValueError('Classify every nonempty scientific cell exactly once')
        if not set(wrong) <= set(residual):
            raise ValueError('Each incorrect cell must remain an independently counted residual')
        remove = set(valid) & set(residual)
        chosen.update(remove)
        changes.append({'prediction_row': row, 'valid_context_cells': sorted(valid),
                        'incorrect_cells': sorted(wrong), 'excluded_residual_cells': sorted(remove),
                        'reason': item['reason'], 'evidence': deepcopy(proofs)})
    result = deepcopy(score)
    result['residual_extras'] = [x for x in result['residual_extras'] if x['cell'] not in chosen]
    counts = score['field']
    result['field'] = metrics(counts['tp'], counts['predicted'] - len(chosen), counts['gold'])
    result['logical']['field'] = deepcopy(result['field'])
    result['known_field_counts'] = {'tp': result['field']['tp'], 'predicted': result['field']['predicted'],
                                    'gold': result['field']['gold']}
    mark_counts = Counter(result['mark_counts'])
    mark_counts['extra'] -= len(chosen)
    if mark_counts['extra'] < 0:
        raise ValueError('Context exclusions exceeded recorded extras')
    result['mark_counts'] = dict(mark_counts)
    result['partial_context_accounting'] = {
        'format': FORMAT, 'base_score_identity': digest(score), 'decision_identity': digest(decision),
        'inventory_identity': digest(inventory), 'sources_identity': digest(sources),
        'implementation_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
        'actor': actor, 'records': changes,
    }
    result['score_basis'] = FORMAT
    return result
