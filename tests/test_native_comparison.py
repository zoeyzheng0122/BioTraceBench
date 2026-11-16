import copy
import unittest

from biotracebench_analysis.native_comparison import FORMAT, summarize


def metric(m, p, g):
    return {'tp': m, 'predicted': p, 'gold': g,
            'precision': m / p if p else 0.0, 'recall': m / g if g else 0.0,
            'f1': 2 * m / (p + g) if p + g else 0.0}


def fixture():
    value = {'format': FORMAT, 'validation_status': 'exact_replay_passed',
             'protocol': 'synthetic-logical-2', 'positions': [], 'historical': [], 'audit': []}
    for case, domain, new, audit in [('B1', 'basic', [True, False], [True, True]),
                                     ('C1', 'clinical', [True, False], [False, False])]:
        identity = {'case': case, 'model': 'synthetic-model', 'condition': 'i0', 'domain': domain}
        row = {'identity': identity, 'status': 'complete',
               'score': {'field': metric(sum(new), 2, 2), 'record': metric(0, 1, 1)},
               'field_items': [['result', 0, 'value', new[0]], ['result', 0, 'method', new[1]]],
               'record_items': [['result', 0, False]]}
        value['positions'].append(row)
        value['historical'].append({'identity': identity,
                                    'score': {'field': metric(0, 3, 3), 'record': metric(0, 1, 1)}})
        ref = copy.deepcopy(row)
        ref['score']['field'] = metric(sum(audit), 2, 2)
        ref['field_items'] = [['result', 0, 'value', audit[0]], ['result', 0, 'method', audit[1]]]
        value['audit'].append(ref)
    return value


class NativeComparisonTests(unittest.TestCase):
    def test_recounts_reference_denominators_and_preserves_accounting_changes(self):
        report = summarize(fixture(), resamples=20)
        fields = report['audit_confusion']['field']
        self.assertEqual(fields['adjudicated_accepted_n'], 2)
        self.assertEqual(fields['adjudicated_rejected_n'], 2)
        self.assertEqual(fields['false_acceptance'], 1)
        self.assertEqual(fields['false_rejection'], 1)
        self.assertEqual(fields['false_acceptance_rate'], .5)
        self.assertEqual(fields['false_rejection_rate'], .5)
        self.assertEqual(len(report['denominator_changes']), 4)
        self.assertEqual(report['f1_differences_pp']['field'], 0)

    def test_incomplete_calibration_has_coverage_and_no_accuracy_estimate(self):
        data = fixture(); data['positions'][0]['status'] = 'waiting'
        result = summarize(data, resamples=20)
        self.assertEqual(result['audit_status'], 'incomplete')
        self.assertEqual(len(result['audit_missing']), 1)
        self.assertNotIn('audit_confusion', result)

    def test_rejects_unvalidated_counts_and_missing_grid(self):
        data = fixture(); data['validation_status'] = 'unchecked'
        with self.assertRaises(ValueError): summarize(data)
        data = fixture(); data['positions'][0]['score']['field']['tp'] = 3
        with self.assertRaises(ValueError): summarize(data)
        data = fixture(); data['positions'].pop()
        with self.assertRaises(ValueError): summarize(data)

    def test_rejects_unknown_duplicate_or_differently_bridged_reference_items(self):
        for change in ('unknown', 'duplicate', 'identity'):
            data = fixture()
            row = data['positions'][0]
            if change == 'unknown': row['field_items'][0][-1] = None
            elif change == 'duplicate': row['field_items'][1] = row['field_items'][0].copy()
            else: row['field_items'][0][1] = 99
            with self.assertRaises(ValueError): summarize(data)

    def test_bootstrap_preserves_pairs_and_replays_seed(self):
        first = summarize(fixture(), resamples=100, seed=20261111)
        second = summarize(fixture(), resamples=100, seed=20261111)
        self.assertEqual(first['f1_intervals_pp'], second['f1_intervals_pp'])
        self.assertEqual(first['f1_intervals_pp']['field'], [0, 0])

    def test_empty_targets_retain_the_existing_perfect_empty_score(self):
        data = fixture()
        for rows in (data['positions'], data['historical'], data['audit']):
            for row in rows:
                row['score'] = {level: {'tp': 0, 'predicted': 0, 'gold': 0,
                    'precision': 1.0, 'recall': 1.0, 'f1': 1.0} for level in ('field', 'record')}
                row['field_items'] = []; row['record_items'] = []
        report = summarize(data, resamples=20)
        self.assertIsNone(report['audit_confusion']['field']['false_acceptance_rate'])
        self.assertEqual(report['f1_differences_pp']['field'], 0)

    def test_source_discordance_is_reported_without_changing_primary_audit(self):
        data = fixture()
        data['audit'][0]['reference_discordant_items'] = [['result', 0, 'method']]
        report = summarize(data, resamples=20)
        self.assertEqual(report['audit_confusion']['field']['false_rejection'], 1)
        self.assertEqual(report['reference_discordant_field_confusion']['false_rejection'], 1)
        self.assertEqual(report['reference_compatible_field_confusion']['false_rejection'], 0)
        self.assertEqual(report['f1_differences_pp']['field'], 0)
        data['audit'][0]['reference_discordant_items'].append(['result', 99, 'method'])
        with self.assertRaises(ValueError): summarize(data)


if __name__ == '__main__':
    unittest.main()
