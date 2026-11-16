"""Batch proposals, one human check round, and offline completion gates."""
import copy
import csv
import html
import json
import sys
from pathlib import Path
from model_conversation.archive import read, read_exact, write, digest, sha, seal, verify
from .evaluation import score, metrics

PROTOCOL = 'biotracebench-scoring-completion-1'


def implementation():
    from model_conversation import archive
    return {'files': {p.name: sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
            'archive': sha(Path(archive.__file__)), 'python': sys.version}


def save_overview(folder, status):
    write(Path(folder)/'scoring-overview.json', status)
    with (Path(folder)/'scoring-overview.csv').open('w', encoding='utf-8', newline='') as stream:
        columns = ['case_id','condition','status','pending_items','reason','no_usable_output','error_type']
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(status['outputs'])


def overview(entries):
    counts = {s: sum(e['status'] == s for e in entries) for s in
              ('pending', 'awaiting_human_review', 'completed', 'blocked')}
    return {'protocol': PROTOCOL, 'expected_outputs': len(entries), 'counts': counts,
            'status': 'completed' if entries and counts['completed'] == len(entries) else
                      'blocked' if counts['blocked'] else 'awaiting_human_review' if counts['awaiting_human_review'] else 'pending',
            'completed_zero_output': sum(e['status'] == 'completed' and e.get('no_usable_output', False) for e in entries),
            'outputs': entries, 'analysis_status': 'not_requested'}


def save_round(folder, expected, capsules, studies):
    """Keep exact scientific inputs outside source distribution for offline replay."""
    write(Path(folder)/'replay-inputs.json', {'protocol': PROTOCOL, 'implementation': implementation(),
                                           'expected': expected, 'capsules': capsules})
    save_overview(folder, overview(expected))
    seal(folder)


def prepare(bundle, out, judge_plan=None, judge_run=None):
    bundle = Path(bundle).resolve()
    identity = verify(bundle)
    replay = read_exact(bundle/'replay-inputs.json')
    if replay['protocol'] != PROTOCOL or replay['implementation'] != implementation():
        raise ValueError('Use the frozen scorer implementation for this scoring round')
    studies = read_exact(bundle/'study-scores.json')
    scores = {(s['case_id'], stage): r for s in studies for stage, r in s['conditions'].items()}
    suggestions, judge_identity = {}, None
    if bool(judge_plan) != bool(judge_run):
        raise ValueError('Supply both judge plan and completed judge run')
    if judge_plan:
        jp, jr = Path(judge_plan), Path(judge_run)
        plan_identity, run_identity = verify(jp), verify(jr)
        plan = read(jp/'plan.json')
        if read(jr/'plan-identity.json') != plan_identity or plan['scores_identity'] != digest(studies):
            raise ValueError('Judge batch belongs to different scoring inputs')
        proposals = read(jr/'proposals.json')
        routes = read(jp/'routes.json')
        if (read(jr/'status.json')['status'] != 'awaiting_human_review'
                or len(proposals) != len(routes) or {p['id'] for p in proposals} != set(routes)):
            raise ValueError('Finish the complete judge batch before starting human review')
        judge_identity = {'plan': plan_identity, 'run': run_identity}
        for proposal in proposals:
            route = routes[proposal['id']]
            suggestions[(route['context_id'], route['item_id'])] = proposal
    packets, templates, routes = [], [], {}
    for entry in replay['expected']:
        key = (entry['case_id'], entry['condition'])
        result = scores.get(key)
        pid = digest({'bundle': identity, 'output': list(key)})
        semantic = []
        if result:
            for q in result['adjudication_queue']:
                if q['kind'] not in {'text_equivalence', 'state_equivalence'}:
                    continue
                field = q.get('field', '')
                if field.endswith(('_id', '_ids', '_accession')) or field in {'relationship','result_unit','factor_unit','population_size','factor_value'}:
                    continue
                proposal = suggestions.get((result['context_id'], q['id']))
                if proposal is None:
                    raise ValueError('Complete all eligible Qwen proposals before the human check round')
                semantic.append({'item_id': q['id'], 'proposal': proposal})
        packets.append({'id': pid, 'case_id': entry['case_id'], 'execution': entry.get('reason'),
                        'items': result.get('scoring_items', {}) if result else {},
                        'alignment': result.get('alignment_audit', {}) if result else {},
                        'queue': result.get('adjudication_queue', []) if result else [],
                        'diagnostics': result.get('diagnostics', []) if result else [],
                        'proposals': semantic})
        templates.append({'id': pid, 'approve': False, 'reviewer': '', 'reviewed_at': '', 'basis': '',
                          'no_usable_output': False, 'adjudications': {},
                          'semantic_reviews': [{'item_id': p['item_id'], 'proposal_identity': digest(p['proposal']),
                                                'equal': None, 'basis': ''} for p in semantic]})
        routes[pid] = {'case_id': entry['case_id'], 'condition': entry['condition'],
                       'context': result.get('context_id') if result else None}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    write(out/'plan.json', {'protocol': PROTOCOL, 'bundle': str(bundle), 'bundle_identity': identity,
                           'judge_identity': judge_identity, 'implementation': implementation()})
    write(out/'review-packets.json', sorted(packets, key=lambda p: p['id']))
    write(out/'review-template.json', sorted(templates, key=lambda p: p['id']))
    write(out/'private-routes.json', routes)
    sections = ''.join('<details><summary>' + html.escape(p['case_id'] + ' / ' + p['id']) +
                       '</summary><pre>' + html.escape(json.dumps(p, ensure_ascii=False, indent=2, default=str)) +
                       '</pre></details>' for p in sorted(packets, key=lambda p: p['id']))
    (out/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>Scoring human check</title>'
        '<style>body{max-width:1100px;margin:2rem auto;font:16px system-ui}pre{white-space:pre-wrap;overflow-wrap:anywhere}'
        'details{padding:1rem;border:1px solid #ddd;margin:1rem 0}</style>'
        '<h1>Scoring human check</h1><p>Review each output and its proposals. '
        'Record decisions in a separate copy of review-template.json. No scores or condition labels are shown.</p>'+sections,
        encoding='utf-8')
    seal(out)
    return {'outputs': len(packets), 'status': 'awaiting_human_review', 'model_calls': 0}


def _merge(target, incoming):
    allowed = {'field_states', 'projections', 'matches', 'equivalences', 'unit_equivalences'}
    if not isinstance(incoming, dict) or set(incoming) - allowed:
        raise ValueError('Unsupported manual adjudication category')
    for category, values in incoming.items():
        if not isinstance(values, dict):
            raise ValueError('Adjudication categories must be mappings')
        dest = target.setdefault(category, {})
        for key, value in values.items():
            if key in dest and dest[key] != value:
                raise ValueError('Conflicting adjudications; do not overwrite earlier decisions')
            dest[key] = copy.deepcopy(value)


def finalize(plan_folder, reviews_file, out):
    plan_folder = Path(plan_folder)
    review_identity = verify(plan_folder)
    plan = read(plan_folder/'plan.json')
    bundle = Path(plan['bundle'])
    verify(bundle, plan['bundle_identity'])
    if plan['protocol'] != PROTOCOL or plan['implementation'] != implementation():
        raise ValueError('Use the frozen scoring implementation for completion')
    replay = read_exact(bundle/'replay-inputs.json')
    routes = read(plan_folder/'private-routes.json')
    packets = {p['id']: p for p in read(plan_folder/'review-packets.json')}
    by_key, seen = {}, set()
    for review in read_exact(reviews_file):
        pid = review.get('id')
        if pid not in routes or pid in seen:
            raise ValueError('Unknown or duplicate output review')
        seen.add(pid)
        if (type(review.get('approve')) is not bool or type(review.get('no_usable_output')) is not bool
                or not all(isinstance(review.get(k), str) and review[k].strip() for k in ('reviewer','reviewed_at','basis'))):
            raise ValueError('Each human check requires approval, reviewer, time and basis')
        route = routes[pid]
        by_key[(route['case_id'],route['condition'])] = review
    updated, entries, accepted, audit = [], [], {'contexts': {}}, []
    capsules = {(c['case_id'], c['condition']): c for c in replay['capsules']}
    for entry in replay['expected']:
        key = (entry['case_id'], entry['condition'])
        cap, review = capsules.get(key), by_key.get(key)
        if cap is None:
            entries.append(entry)
            continue
        base = score(cap['prediction'], cap['gold'], cap['dictionary'], cap['policy'], cap['decisions'], context=cap['scope'])
        if digest(base) != cap['result_identity']:
            raise ValueError('Original offline score replay differs; completion is blocked')
        decisions = copy.deepcopy(cap['decisions'] or {'contexts': {}})
        target = decisions['contexts'].setdefault(base['context_id'], {})
        if review:
            _merge(target, review.get('adjudications', {}))
            available = {p['item_id']: p['proposal'] for p in packets[review['id']]['proposals']}
            item_seen = set()
            for item in review.get('semantic_reviews', []):
                qid = item.get('item_id')
                if qid not in available or qid in item_seen or item.get('proposal_identity') != digest(available[qid]):
                    raise ValueError('Unknown, duplicate or stale semantic review')
                item_seen.add(qid)
                if 'equal' not in item or item['equal'] is not None and type(item['equal']) is not bool:
                    raise ValueError('Semantic decision must be boolean or unresolved null')
                if item['equal'] is not None:
                    if not isinstance(item.get('basis'), str) or not item['basis'].strip():
                        raise ValueError('Confirmed semantic decision requires a basis')
                    _merge(target, {'equivalences': {qid: {'equal': item['equal'], 'basis': item['basis'],
                           'reviewer': review['reviewer'], 'reviewed_at': review['reviewed_at'],
                           'judge_proposal': digest(available[qid])}}})
        result = score(cap['prediction'], cap['gold'], cap['dictionary'], cap['policy'], decisions, context=cap['scope'])
        repeated = score(cap['prediction'], cap['gold'], cap['dictionary'], cap['policy'], decisions, context=cap['scope'])
        if digest(result) != digest(repeated):
            raise ValueError('Final score replay differs')
        for level in ('field', 'record'):
            m = result[level]
            if not 0 <= m['tp'] <= min(m['predicted'], m['gold']) or metrics(m['tp'], m['predicted'], m['gold']) != m:
                raise ValueError('Inconsistent scoring counts')
        intake = cap['intake']
        unreadable = intake['availability'] == 'unreadable_requires_review'
        no_output = intake['availability'] == 'terminal_no_output' or unreadable and bool(review and review['no_usable_output'])
        if review and review['no_usable_output'] and not unreadable and intake['availability'] != 'terminal_no_output':
            raise ValueError('Human review cannot discard a usable submitted answer')
        approved = bool(review and review['approve'])
        complete = approved and not result['adjudication_queue'] and (not unreadable or no_output)
        result['comparison_status'] = result['status']
        result['completion_status'] = 'completed' if complete else 'awaiting_human_review'
        result['status'] = 'final_under_frozen_dictionary' if complete else 'provisional'
        result['submission_intake'] = intake
        if unreadable and not no_output:
            result['adjudication_queue'].append({'kind':'unreadable_submission','id':digest(intake),'intake':intake})
        entries.append({**entry, 'status':result['completion_status'], 'no_usable_output':no_output,
                        'pending_items':len(result['adjudication_queue']),
                        'reason':None if complete else 'human_check_or_adjudication_pending'})
        updated.append({'case_id':key[0], 'study_id':cap['study_id'], 'domain':cap['domain'],
                        'condition':key[1], 'result':result})
        previous = accepted['contexts'].setdefault(base['context_id'], {})
        _merge(previous, target)
        audit.append({'output':list(key), 'review':review, 'original_replay_verified':True,
                      'final_replay_verified':True, 'final_score_identity':digest(result)})
    studies = {}
    for item in updated:
        study = studies.setdefault(item['case_id'], {'case_id':item['case_id'], 'study_id':item['study_id'],
                                     'domain':item['domain'], 'conditions':{}, 'changes':{}})
        study['conditions'][item['condition']] = item['result']
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    status = overview(entries)
    write(out/'study-scores.json', list(studies.values()))
    save_overview(out, status)
    write(out/'adjudications.json', accepted)
    write(out/'completion-audit.json', {'protocol':PROTOCOL, 'review_plan_identity':review_identity,
          'bundle_identity':plan['bundle_identity'], 'judge_identity':plan['judge_identity'],
          'implementation':implementation(), 'checks':audit, 'model_calls':0})
    seal(out)
    return status
