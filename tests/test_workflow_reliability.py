"""Manuscript scoring boundaries and unresolved analysis, using synthetic data."""
import copy
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from model_conversation.archive import read, write, seal
from biotracebench_analysis.statistics import aggregate, compare_conditions
from biotracebench_analysis.__main__ import main as analyze
from biotracebench_scoring import task_grading as grading
from biotracebench_scoring.task_grading_contract import inventory, mark_all
from test_biotracebench_task_grading import DICT, GOLD, POLICY, PROFILE, reply_for
import test_biotracebench_task_grading as fixtures


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.network = patch.object(socket, 'socket', side_effect=AssertionError('Live network forbidden'))
        self.network.start()
        self.addCleanup(self.network.stop)

    def result(self, overrides=None, prediction=None):
        inv = inventory(GOLD if prediction is None else prediction, GOLD, DICT, POLICY)
        result = mark_all(inv, reply_for(inv, overrides=overrides))
        result['status'] = 'provisional'
        return result

    def study(self, result, domain='basic', identity='synthetic'):
        return {'study_id': identity, 'case_id': identity, 'domain': domain,
                'conditions': {s: copy.deepcopy(result) for s in ('i0', 'gsr', 'ssr')}}

    def test_all_nine_transitions_keep_uncertainty_separate(self):
        values = (True, False, None)
        before, after = {}, {}
        for i, a in enumerate(values):
            for j, b in enumerate(values):
                before[f'{i}:{j}'] = a
                after[f'{i}:{j}'] = b
        result = compare_conditions({'gold_field_correctness': before}, {'gold_field_correctness': after})
        self.assertEqual(set(result['transitions'].values()), {1})
        self.assertEqual(result['uncertain_transitions'], 5)
        for key in ('corrected', 'persistent_error', 'regressed', 'stable_correct'):
            self.assertEqual(result[key], 1)

    def test_uncertain_judgments_produce_analysis_and_review_list(self):
        result = self.result({'label': 'uncertain'})
        studies = [self.study(result), self.study(result, 'clinical', 'second')]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root/'scores.json', studies)
            write(root/'config.json', {'bootstrap_seed': 20261024, 'bootstrap_resamples': 10000})
            self.assertEqual(analyze(['--scores', str(root/'scores.json'), '--config', str(root/'config.json'),
                                      '--out', str(root/'analysis')]), 0)
            summary = read(root/'analysis/summary.json')
            self.assertEqual(summary['uncertainty']['groups']['overall']['i0']['uncertain_fields'], 2)
            self.assertEqual(summary['uncertainty']['groups']['overall']['i0']['uncertain_records'], 0)
            self.assertEqual(summary['means']['overall']['i0']['field']['f1'], .5)
            self.assertEqual(len(read(root/'analysis/pending-review.json')), 6)

    def test_unknown_denominator_propagates_without_dropping_studies(self):
        valid = self.study(self.result())
        unknown = self.study(self.result(), 'clinical', 'unknown')
        unknown['conditions']['gsr']['field'] = None
        result = aggregate([valid, unknown])
        self.assertIsNone(result['means']['overall']['gsr']['field']['f1'])
        self.assertIsNone(result['paired_differences']['overall:field:gsr-i0']['mean'])
        self.assertEqual(result['coverage']['clinical']['gsr']['field']['expected_studies'], 1)
        self.assertEqual(result['coverage']['clinical']['gsr']['field']['available_studies'], 0)
        self.assertEqual(result['means']['overall']['i0']['field']['f1'], 1)

    def test_missing_condition_is_reported_without_manufactured_zero(self):
        study = self.study(self.result())
        del study['conditions']['ssr']
        study['outputs'] = {'i0': 'completed', 'gsr': 'completed', 'ssr': 'waiting_for_input'}
        result = aggregate([study])
        self.assertIsNone(result['means']['basic']['ssr']['field']['f1'])
        self.assertEqual(result['uncertainty']['groups']['basic']['ssr']['unavailable_outputs'], 1)

    def test_malformed_record_retains_readable_content_and_record_denominator(self):
        prediction = copy.deepcopy(GOLD)
        prediction['sample'].insert(0, 'malformed')
        inv = inventory(prediction, GOLD, DICT, POLICY)
        self.assertEqual(next(r for r in inv['rows'] if r['side'] == 'prediction')['row_index'], 1)
        result = mark_all(inv, reply_for(inv))
        self.assertEqual(result['known_field_counts']['tp'], 2)
        self.assertIsNone(result['field'])
        self.assertEqual(result['record']['tp'], 1)
        self.assertEqual(result['record']['predicted'], 2)
        self.assertEqual(result['record']['f1'], 2/3)
        self.assertEqual(result['structural_diagnostics'][0]['value_json'], '"malformed"')

    def test_bad_table_preserves_another_table_and_marks_unknown_record_count(self):
        prediction = {**copy.deepcopy(GOLD), 'unknown_table': {'broken': 'table'}}
        inv = inventory(prediction, GOLD, DICT, POLICY)
        result = mark_all(inv, reply_for(inv))
        self.assertEqual(result['known_field_counts']['tp'], 2)
        self.assertIsNone(result['record'])
        self.assertIsNone(result['field'])

    def test_wrong_field_type_is_delivered_unchanged(self):
        prediction = copy.deepcopy(GOLD)
        prediction['sample'][0]['value'] = {'unusable': [1, 2]}
        inv = inventory(prediction, GOLD, DICT, POLICY)
        value = next(c for c in inv['cells'] if c['side'] == 'prediction' and c['field'] == 'value')
        self.assertEqual(json.loads(value['value_json']), {'unusable': [1, 2]})
        self.assertEqual(mark_all(inv, reply_for(inv))['record']['tp'], 0)

    def test_invalid_reference_is_an_input_error(self):
        with self.assertRaisesRegex(ValueError, 'Reference'):
            inventory(GOLD, {'sample': ['bad reference row']}, DICT, POLICY)

    def test_conditions_from_different_review_rounds_cannot_be_combined(self):
        study = self.study(self.result())
        for stage in ('i0','gsr','ssr'):
            study['conditions'][stage]['score_binding']={'run_manifest_identity':'same-round'}
        study['conditions']['ssr']['score_binding']['run_manifest_identity']='other-round'
        with self.assertRaisesRegex(ValueError,'one explicit run'):
            aggregate([study])

    def test_terminal_unreadable_answer_scores_zero_without_client_or_budget(self):
        helper = fixtures.WorkflowTests()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            helper.fixture(root)
            final = root/'submission/SYN/i0/final'
            write(final/'database.json', None)
            write(final/'output-assessment.json', {'final_response_received': True})
            (final/'raw-answer.txt').write_text('Unreadable final answer.')
            seal(final)
            write(root/'budget.json', {})
            prepared = grading.prepare(root/'submission', root/'gold', root/'policy.json', PROFILE,
                                       root/'budget.json', root/'zero-plan', provisional=True)
            self.assertEqual(prepared['prepared_outputs'], 1)
            with patch.object(grading, 'Backend', side_effect=AssertionError('No provider client for local zeros')):
                state = grading.execute(root/'zero-plan', root/'scores', offline=True)
            self.assertEqual(state['graded_outputs'], 1)
            result = read(root/'scores/study-scores.json')[0]['conditions']['i0']
            for level in ('field', 'record'):
                for metric in ('precision', 'recall', 'f1'):
                    self.assertEqual(result[level][metric], 0)
            self.assertEqual(read(root/'scores/completion-audit.json')['generated_requests'], 0)
            self.assertEqual(read(root/'scores/costs.json')['exact_cny'], '0')

    def test_terminal_absent_answer_scores_zero_locally(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixtures.WorkflowTests().fixture(root, terminal=True)
            with patch.object(grading, 'Backend', side_effect=AssertionError('No model call')):
                state = grading.execute(root/'plan', root/'scores', offline=True)
            self.assertEqual(state['graded_outputs'], 1)

    def test_local_report_recovers_after_a_partial_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            fixtures.WorkflowTests().fixture(root,terminal=True)
            from biotracebench_scoring import task_grading_report as reports
            original=reports._atomic_text
            def fail_after_scoring(path, content, **kwargs):
                marking=path.parent/'marking.json'
                if marking.exists() and read(marking)['result'] is not None:
                    raise OSError('Synthetic report failure')
                return original(path,content,**kwargs)
            with patch.object(reports,'_atomic_text',side_effect=fail_after_scoring):
                with self.assertRaises(OSError):
                    grading.execute(root/'plan',root/'scores',offline=True)
            self.assertTrue(list((root/'scores/tasks').glob('*/marking.json')))
            self.assertEqual(read(next((root/'scores/tasks').glob('*/marking.json')))['result']['field']['f1'],0)
            with patch.object(grading,'Backend',side_effect=AssertionError('No model needed for local recovery')):
                state=grading.execute(root/'plan',root/'scores',offline=True)
            self.assertEqual(state['graded_outputs'],1)
            self.assertTrue(list((root/'scores/tasks').glob('*/cells.csv')))
            self.assertTrue(list((root/'scores/tasks').glob('*/review.html')))

    def test_partial_output_runs_through_grading_and_analysis(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ',{'DASHSCOPE_API_KEY':'fixture-grader-private-key'}):
            root=Path(tmp)
            prediction=copy.deepcopy(GOLD)
            prediction['sample'].append('unreadable row')
            helper=fixtures.WorkflowTests()
            helper.fixture(root,stages=('i0','gsr','ssr'),prediction=prediction)
            calls=[]
            result=grading.execute(root/'plan',root/'scores',backend=helper.backend(calls))
            self.assertEqual(result['graded_outputs'],3)
            self.assertEqual(len(calls),3)
            write(root/'config.json',{'bootstrap_seed':20261024,'bootstrap_resamples':10000})
            analyze(['--scores',str(root/'scores/study-scores.json'),'--config',str(root/'config.json'),
                     '--out',str(root/'analysis')])
            summary=read(root/'analysis/summary.json')
            self.assertIsNone(summary['means']['basic']['i0']['field']['f1'])
            self.assertEqual(summary['means']['basic']['i0']['record']['f1'],2/3)
            self.assertEqual(summary['uncertainty']['groups']['basic']['i0']['structural_issues'],1)

    def test_archive_conflict_is_not_scored_as_a_model_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            fixtures.WorkflowTests().fixture(root)
            write(root/'submission/SYN/i0/final/database.json',None)
            write(root/'submission/status.json',{'tasks':{'SYN':{'i0':'invalid_output'}}})
            result=grading.prepare(root/'submission',root/'gold',root/'policy.json',PROFILE,
                                  root/'budget.json',root/'conflict-plan',provisional=True)
            self.assertEqual(result['prepared_outputs'],0)
            self.assertEqual(result['blocked_outputs'],1)

    def test_local_zeros_are_retained_when_other_outputs_lack_execution_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            fixtures.WorkflowTests().fixture(root,stages=('i0','gsr','ssr'))
            final=root/'submission/SYN/i0/final'
            write(final/'database.json',None)
            write(final/'output-assessment.json',{'final_response_received':True})
            seal(final)
            write(root/'budget.json',{})
            grading.prepare(root/'submission',root/'gold',root/'policy.json',PROFILE,
                            root/'budget.json',root/'mixed-plan',provisional=True)
            with self.assertRaises(ValueError):
                grading.execute(root/'mixed-plan',root/'scores',offline=True)
            scores=read(root/'scores/study-scores.json')
            self.assertEqual(scores[0]['conditions']['i0']['field']['f1'],0)
            self.assertEqual(set(scores[0]['conditions']),{'i0'})
            self.assertEqual(read(root/'scores/status.json')['status'],'paused')

    def test_cancelled_or_paused_execution_is_not_a_terminal_model_zero(self):
        for status in ('cancelled', 'terminated', 'paused_unknown_cost', 'paused_account'):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                fixtures.WorkflowTests().fixture(root, terminal=True)
                write(root/'submission/status.json', {'tasks':{'SYN':{'i0':status}}})
                result = grading.prepare(root/'submission', root/'gold', root/'policy.json', PROFILE,
                    root/'budget.json', root/'pending-plan', provisional=True)
                self.assertEqual(result['prepared_outputs'], 0)
                self.assertEqual(result['waiting_outputs'], 1)


if __name__ == '__main__':
    unittest.main()
