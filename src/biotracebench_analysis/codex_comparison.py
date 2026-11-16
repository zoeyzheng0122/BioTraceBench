"""Frozen-reference comparisons of a new Codex campaign and its calibration audit."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import random

LEVELS = ('field', 'record')
METRICS = ('tp', 'predicted', 'gold', 'precision', 'recall', 'f1')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stage(value):
    return 'i0' if value == 'generation' else value


def key(row):
    return row['case'], row['model'], stage(row.get('condition', row.get('stage')))


def _write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def _csv(path, rows):
    if not rows:
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader(); writer.writerows(rows)


def confusion(new, audit):
    if set(new) != set(audit):
        raise ValueError('New and audit reference items differ')
    result = Counter()
    for item, actual in audit.items():
        if actual is None:
            raise ValueError('Frozen audit contains an unresolved scientific judgment')
        predicted = new[item]
        result['unresolved_new' if predicted is None else
               'both_correct' if predicted and actual else
               'false_acceptance' if predicted else
               'false_rejection' if actual else 'both_incorrect'] += 1
    return result


def confusion_summary(counts):
    out = {k: counts[k] for k in ('both_correct', 'false_acceptance', 'false_rejection', 'both_incorrect', 'unresolved_new')}
    out['reference_items'] = sum(counts.values())
    rejected = counts['false_acceptance'] + counts['both_incorrect']
    accepted = counts['false_rejection'] + counts['both_correct']
    out.update(adjudicated_rejected_n=rejected, adjudicated_accepted_n=accepted,
               false_acceptance_rate=counts['false_acceptance'] / rejected if rejected else None,
               false_rejection_rate=counts['false_rejection'] / accepted if accepted else None)
    if counts['unresolved_new']:
        out.update(false_acceptance_rate=None, false_rejection_rate=None)
    return out


def study_domain_mean(rows, value):
    """Equal domain means of equal study means, retaining all models per study."""
    studies = defaultdict(list)
    for row in rows:
        studies[row['domain'], row['case']].append(row[value])
    domains = defaultdict(list)
    for (domain, _), values in studies.items():
        domains[domain].append(sum(values) / len(values))
    if not domains:
        return None
    return sum(sum(v) / len(v) for v in domains.values()) / len(domains)


def percentile(values, q):
    values = sorted(values)
    position = (len(values) - 1) * q
    lo, hi = math.floor(position), math.ceil(position)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)


def study_bootstrap(rows, resamples=10000, seed=20261111):
    studies = defaultdict(list)
    for row in rows:
        studies[row['domain'], row['case']].append(row)
    domains = {d: [k for k in studies if k[0] == d] for d in ('clinical', 'basic')}
    if any(not v for v in domains.values()):
        raise ValueError('Audit intervals require both domains')
    means = {k: {level: sum(r['delta_' + level + '_f1_pp'] for r in group) / len(group)
                 for level in LEVELS} for k, group in studies.items()}
    rng = random.Random(seed); samples = {level: [] for level in LEVELS}
    for _ in range(resamples):
        draws = {d: [rng.choice(keys) for _ in keys] for d, keys in domains.items()}
        for level in LEVELS:
            samples[level].append(sum(sum(means[k][level] for k in keys) / len(keys)
                                      for keys in draws.values()) / len(draws))
    return {level: [percentile(v, .025), percentile(v, .975)] for level, v in samples.items()}


def _expected_score(row):
    expected = row['expected']
    return {level: {metric: expected[level + '_' + metric] for metric in METRICS} for level in LEVELS}


def _same_score(stored, actual):
    return all(stored[level][metric] == actual[level][metric] for level in LEVELS for metric in METRICS)


def compare(old_manifest, new_index, audit_dir, out, verified_input=None):
    old_manifest, new_index, out = Path(old_manifest), Path(new_index), Path(out)
    old, new = read(old_manifest), read(new_index)
    original = {key(r): r for r in old['positions']}
    if len(original) != len(old['positions']):
        raise ValueError('Duplicate old position')
    routes = {key(r): r for r in new['positions']}
    if len(routes) != len(new['positions']) or set(routes) - set(original):
        raise ValueError('Duplicate or unexpected new campaign position')
    if verified_input is None:
        raise ValueError('Run the scoring-side codex_audit_export preflight and supply --verified-input')
    verified = read(verified_input)
    if (verified.get('format') != 'biotracebench-codex-audit-interchange-1'
            or verified.get('new_index_sha256') != sha(new_index)
            or verified.get('plan_identity') != new.get('plan_identity')):
        raise ValueError('Verified interchange differs from the selected campaign')
    fingerprints = verified['source_sha256']
    if any(sha(path) != fingerprint for path, fingerprint in fingerprints.items()):
        raise ValueError('Validated audit/scoring input changed after export')
    audit = {key(item['identity']): item for item in verified['audit']}
    if len(audit) != len(verified['audit']):
        raise ValueError('Duplicate frozen audit identity')
    validations = {key(item): item for item in verified['positions']}
    loaded, coverage, all_rows = {}, [], []
    for identity, old_row in original.items():
        route = routes.get(identity)
        status, reason = 'waiting', 'Position not completed'
        score = None
        if route and route.get('status') == 'complete':
            try:
                validation = validations[identity]
                value = verified['jobs'][validation['validation_key']]
                if value.get('error'):
                    raise ValueError(value['error'])
                score = value['score']
                if not _same_score(route['score'], score):
                    raise ValueError('Index score differs from validated interchange')
                old_score = _expected_score(old_row)
                if any(score[level][metric] != old_score[level][metric]
                       for level in LEVELS for metric in ('gold', 'predicted')):
                    raise ValueError('New scoring changed fixed reference/submission denominators')
                if score.get('unresolved_items'):
                    status, reason = 'provisional', 'Unresolved new scientific judgments'
                else:
                    status, reason = 'complete', ''
                loaded[identity] = value
            except (ValueError, KeyError, OSError, TypeError) as error:
                status, reason, score = 'invalid', str(error), None
        row = {'case': identity[0], 'model': identity[1], 'stage': identity[2],
               'domain': old_row['domain'], 'status': status, 'reason': reason}
        coverage.append(row.copy())
        if score is not None:
            old_score = _expected_score(old_row)
            for level in LEVELS:
                for metric in METRICS:
                    row['new_' + level + '_' + metric] = score[level][metric]
                    row['old_' + level + '_' + metric] = old_score[level][metric]
                row['delta_' + level + '_f1_pp'] = 100 * (score[level]['f1'] - old_score[level]['f1'])
        all_rows.append(row)
    primary = audit
    primary_missing = [k for k in primary if not any(key(r) == k and r['status'] == 'complete' for r in coverage)]
    out.mkdir(parents=True, exist_ok=False)
    report = {'expected_positions': len(original), 'indexed_positions': len(routes),
              'status_counts': dict(Counter(r['status'] for r in coverage)),
              'primary_audit_expected': len(primary), 'primary_audit_missing_or_provisional': primary_missing,
              'positions': coverage,
              'inputs': {'old_manifest': str(old_manifest), 'old_manifest_sha256': sha(old_manifest),
                         'new_index': str(new_index), 'new_index_sha256': sha(new_index),
                         'verified_input': str(verified_input), 'verified_input_sha256': sha(verified_input),
                         'validated_source_sha256': fingerprints}}
    _write(out / 'coverage.json', report)
    if primary_missing:
        return {'status': 'coverage_only', 'missing_primary_outputs': len(primary_missing), 'out': str(out)}
    if not primary:
        raise ValueError('No initial-generation audit outputs')
    paired, details, counts = [], [], {level: Counter() for level in LEVELS}
    for identity, human in primary.items():
        value = loaded[identity]
        score = value['score']
        if value['inventory_signature'] != human['inventory_signature']:
            raise ValueError('Audit and new inventory differ for ' + str(identity))
        human_score = human['score']
        row = {**human['identity'], 'answer_id': human['answer_id']}
        for level in LEVELS:
            new_items = {tuple(item[:-1]): item[-1] for item in value[level + '_items']}
            audit_items = {tuple(item[:-1]): item[-1] for item in human[level + '_items']}
            cc = confusion(new_items, audit_items); counts[level].update(cc)
            for item, actual in audit_items.items():
                predicted = new_items[item]
                state = next(iter(confusion({item: predicted}, {item: actual})))
                details.append({**{k: row[k] for k in ('answer_id', 'case', 'model', 'stage', 'domain')},
                                'level': level, 'reference_item': str(item),
                                'new_correct': predicted, 'adjudicated_correct': actual, 'comparison': state})
            for metric in METRICS:
                row['new_' + level + '_' + metric] = score[level][metric]
                row['adjudicated_' + level + '_' + metric] = human_score[level][metric]
            row['delta_' + level + '_f1_pp'] = 100 * (human_score[level]['f1'] - score[level]['f1'])
        paired.append(row)
    audit_root = Path(audit_dir); audit_root = audit_root.parent if audit_root.name == 'adjudicated' else audit_root
    baseline = read(audit_root / 'audit_summary.json')['i0'] if (audit_root / 'audit_summary.json').exists() else None
    summary = {'status': 'complete_primary_audit', 'outputs': len(paired),
               'field': confusion_summary(counts['field']), 'record': confusion_summary(counts['record']),
               'mean_F1': {role + '_' + level: study_domain_mean(paired, role + '_' + level + '_f1')
                           for role in ('new', 'adjudicated') for level in LEVELS},
               'mean_delta_pp': {level: study_domain_mean(paired, 'delta_' + level + '_f1_pp') for level in LEVELS},
               'delta_95pct_study_bootstrap_pp': study_bootstrap(paired),
               'old_baseline': baseline,
               'estimation': {'weights': 'Equal studies within equally weighted domains; all sampled model outputs retained per study',
                              'resamples': 10000, 'seed': 20261111, 'quantiles': 'linear',
                              'comparison': 'Frozen audit minus new Codex scoring; calibration comparison, not held-out validation'}}
    if baseline:
        for level in LEVELS:
            for metric in ('reference_items', 'adjudicated_rejected_n', 'adjudicated_accepted_n'):
                if summary[level][metric] != baseline[level][metric]:
                    raise ValueError('Frozen audit denominator changed: ' + level + ':' + metric)
    groups = defaultdict(list)
    for row in all_rows:
        for group in [('stage', row['stage']), ('model_stage', row['model'], row['stage']),
                      ('domain_stage', row['domain'], row['stage']),
                      ('model_domain_stage', row['model'], row['domain'], row['stage'])]:
            groups[group].append(row)
    aggregates = []
    for group, rows in sorted(groups.items()):
        item = {'group': '|'.join(group), 'expected_positions': len(rows),
                'complete_positions': sum(r['status'] == 'complete' for r in rows),
                'status': 'complete' if all(r['status'] == 'complete' for r in rows) else 'incomplete'}
        for version in ('old', 'new'):
            for level in LEVELS:
                for metric in ('precision', 'recall', 'f1'):
                    name = version + '_' + level + '_' + metric
                    item[name] = study_domain_mean(rows, name) if item['status'] == 'complete' else None
        aggregates.append(item)
    _write(out / 'audit_comparison.json', summary)
    _write(out / 'grid_summary.json', {'full_grid_complete': all(r['status'] == 'complete' for r in all_rows), 'groups': aggregates})
    _csv(out / 'paired_audit_scores.csv', paired)
    _csv(out / 'audit_item_comparison.csv', details)
    _csv(out / 'all_position_scores.csv', all_rows)
    _csv(out / 'group_summary.csv', aggregates)
    if any(sha(path) != fingerprint for path, fingerprint in fingerprints.items()):
        raise ValueError('Frozen audit input changed during comparison')
    return {'status': summary['status'], 'outputs': len(paired),
            'false_acceptance': summary['field']['false_acceptance'],
            'false_rejection': summary['field']['false_rejection'],
            'mean_delta_pp': summary['mean_delta_pp'], 'out': str(out)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('old-manifest', 'new-index', 'audit-dir', 'out', 'verified-input'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(compare(args.old_manifest, args.new_index, args.audit_dir, args.out, args.verified_input), ensure_ascii=False))


if __name__ == '__main__': main()
