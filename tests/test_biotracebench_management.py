"""Synthetic execution records and module separation; no real models/gold."""
import ast
import json
import subprocess
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import test_biotracebench_conditions as fixtures
from biotracebench.common import read,write,verify_events,sha
from biotracebench.run_management import execution_state,money_view

ROOT=Path(__file__).resolve().parents[1]

class ManagementTests(unittest.TestCase):
    setUp=fixtures.ConditionTests.setUp
    tearDown=fixtures.ConditionTests.tearDown
    execute=fixtures.ConditionTests.execute
    response=fixtures.ConditionTests.response
    send=fixtures.ConditionTests.send
    manifest=fixtures.ConditionTests.manifest

    def test_management_forks_costs_replay_and_readonly_export(self):
        self.manifest(); result=self.execute()
        self.assertIsNone(result['failure'])
        report=read(self.out/'management/overview.json')
        self.assertEqual([r['execution'] for r in report['rows']],['submitted']*3)
        self.assertEqual([r['answer'] for r in report['rows']],['readable']*3)
        self.assertEqual([r['new_requests_this_session'] for r in report['rows']],[1]*3)
        self.assertEqual(report['forks']['B001']['common_start'],'verified')
        self.assertEqual(len(set(report['forks']['B001']['initial_result_identities'].values())),1)
        costs=read(self.out/'management/cost-ledger.json')
        self.assertTrue(all(r['purpose']=='task_generation' and r['billed_actual'] is None for r in costs['calls']))
        self.assertTrue(all(r['started_at'] and r['ended_at'] for r in costs['calls']))
        self.assertTrue(all(r['actual_model']=='kimi-k3' for r in costs['calls']))
        self.assertEqual(Decimal(costs['workflows']['B001']['experiment_total']['cost_upper']),sum(Decimal(r['budget_upper']) for r in costs['calls']))
        old_id=read(self.out/'management/identity.json')
        originals={str(p):sha(p) for p in self.out.glob('B001/*/final/*') if p.is_file()}
        self.assertIsNone(self.execute(offline=True)['failure'])
        self.assertEqual(self.provider.completions,3)
        self.assertEqual(old_id,read(self.out/'management/identity.json'))
        self.assertEqual([r['new_requests_this_session'] for r in read(self.out/'management/overview.json')['rows']],[0]*3)
        self.assertEqual(originals,{str(p):sha(p) for p in self.out.glob('B001/*/final/*') if p.is_file()})
        verify_events(self.out/'management')
        from biotracebench.cli import main
        before={str(p):sha(p) for p in self.out.rglob('*') if p.is_file()}
        main(['overview','--run',str(self.out),'--out',str(self.root/'overview-export')])
        self.assertEqual(before,{str(p):sha(p) for p in self.out.rglob('*') if p.is_file()})

    def test_identity_tampering_rejected(self):
        self.manifest();self.execute()
        file=self.out/'management/identity.json'; data=read(file);data['run_id']='changed';write(file,data)
        with self.assertRaises(Exception):self.execute(offline=True)

    def test_unknown_is_not_zero_and_state_axes_separate(self):
        values=money_view([{'amount':None,'budget_upper':None}])
        self.assertIsNone(values['tariff_estimate']);self.assertIsNone(values['cost_upper'])
        self.assertEqual(values['unknown_cost_requests'],1)
        self.assertEqual(execution_state('invalid_output','partially_readable'),'submitted')
        self.assertEqual(execution_state('blocked_initial','no_submission'),'blocked_dependency')
        self.assertEqual(execution_state('paused_budget','no_submission'),'paused')
        self.assertEqual(execution_state('not_started','no_submission'),'not_started')

    def test_modules_do_not_load_scoring_during_execution(self):
        code="import sys; import biotracebench.runner; assert 'biotracebench_scoring' not in sys.modules; assert 'biotracebench_analysis' not in sys.modules"
        subprocess.run([sys.executable,'-B','-c',code],check=True,cwd=ROOT)
        from biotracebench_scoring import scoring_judge
        self.assertIn('biotracebench_scoring',scoring_judge.__file__)
        for package in ('model_api','model_conversation','biotracebench_analysis'):
            for p in (ROOT/'src'/package).glob('*.py'):
                tree=ast.parse(p.read_text())
                modules=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
                self.assertFalse(any(x.startswith('biotracebench_scoring') or x.startswith('biotracebench.runner') for x in modules))

    def test_standalone_scoring_and_analysis_are_separate_steps(self):
        from biotracebench.common import seal
        from biotracebench_scoring.__main__ import main as score_main
        from biotracebench_analysis.__main__ import main as analyse_main
        from test_biotracebench_scoring_items import DICT,GOLD,POLICY
        prepared=self.root/'score-prepared';run=self.root/'score-run';gold=self.root/'synthetic-reference'
        write(prepared/'dictionary.json',DICT)
        write(prepared/'materials.json',{'domain':'clinical','study_id':'synthetic-study'})
        receipt=seal(prepared)
        write(run/'manifest.json',{'protocol':'biotracebench-run-2','stages':['i0','gsr','ssr'],
              'tasks':[{'case_id':'SYN','prepared':str(prepared),'material_identity':receipt}]})
        for stage in ['i0','gsr','ssr']:
            write(run/'SYN'/stage/'final/database.json',GOLD);seal(run/'SYN'/stage/'final')
        write(gold/'clinical/SYN/SYN.json',GOLD);write(self.root/'policy.json',POLICY)
        with patch('biotracebench_analysis.statistics.aggregate',side_effect=AssertionError('Scoring must not run statistics')):
            score_main(['score','--run',str(run),'--gold-root',str(gold),'--policy',str(self.root/'policy.json'),'--out',str(self.root/'scores')])
        self.assertFalse((self.root/'scores/summary.json').exists())
        write(self.root/'analysis-config.json',{'bootstrap_seed':20261024,'bootstrap_resamples':10000})
        analyse_main(['--scores',str(self.root/'scores/study-scores.json'),'--config',str(self.root/'analysis-config.json'),'--out',str(self.root/'analysis')])
        self.assertEqual(read(self.root/'analysis/summary.json')['means']['clinical']['i0']['field']['f1'],1)

    def test_notification_deduplicates_completed_event(self):
        from biotracebench.worker import notify_error
        write(self.root/'status.json',{'tasks':{'B001':{'i0':'completed'}},'failure':None})
        with patch('biotracebench.worker.sys.platform','darwin'),patch('biotracebench.worker.subprocess.run') as process:
            process.return_value.returncode=0
            notify_error(self.root,completed=True);notify_error(self.root,completed=True)
            self.assertEqual(process.call_count,1)
        self.assertEqual(read(self.root/'notification.json')['event'],'completed')

if __name__=='__main__':unittest.main()
