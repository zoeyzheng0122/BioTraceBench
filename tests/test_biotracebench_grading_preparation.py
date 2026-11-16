"""Offline readiness, command status and zero-request grading boundaries."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from model_conversation.archive import read, write, seal, verify, verify_events
from biotracebench_scoring import task_grading as grading
from biotracebench_scoring.__main__ import main
import test_biotracebench_task_grading as fixtures

PROFILE=fixtures.PROFILE


class PreparationTests(unittest.TestCase):
    def fixture(self, root, mode):
        helper=fixtures.WorkflowTests()
        helper.fixture(root,('i0','gsr','ssr'))
        if mode in {'blocked','partial','mixed','partly_blocked'}:
            stages=('i0','gsr','ssr') if mode in {'blocked','mixed'} else ('gsr',)
            for stage in stages:
                final=root/'submission/SYN'/stage/'final'
                write(final/'database.json',None)
                seal(final)
        if mode in {'waiting','partial','mixed','partly_waiting'}:
            stages=('i0','gsr','ssr') if mode=='waiting' else ('ssr',)
            for stage in stages:
                final=root/'submission/SYN'/stage/'final'
                final.rename(final.with_name('saved-final'))
        return helper

    def prepare_cli(self, root, profile=PROFILE):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            code=main(['grade-prepare','--run',str(root/'submission'),
                '--gold-root',str(root/'gold'),'--policy',str(root/'policy.json'),
                '--profile',str(profile),'--budget',str(root/'budget.json'),
                '--out',str(root/'new-plan'),'--provisional'])
        return code,json.loads(output.getvalue())

    def test_real_preparation_cli_reports_distinct_states_and_preserves_diagnostics(self):
        cases={'ready':('preparation_completed',0,3,0,0),
               'partial':('preparation_partial',2,1,1,1),
               'partly_blocked':('preparation_partial',2,2,1,0),
               'partly_waiting':('preparation_partial',2,2,0,1),
               'blocked':('no_ready_outputs',1,0,3,0),
               'waiting':('waiting_for_inputs',3,0,0,3),
               'mixed':('no_ready_outputs',1,0,2,1)}
        for mode,(status,exit_code,ready,blocked,waiting) in cases.items():
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);self.fixture(root,mode)
                with patch.dict('os.environ',{},clear=True),patch('socket.socket',side_effect=AssertionError('Offline only')):
                    code,result=self.prepare_cli(root)
                self.assertEqual(code,exit_code)
                self.assertEqual(result['status'],status)
                self.assertEqual(result['expected_outputs'],3)
                self.assertEqual(result['prepared_outputs'],ready)
                self.assertEqual(result['blocked_outputs'],blocked)
                self.assertEqual(result['waiting_outputs'],waiting)
                self.assertEqual(result['blocked_or_waiting'],blocked+waiting)
                self.assertEqual(result['can_start_grading'],bool(ready))
                self.assertEqual(result['model_calls'],0)
                plan=read(root/'new-plan/plan.json')
                self.assertEqual(len(plan['packets']),ready)
                self.assertEqual(plan['preparation'],read(root/'new-plan/preparation-status.json'))
                for entry in plan['entries']:
                    if entry['status']!='prepared':self.assertTrue(entry['reason'])
                verify(root/'new-plan')

    def test_wrong_input_location_and_capacity_limit_are_non_successful_preparations(self):
        from model_api import load_profile
        for mode in ('missing_file','capacity'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);self.fixture(root,'ready');profile=PROFILE
                if mode=='missing_file':
                    (root/'prepared/instruction.md').rename(root/'saved-instruction.md')
                else:
                    profile=root/'small-profile.json'
                    config=load_profile(PROFILE).describe();config['max_input_bytes']=100
                    write(profile,config)
                with patch('socket.socket',side_effect=AssertionError('No network')):
                    code,result=self.prepare_cli(root,profile)
                self.assertEqual(code,1)
                self.assertEqual(result['prepared_outputs'],0)
                self.assertEqual(result['blocked_outputs'],3)
                entries=read(root/'new-plan/plan.json')['entries']
                for entry in entries:
                    self.assertIn('No such file' if mode=='missing_file' else 'no truncation',entry['reason'])

    def test_zero_ready_execution_and_recovery_do_not_initialize_a_provider_or_finish_scoring(self):
        for mode in ('blocked','waiting','mixed'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);self.fixture(root,mode)
                _,prepared=self.prepare_cli(root)
                # Even unfilled execution budgets are irrelevant to a zero-request diagnostic.
                with (patch.dict('os.environ',{},clear=True),patch('socket.socket',side_effect=AssertionError('No network')),
                     patch.object(grading,'Backend',side_effect=AssertionError('No provider')),
                     patch.object(grading,'_budget',side_effect=AssertionError('No execution reservation'))):
                    result=grading.execute(root/'new-plan',root/'run')
                    recovered=grading.execute(root/'new-plan',root/'run',offline=True)
                self.assertEqual(result,recovered)
                self.assertEqual(result['status'],prepared['status'])
                self.assertEqual(result['model_calls'],0)
                self.assertEqual(result['graded_outputs'],0)
                self.assertFalse(result['automatic_workflow_finished'])
                self.assertNotEqual(grading.command_exit_code(result),0)
                self.assertFalse((root/'run/completion-audit.json').exists())
                self.assertFalse((root/'run/costs.json').exists())
                self.assertFalse((root/'run/attempts').exists())
                for study in read(root/'run/study-scores.json'):
                    self.assertEqual(study['conditions'],{})
                for marking in (root/'run/tasks').glob('*/marking.json'):
                    self.assertIsNone(read(marking)['result'])
                self.assertIn(result['status'],(root/'run/review.html').read_text())
                verify(root/'run');verify_events(root/'run')

    def test_partial_plan_grades_only_ready_output_and_never_invents_other_scores(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);helper=self.fixture(root,'partial')
            code,prepared=self.prepare_cli(root)
            self.assertEqual(code,2);self.assertTrue(prepared['can_start_grading'])
            calls=[]
            with patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
                result=grading.execute(root/'new-plan',root/'run',backend=helper.backend(calls))
            self.assertEqual(len(calls),1)
            self.assertEqual(result['graded_outputs'],1)
            self.assertEqual(result['waiting_outputs'],1)
            self.assertEqual(result['failed_outputs'],1)
            self.assertFalse(result['automatic_workflow_finished'])
            self.assertFalse(result['all_selected_outputs_graded'])
            self.assertFalse(read(root/'run/completion-audit.json')['automatic_workflow_finished'])
            self.assertNotEqual(grading.command_exit_code(result),0)
            study=read(root/'run/study-scores.json')[0]
            self.assertEqual(set(study['conditions']),{'i0'})
            self.assertEqual(study['conditions']['i0']['field']['f1'],1)
            with patch.dict('os.environ',{},clear=True),patch('socket.socket',side_effect=AssertionError('No network')):
                recovered=grading.execute(root/'new-plan',root/'run',offline=True,backend=helper.backend(calls))
            self.assertEqual(result,recovered);self.assertEqual(len(calls),1)

    def test_cli_run_and_recover_return_incomplete_for_zero_ready_plans(self):
        for mode,expected_code in (('blocked',1),('waiting',3)):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);self.fixture(root,mode);self.prepare_cli(root)
                for command in ('grade-run','grade-recover'):
                    args=[command,'--plan',str(root/'new-plan'),'--out',str(root/'run')]
                    if command=='grade-run':args.append('--execute')
                    output=io.StringIO()
                    with contextlib.redirect_stdout(output),patch.dict('os.environ',{},clear=True),patch('socket.socket',side_effect=AssertionError('No network')):
                        code=main(args)
                    result=json.loads(output.getvalue())
                    self.assertEqual(code,expected_code)
                    self.assertEqual(result['graded_outputs'],0)

    def test_partial_completion_keeps_scores_and_distinguishes_blocked_from_waiting(self):
        for mode,status,code in (('partly_blocked','automatic_scoring_completed_with_errors',1),
                                 ('partly_waiting','waiting_for_inputs',3)):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);helper=self.fixture(root,mode);self.prepare_cli(root);calls=[]
                with patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
                    result=grading.execute(root/'new-plan',root/'run',backend=helper.backend(calls))
                self.assertEqual(len(calls),2)
                self.assertEqual(result['graded_outputs'],2)
                self.assertEqual(result['status'],status)
                self.assertEqual(grading.command_exit_code(result),code)
                self.assertFalse(result['all_selected_outputs_graded'])
                self.assertEqual(len(read(root/'run/study-scores.json')[0]['conditions']),2)
                self.assertEqual(len(read(root/'run/costs.json')['requests']),2)


if __name__=='__main__':unittest.main()
