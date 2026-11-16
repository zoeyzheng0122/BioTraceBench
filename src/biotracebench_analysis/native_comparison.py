"""Data-only comparison of validated native Codex logical-field scores.

The scoring exporter supplies replayed scores and current-reference item keys.
Scientific reference bridging belongs to the upstream evidence ledger.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path

from .codex_comparison import confusion, confusion_summary, study_bootstrap, study_domain_mean

FORMAT = 'biotracebench-native-comparison-input-2'
LEVELS = ('field', 'record')
METRICS = ('tp', 'predicted', 'gold', 'precision', 'recall', 'f1')


def _key(row):
    identity = row.get('identity', row)
    stage = identity.get('condition', identity.get('stage'))
    return identity['case'], identity['model'], 'i0' if stage == 'generation' else stage


def _score(value):
    for level in LEVELS:
        score = value[level]
        m, p, g = (score[name] for name in ('tp', 'predicted', 'gold'))
        if any(type(n) is not int or n < 0 for n in (m, p, g)) or m > min(p, g):
            raise ValueError('Invalid exact M/P/G counts')
        expected = {'precision': m / p if p else (1.0 if not g else 0.0),
                    'recall': m / g if g else (1.0 if not p else 0.0),
                    'f1': 2 * m / (p + g) if p + g else 1.0}
        if any(abs(score[name] - number) > 1e-12 for name, number in expected.items()):
            raise ValueError('Score does not agree with exact M/P/G counts')


def _items(row, level):
    length = 4 if level == 'field' else 3
    result = {}
    for item in row[level + '_items']:
        if len(item) != length or type(item[-1]) is not bool:
            raise ValueError('Reference item needs a definite Boolean judgment')
        identity = tuple(item[:-1])
        if identity in result:
            raise ValueError('Repeated current-reference item')
        result[identity] = item[-1]
    if len(result) != row['score'][level]['gold']:
        raise ValueError('Reference item coverage differs from G')
    if sum(result.values()) != row['score'][level]['tp']:
        raise ValueError('Reference item judgments differ from M')
    return result


def summarize(value, *, resamples=10000, seed=20261111):
    """Allow versioned denominator changes and report them explicitly."""
    if value.get('format') != FORMAT or value.get('validation_status') != 'exact_replay_passed':
        raise ValueError('A scoring-side validated native interchange is required')
    if type(resamples) is not int or resamples <= 0:
        raise ValueError('Bootstrap resamples must be a positive integer')
    positions, expected, audit = {}, {}, {}
    for row in value['positions']:
        key = _key(row)
        if key in positions:
            raise ValueError('Duplicate new position')
        if row['status'] == 'complete':
            _score(row['score'])
        positions[key] = row
    for row in value['historical']:
        key = _key(row)
        if key in expected:
            raise ValueError('Duplicate historical position')
        _score(row['score'])
        expected[key] = row
    if set(positions) != set(expected):
        raise ValueError('Full position grid differs from the frozen archive')
    for row in value['audit']:
        key = _key(row)
        if key in audit or key not in expected:
            raise ValueError('Duplicate or unexpected audit position')
        _score(row['score'])
        for level in LEVELS:
            _items(row, level)
        audit[key] = row
    if not audit:
        raise ValueError('An explicit audit comparison set is required')
    missing = [list(k) for k in audit if positions[k]['status'] != 'complete']
    rows, audit_rows, denominator_changes = [], [], []
    counts = {level: Counter() for level in LEVELS}
    compatible_counts = Counter()
    discordant_counts = Counter()
    coverage = Counter()
    for key, row in positions.items():
        coverage[row['status']] += 1
        if row['status'] != 'complete':
            continue
        identity = row.get('identity', row)
        output = {'case': key[0], 'model': key[1], 'condition': key[2], 'domain': identity['domain']}
        for level in LEVELS:
            for metric in METRICS:
                output['new_' + level + '_' + metric] = row['score'][level][metric]
                output['historical_' + level + '_' + metric] = expected[key]['score'][level][metric]
            output['delta_' + level + '_f1_pp'] = 100 * (row['score'][level]['f1'] - expected[key]['score'][level]['f1'])
            for metric in ('predicted', 'gold'):
                if row['score'][level][metric] != expected[key]['score'][level][metric]:
                    denominator_changes.append({'identity': list(key), 'level': level, 'count': metric,
                                                'historical': expected[key]['score'][level][metric],
                                                'new': row['score'][level][metric]})
        rows.append(output)
        if key in audit:
            paired = {k: output[k] for k in ('case', 'model', 'condition', 'domain')}
            for level in LEVELS:
                automatic_items, reference_items = _items(row, level), _items(audit[key], level)
                counts[level].update(confusion(automatic_items, reference_items))
                if level == 'field':
                    flagged = {tuple(item) for item in audit[key].get('reference_discordant_items', [])}
                    if not flagged <= set(reference_items):
                        raise ValueError('Reference-discordance stratum contains an unknown logical item')
                    for subset, counter in ((set(reference_items) - flagged, compatible_counts),
                                            (flagged, discordant_counts)):
                        counter.update(confusion({k: automatic_items[k] for k in subset},
                                                 {k: reference_items[k] for k in subset}))
                paired['delta_' + level + '_f1_pp'] = 100 * (audit[key]['score'][level]['f1'] - row['score'][level]['f1'])
                paired['automatic_' + level] = row['score'][level]
                paired['reference_' + level] = audit[key]['score'][level]
            audit_rows.append(paired)
    report = {'format': 'biotracebench-native-comparison-report-2',
              'protocol': value['protocol'], 'expected_positions': len(expected),
              'coverage': dict(coverage), 'audit_expected': len(audit), 'audit_missing': missing,
              'audit_status': 'incomplete' if missing else 'complete',
              'denominator_changes': denominator_changes,
              'historical_comparison_basis': 'Versioned physical versus logical counting; counts may change.',
              'parameters': {'resamples': resamples, 'seed': seed,
                             'weights': 'Equal studies within domains; equal domains.',
                             'bootstrap': 'Studies resampled within domain, retaining all paired models.',
                             'study_order': 'Case ascending within each domain; independent of file row order.',
                             'interval': '95% percentile, linear interpolation.'},
              'calibration_status': 'Rules developed with the human audit; calibration comparison.',
              'audit_provenance': value.get('audit_provenance', {}), 'rows': rows,
              'audit_rows': audit_rows, 'model_summaries': []}
    groups = defaultdict(list)
    for row in rows:
        groups[row['model'], row['condition']].append(row)
    for (model, condition), group in sorted(groups.items()):
        summary = {'model': model, 'condition': condition, 'completed_positions': len(group),
                   'expected_positions': sum(k[1:] == (model, condition) for k in expected)}
        summary['status'] = 'complete' if summary['completed_positions'] == summary['expected_positions'] else 'incomplete'
        for level in LEVELS:
            for metric in ('precision', 'recall', 'f1'):
                mean = study_domain_mean(group, 'new_' + level + '_' + metric)
                summary[level + '_' + metric] = mean if summary['status'] == 'complete' else None
                summary['observed_' + level + '_' + metric] = mean
        report['model_summaries'].append(summary)
    if not missing:
        report['audit_confusion'] = {level: confusion_summary(v) for level, v in counts.items()}
        report['reference_compatible_field_confusion'] = confusion_summary(compatible_counts)
        report['reference_discordant_field_confusion'] = confusion_summary(discordant_counts)
        report['reference_discordance_note'] = (
            'The primary audit retains all selected human/source judgments. The separately '
            'declared stratum identifies differences between frozen reference conventions '
            'and source-adjudicated audit targets; it is not automatically a semantic-judge error. '
            'Primary paired F1 differences retain those items and their original denominators.')
        report['f1_differences_pp'] = {level: study_domain_mean(audit_rows, 'delta_' + level + '_f1_pp') for level in LEVELS}
        ordered = sorted(audit_rows, key=lambda row: (row['domain'], row['case'], row['model']))
        report['f1_intervals_pp'] = study_bootstrap(ordered, resamples=resamples, seed=seed)
    return report


def compare(path, out, *, resamples=10000, seed=20261111):
    path, out = Path(path), Path(out)
    raw = path.read_bytes()
    value = json.loads(raw)
    for file, expected in value.get('source_sha256', {}).items():
        if hashlib.sha256(Path(file).read_bytes()).hexdigest() != expected:
            raise ValueError('Validated scientific input changed after export')
    report = summarize(value, resamples=resamples, seed=seed)
    report['input_sha256'] = hashlib.sha256(raw).hexdigest()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    for name in ('rows', 'audit_rows', 'model_summaries', 'denominator_changes'):
        records = report[name]
        if records:
            columns = list(dict.fromkeys(k for row in records for k in row))
            with (out / (name + '.csv')).open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader(); writer.writerows(records)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verified-input', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--resamples', type=int, default=10000)
    parser.add_argument('--seed', type=int, default=20261111)
    args = parser.parse_args(argv)
    report = compare(args.verified_input, args.out, resamples=args.resamples, seed=args.seed)
    print(json.dumps({k: report[k] for k in ('expected_positions', 'coverage', 'audit_status')}))


if __name__ == '__main__':
    main()
