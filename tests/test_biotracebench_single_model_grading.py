"""Independent generation runs are graded without coordinating other models."""
import builtins
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_biotracebench_task_grading as fixtures
from biotracebench_scoring import task_grading as grading
from model_conversation.archive import read, write, verify, sha


class SingleModelGradingTests(unittest.TestCase):
    fixture=fixtures.WorkflowTests.fixture
    backend=fixtures.WorkflowTests.backend

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'DASHSCOPE_API_KEY':'fixture-private-grader-only-key'})
        self.env.start()
        write(self.root/'common-gold/basic/SYN/SYN.json',fixtures.GOLD)

    def tearDown(self):
        self.env.stop();self.temp.cleanup()

    def prepare_model(self,name,provider,prediction=None):
        folder=self.root/name
        self.fixture(folder,('i0','gsr','ssr'),prediction=fixtures.GOLD if prediction is None else prediction)
        path=folder/'submission/manifest.json';manifest=read(path)
        # These describe fictional generation runs, never live deployments.
        manifest['model']={'provider':provider,'model':'fixture-generation-'+name}
        write(path,manifest)
        result=grading.prepare(folder/'submission',self.root/'common-gold',folder/'policy.json',
            fixtures.PROFILE,folder/'budget.json',folder/'current-plan',provisional=True)
        self.assertEqual(result['prepared_outputs'],3)
        return folder

    def execute_model(self,folder,calls,mode='valid',forbidden_folder=None):
        original_import=builtins.__import__;original_open=Path.open
        def no_analysis(name,*args,**kwargs):
            if name.startswith('biotracebench_analysis'):
                raise AssertionError('Grading must not import analysis')
            return original_import(name,*args,**kwargs)
        def own_files_only(path,*args,**kwargs):
            mode=str(args[0] if args else kwargs.get('mode','r'))
            if forbidden_folder and ('r' in mode or '+' in mode) and path.resolve().is_relative_to(forbidden_folder.resolve()):
                raise AssertionError('Grading must not read another generation model run')
            return original_open(path,*args,**kwargs)
        with patch.object(builtins,'__import__',no_analysis),patch.object(Path,'open',own_files_only):
            return grading.execute(folder/'current-plan',folder/'scores',backend=self.backend(calls,mode))

    def assert_independent_completion(self,folder,state):
        self.assertEqual(state['status'],'automatic_scoring_completed')
        self.assertEqual(state['graded_outputs'],3)
        scope=state['workflow_scope']
        self.assertFalse(scope['other_model_results_required'])
        self.assertFalse(scope['analysis_required_for_completion'])
        self.assertEqual(scope['cross_model_aggregation'],'outside_scoring')
        self.assertEqual(scope,read(folder/'scores/completion-audit.json')['workflow_scope'])
        self.assertEqual(set(read(folder/'scores/study-scores.json')[0]['conditions']),{'i0','gsr','ssr'})
        for name in ('comparisons.json','summary.json','changes.json','ranking.json'):
            self.assertFalse((folder/'scores'/name).exists())
        verify(folder/'scores')

    def test_one_model_finishes_without_reading_an_unstarted_other_model(self):
        folder=self.prepare_model('first','kimi')
        other=self.root/'other-model'
        write(other/'status.json',{'tasks':{'SYN':{'i0':'not_started','gsr':'not_started','ssr':'not_started'}}})
        write(other/'must-not-read.json',{'content':'Other model data must not enter this grading request.'})
        before=sha(other/'status.json');calls=[]
        state=self.execute_model(folder,calls,forbidden_folder=other)
        self.assert_independent_completion(folder,state)
        self.assertEqual(len(calls),3)
        self.assertEqual(sha(other/'status.json'),before)
        self.assertNotIn('Other model data must not enter',str(calls))

    def test_two_model_runs_get_separate_scores_without_merging_or_regrading(self):
        first=self.prepare_model('first','kimi')
        wrong=copy.deepcopy(fixtures.GOLD);wrong['sample'][0]['value']=61
        second=self.prepare_model('second','openai',wrong)
        calls_a=[];state_a=self.execute_model(first,calls_a,forbidden_folder=second)
        self.assert_independent_completion(first,state_a)
        original={str(p.relative_to(first/'scores')):sha(p) for p in (first/'scores').rglob('*') if p.is_file()}
        calls_b=[];state_b=self.execute_model(second,calls_b,forbidden_folder=first)
        self.assert_independent_completion(second,state_b)
        a=read(first/'scores/study-scores.json')[0]['conditions']
        b=read(second/'scores/study-scores.json')[0]['conditions']
        for stage in ('i0','gsr','ssr'):
            self.assertEqual(a[stage]['field']['f1'],1)
            self.assertEqual(b[stage]['field']['f1'],.5)
            self.assertEqual(b[stage]['mark_counts']['incorrect'],1)
        self.assertEqual(original,{str(p.relative_to(first/'scores')):sha(p) for p in (first/'scores').rglob('*') if p.is_file()})
        self.assertEqual((len(calls_a),len(calls_b)),(3,3))
        with patch.dict(os.environ,{},clear=True):
            recovered=grading.execute(first/'current-plan',first/'scores',offline=True,backend=self.backend(calls_a))
        self.assertEqual(recovered,state_a);self.assertEqual(len(calls_a),3)

    def test_another_models_failed_grading_does_not_block_the_current_model(self):
        failed=self.prepare_model('failed','openai');calls_b=[]
        stopped=self.execute_model(failed,calls_b,mode='bad_json')
        self.assertEqual(stopped['status'],'automatic_scoring_completed_with_errors')
        self.assertEqual(stopped['failed_outputs'],3)
        first=self.prepare_model('first','kimi');calls_a=[]
        state=self.execute_model(first,calls_a,forbidden_folder=failed)
        self.assert_independent_completion(first,state)
        self.assertEqual((len(calls_a),len(calls_b)),(3,3))
