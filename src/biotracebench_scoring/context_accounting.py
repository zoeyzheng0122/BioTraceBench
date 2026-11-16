"""Versioned accounting for explicitly judged contextual scientific content.

This module never makes a scientific decision. It applies evidence-backed native
judgments to an immutable completed score, keeping the original score intact.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from collections import Counter

from model_conversation.archive import digest
from biotracebench_scoring.evaluation import metrics

FORMAT = 'biotracebench-context-accounting-1'


def apply_context_accounting(score, inventory, sources, decision):
    """Apply a source-supported context classification to one native score.

    ``decision`` identifies the exact base score, source quotations, reference
    fields whose only information is non-required context, and submitted extra
    records that are wholly valid contextual records. Incorrect expressions in
    a suppressed reference field remain predicted extras. Evidence used by
    another field remains available; nothing is deleted from the native audit.
    """
    if decision.get('format') != FORMAT or decision.get('base_score_identity') != digest(score):
        raise ValueError('Context decision does not bind this exact base score')
    if score.get('status') != 'native_scoring_completed' or score.get('unresolved_items') != 0:
        raise ValueError('Context accounting requires a complete native score')
    actor = decision.get('actor')
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError('A decision maker is required')
    source_text = {s['id']: s.get('text', '') for s in sources}
    if len(source_text) != len(sources):
        raise ValueError('Source identities must be unique')
    cells = {c['id']: c for c in inventory['cells']}
    rows = {r['id']: r for r in inventory['rows']}
    items = {i['id']: i for i in score['field_items']}
    records = {r['prediction_row']: r for r in score['record_items'] if r['prediction_row']}

    def evidence(entry):
        if not isinstance(entry.get('reason'), str) or not entry['reason'].strip():
            raise ValueError('Every context decision requires a reason')
        proofs = entry.get('evidence')
        if not isinstance(proofs, list) or not proofs:
            raise ValueError('Every context decision requires source evidence')
        for proof in proofs:
            text = source_text.get(proof.get('source_id'))
            quote = proof.get('quote')
            if not text or not isinstance(quote, str) or not quote.strip() or quote not in text:
                raise ValueError('Context evidence must quote an actual source')

    revised = deepcopy(score)
    revised_items = {i['id']: i for i in revised['field_items']}
    field_changes, row_changes = [], []
    seen_fields, seen_rows = set(), set()
    extra_for_row = Counter()
    for choice in decision.get('reference_context_fields', []):
        evidence(choice)
        fid = choice.get('field_id')
        if fid in seen_fields or fid not in items:
            raise ValueError('Unknown or duplicate reference-context field')
        seen_fields.add(fid)
        old, new = items[fid], revised_items[fid]
        if not old['gold'] or old['verdict'] not in {'correct', 'incorrect', 'missing'}:
            raise ValueError('Reference context must bind one scored reference field')
        classification = choice.get('prediction_class')
        if classification not in {'context', 'incorrect', 'absent'}:
            raise ValueError('An explicit prediction classification is required')
        if (classification == 'absent') == bool(old['predicted']):
            raise ValueError('Prediction classification conflicts with recorded presence')
        is_wrong = classification == 'incorrect'
        new.update({'applicable': False, 'gold': False, 'correct': None,
                    'predicted': bool(is_wrong), 'verdict': 'extra' if is_wrong else 'not_scored',
                    'reason': choice['reason'], 'original_verdict': old['verdict']})
        if is_wrong:
            extra_for_row[old['prediction_row']] += 1
        field_changes.append({'field_id': fid, 'old_verdict': old['verdict'],
                              'new_verdict': new['verdict'], 'prediction_class': classification,
                              'reason': choice['reason'], 'evidence': deepcopy(choice['evidence'])})

    for choice in decision.get('optional_prediction_records', []):
        evidence(choice)
        row = choice.get('prediction_row')
        if row in seen_rows or row not in rows or row not in records:
            raise ValueError('Unknown or duplicate context record')
        seen_rows.add(row)
        if rows[row]['side'] != 'prediction' or records[row]['verdict'] != 'extra':
            raise ValueError('Only unmatched submitted records can be contextual')
        all_cells = {c['id'] for c in cells.values() if c['row'] == row
                     and c['role'] in {'scientific', 'unclassified'} and c['nonempty']}
        if any(cells[c]['role'] == 'unclassified' for c in all_cells):
            raise ValueError('Unclassified content cannot be discarded as context')
        accepted = choice.get('accepted_cells')
        if not isinstance(accepted, list) or len(accepted) != len(set(accepted)) or set(accepted) != all_cells:
            raise ValueError('Context record must explicitly cover every scientific cell')
        row_changes.append({'prediction_row': row, 'accepted_cells': sorted(accepted),
                            'evidence': deepcopy(choice['evidence']), 'reason': choice['reason']})

    revised['residual_extras'] = [x for x in score['residual_extras'] if x['owner_row'] not in seen_rows]
    for record in revised['record_items']:
        p, g = record['prediction_row'], record['reference_row']
        if p in seen_rows:
            record.update({'applicable': False, 'correct': False, 'verdict': 'optional_context'})
            continue
        if p and g:
            own = [i for i in revised['field_items'] if i['reference_row'] == g]
            gold = [i for i in own if i['gold']]
            residual = any(e['owner_row'] == p for e in revised['residual_extras'])
            record['correct'] = bool(gold and all(i['verdict'] in {'correct', 'not_scored'} for i in own)
                                     and not record['schema_missing_fields'] and not residual
                                     and not extra_for_row[p])
    field_tp = sum(x['verdict'] == 'correct' for x in revised['field_items'])
    field_gold = sum(x['gold'] for x in revised['field_items'])
    field_p = sum(x['predicted'] for x in revised['field_items']) + len(revised['residual_extras'])
    # Native diagnostics can contribute unknown or malformed predicted entries.
    original_items_p = sum(x['predicted'] for x in score['field_items']) + len(score['residual_extras'])
    field_p += score['field']['predicted'] - original_items_p
    record_tp = sum(r['correct'] for r in revised['record_items'])
    record_p = score['record']['predicted'] - len(seen_rows)
    if (not 0 <= field_tp <= min(field_p, field_gold) or
            not 0 <= record_tp <= min(record_p, score['record']['gold'])):
        raise ValueError('Context accounting produced invalid score counts')
    revised['field'] = metrics(field_tp, field_p, field_gold)
    revised['record'] = metrics(record_tp, record_p, score['record']['gold'])
    revised['logical'] = {'field': deepcopy(revised['field']), 'record': deepcopy(revised['record'])}
    revised['known_field_counts'] = {'tp': field_tp, 'predicted': field_p, 'gold': field_gold}
    revised['mark_counts'] = dict(Counter(i['verdict'] for i in revised['field_items']) +
                                  Counter({'extra': len(revised['residual_extras'])}))
    revised['gold_field_correctness'] = {i['owner_key']: i['correct'] for i in revised['field_items'] if i['gold']}
    revised['context_accounting'] = {'format': FORMAT, 'base_score_identity': digest(score),
                                     'decision_identity': digest(decision), 'inventory_identity': digest(inventory),
                                     'sources_identity': digest(sources),
                                     'implementation_sha256': sha256(Path(__file__).read_bytes()).hexdigest(), 'actor': actor,
                                     'reference_fields': field_changes, 'optional_records': row_changes}
    revised['score_basis'] = FORMAT
    return revised
