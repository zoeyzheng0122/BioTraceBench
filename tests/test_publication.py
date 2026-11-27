"""Scoring contracts exercised with synthetic values."""
import importlib.util
from importlib.resources import files
import unittest
from biotracebench_analysis.replay.demo import fixture, supplied_judgment
from biotracebench_analysis.replay.scoring import projected
from biotracebench_scoring.task_grading_contract import inventory, mark_all
from model_conversation.archive import exact_json

class PublicationTests(unittest.TestCase):

    def test_distribution_module_boundary(self):
        for name in ('biotracebench_scoring.evaluation', 'biotracebench_scoring.scoring'):
            with self.subTest(module=name):
                self.assertIsNone(importlib.util.find_spec(name))

    def test_compatibility_imports_share_the_implementation(self):
        from biotracebench_analysis.publication.scoring import projected as old_projected
        from biotracebench_analysis.publication.score_output import prepare as old_prepare
        from biotracebench_analysis.replay.score_output import prepare
        self.assertIs(old_projected, projected)
        self.assertIs(old_prepare, prepare)

    def test_frozen_protocol_identifiers(self):
        from biotracebench_analysis.replay.score_output import (
            CONTRACT, STATE_CONTRACT, PREVIOUS_CONTRACT, LEGACY_CONTRACT)
        self.assertEqual((LEGACY_CONTRACT, PREVIOUS_CONTRACT, STATE_CONTRACT, CONTRACT), (
            'biotracebench-publication-i0-1', 'biotracebench-publication-review-2',
            'biotracebench-publication-review-3', 'biotracebench-publication-review-4'))

    def test_resource_aliases_are_byte_identical(self):
        package = files('biotracebench')
        for directory in ('scoring', 'schemas'):
            original = package/'publication_configs'/directory
            current = package/'review_configs'/directory
            self.assertEqual({p.name for p in original.iterdir()}, {p.name for p in current.iterdir()})
            for resource in original.iterdir():
                with self.subTest(resource=resource.name):
                    self.assertEqual(resource.read_bytes(), (current/resource.name).read_bytes())

    def setUp(self):
        self.dic, self.policy, self.gold, self.pred = fixture()
        self.inv = inventory(self.pred, self.gold, self.dic, self.policy)
        self.reply = supplied_judgment(self.inv)

    def test_whole_fields_and_complete_records(self):
        mark_all(self.inv, self.reply)
        score = projected(self.inv, self.reply, 'SYNTHETIC')
        self.assertEqual([score['field'][x] for x in ['tp', 'predicted', 'gold']], [4, 5, 6])
        self.assertEqual([score['record'][x] for x in ['tp', 'predicted', 'gold']], [1, 2, 2])

    def test_missing_cell_cannot_be_finalized(self):
        self.reply['cells'].pop()
        with self.assertRaises(ValueError):
            mark_all(self.inv, self.reply)

    def test_duplicate_mark_cannot_be_finalized(self):
        self.reply['cells'].append(self.reply['cells'][0])
        with self.assertRaises(ValueError):
            mark_all(self.inv, self.reply)

    def test_explicit_null_is_missing_for_a_reported_fact(self):
        self.pred['population'][0]['population_size'] = None
        inv = inventory(self.pred, self.gold, self.dic, self.policy)
        r = supplied_judgment(inv)
        self.assertEqual(projected(inv, r, 'SYNTHETIC')['field']['tp'], 3)

    def test_zero_reference_targets_are_undefined(self):
        masks = [{'case': 'SYNTHETIC', 'table': 'population', 'row_index': i, 'field_exclusions': ['*'], 'main_record_scoring': 'excluded'} for i in range(2)]
        x = projected(self.inv, self.reply, 'SYNTHETIC', masks)
        for level in ['field', 'record']:
            for metric in ['precision', 'recall', 'f1']:
                self.assertIsNone(x[level][metric])

    def test_empty_field_reference_with_extra_predictions_is_undefined(self):
        for row in self.gold['population']:
            for field in ('population_name', 'population_size', 'intervention'):
                row[field] = None
        inv = inventory(self.pred, self.gold, self.dic, self.policy)
        reply = supplied_judgment(inv)
        mark_all(inv, reply)
        self.assertEqual(projected(inv, reply, 'SYNTHETIC')['field'], {
            'tp': 0, 'predicted': 5, 'gold': 0,
            'precision': None, 'recall': None, 'f1': None,
        })

    def test_lexical_number_precision_survives(self):
        self.assertEqual(str(exact_json('{"value":2.00}')['value']), '2.00')
