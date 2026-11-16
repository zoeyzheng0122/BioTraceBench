"""Frozen audit denominators, clustered weighting and incomplete-campaign behavior."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from biotracebench_analysis import codex_comparison as comparison
from biotracebench_scoring.task_grading_contract import inventory, mark_all
from biotracebench_scoring import codex_audit_export as exporter
from test_biotracebench_task_grading import reply_for

DICT = {'sample': {'identifier': 'id', 'fields': [{'key': 'id'}, {'key': 'method'}]}}
POLICY = {'reference_contract': 'biotracebench-fixed-reference-1', 'field_roles': {}}
DB = {'sample': [{'id': 'S1', 'method': 'Selected method'}]}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


class ComparisonTests(unittest.TestCase):
    def test_confusion_uses_audit_truth_denominators_and_keeps_uncertainty_separate(self):
        counts = comparison.confusion({'a': True, 'b': False, 'c': False, 'd': True},
                                      {'a': True, 'b': True, 'c': False, 'd': False})
        summary = comparison.confusion_summary(counts)
        self.assertEqual(summary['adjudicated_accepted_n'], 2)
        self.assertEqual(summary['adjudicated_rejected_n'], 2)
        self.assertEqual(summary['false_acceptance_rate'], .5)
        self.assertEqual(summary['false_rejection_rate'], .5)
        pending = comparison.confusion_summary(comparison.confusion({'a': None}, {'a': True}))
        self.assertEqual(pending['unresolved_new'], 1)
        self.assertIsNone(pending['false_rejection_rate'])

    def test_study_and_domain_weights_do_not_give_large_model_groups_extra_weight(self):
        rows = [{'domain': 'clinical', 'case': 'C1', 'x': 10}] * 20
        rows += [{'domain': 'clinical', 'case': 'C2', 'x': 30},
                 {'domain': 'basic', 'case': 'B1', 'x': 100}]
        self.assertEqual(comparison.study_domain_mean(rows, 'x'), 60)
        cluster = [{'domain': d, 'case': case, 'delta_field_f1_pp': value,
                    'delta_record_f1_pp': value} for d, case, value in
                   [('clinical', 'C1', 10), ('clinical', 'C1', -10),
                    ('basic', 'B1', 5), ('basic', 'B1', -5)]]
        intervals = comparison.study_bootstrap(cluster, resamples=100)
        self.assertEqual(intervals, {'field': [0, 0], 'record': [0, 0]})

    def test_inventory_identity_preserves_numeric_value_and_scientific_strings(self):
        original = inventory(DB, DB, DICT, POLICY)
        changed = copy.deepcopy(original)
        original['cells'][0]['value_json'] = '0.10'
        changed['cells'][0]['value_json'] = '0.1'
        self.assertEqual(exporter.inventory_signature(original), exporter.inventory_signature(changed))
        changed['cells'][0]['value_json'] = '0.11'
        self.assertNotEqual(exporter.inventory_signature(original), exporter.inventory_signature(changed))
        original['cells'][0]['value_json'] = '0.123456789012345678901234567891'
        changed['cells'][0]['value_json'] = '0.123456789012345678901234567892'
        self.assertNotEqual(exporter.inventory_signature(original), exporter.inventory_signature(changed))

    def fixture(self, root, incomplete=False, uncertain=False):
        inv = inventory(DB, DB, DICT, POLICY)
        old_positions, new_positions = [], []
        for index, domain in enumerate(('clinical', 'basic'), 1):
            case, model = ('C' if index == 1 else 'B') + '1', 'model'
            audit_verdict = 'correct' if index == 1 else 'incorrect'
            new_verdict = 'incorrect' if index == 1 else 'correct'
            if uncertain and index == 1: new_verdict = 'uncertain'
            audit_reply = reply_for(inv, overrides={'method': audit_verdict})
            audit_packet = {'identity': {'case': case, 'model': model, 'domain': domain, 'stage': 'i0'},
                            'inventory': inv, 'marking': audit_reply}
            write(root / 'audit' / 'adjudicated' / f'Q{index:03d}.json', audit_packet)
            response = reply_for(inv, overrides={'method': new_verdict})
            score = mark_all(inv, response)
            old_score = mark_all(inv, reply_for(inv))
            expected = {level + '_' + metric: old_score[level][metric]
                        for level in comparison.LEVELS for metric in comparison.METRICS}
            old_positions.append({'case': case, 'model': model, 'condition': 'generation',
                                  'domain': domain, 'expected': expected})
            packet_path = root / 'plan' / f'{index}.json'
            write(packet_path, {'payload': {'inventory': inv}})
            result_relative = f'jobs/{index}/result.json'
            write(root / 'new' / result_relative,
                  {'plan_identity': 'plan', 'marking': response, 'score': score})
            new_positions.append({'case': case, 'model': model, 'condition': 'i0', 'domain': domain,
                                  'status': 'waiting' if incomplete and index == 2 else 'complete',
                                  'score': score, 'packet': str(packet_path), 'result': result_relative})
        write(root / 'old.json', {'positions': old_positions})
        write(root / 'new/index.json', {'plan_identity': 'plan', 'positions': new_positions})
        exporter.export(root / 'new/index.json', root / 'audit', root / 'verified.json')

    def test_complete_fixture_replays_scores_and_writes_all_positions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            result = comparison.compare(root / 'old.json', root / 'new/index.json', root / 'audit', root / 'out', root / 'verified.json')
            self.assertEqual(result['status'], 'complete_primary_audit')
            summary = comparison.read(root / 'out/audit_comparison.json')
            self.assertEqual(summary['field']['false_acceptance'], 1)
            self.assertEqual(summary['field']['false_rejection'], 1)
            self.assertEqual(summary['field']['reference_items'], 2)
            self.assertEqual(summary['mean_delta_pp'], {'field': 0, 'record': 0})
            self.assertTrue(comparison.read(root / 'out/grid_summary.json')['full_grid_complete'])
            with (root / 'out/all_position_scores.csv').open() as stream:
                self.assertEqual(sum(1 for _ in stream), 3)

    def test_missing_or_uncertain_primary_produces_only_coverage(self):
        for kwargs in ({'incomplete': True}, {'uncertain': True}):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); self.fixture(root, **kwargs)
                result = comparison.compare(root / 'old.json', root / 'new/index.json', root / 'audit', root / 'out', root / 'verified.json')
                self.assertEqual(result['status'], 'coverage_only')
                self.assertEqual([p.name for p in (root / 'out').iterdir()], ['coverage.json'])

    def test_analysis_requires_validated_unchanged_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            with self.assertRaisesRegex(ValueError, 'scoring-side'):
                comparison.compare(root / 'old.json', root / 'new/index.json', root / 'audit', root / 'out')
            path = root / 'audit/adjudicated/Q001.json'
            path.write_text(path.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'changed after export'):
                comparison.compare(root / 'old.json', root / 'new/index.json', root / 'audit', root / 'out', root / 'verified.json')


if __name__ == '__main__': unittest.main()
