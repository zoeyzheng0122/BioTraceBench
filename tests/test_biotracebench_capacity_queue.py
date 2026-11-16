"""Synthetic queue deferral never generates oversized input or bypasses money."""
import json
import shutil
import unittest

import test_biotracebench_conditions as fixtures
from test_biotracebench import ANSWER
from biotracebench.common import Stop, encoded, read, seal, sha, write
from biotracebench.prompts import SSR
from biotracebench.runner import freeze, increase_limits


class CapacityQueueTests(unittest.TestCase):
    setUp=fixtures.ConditionTests.setUp
    tearDown=fixtures.ConditionTests.tearDown
    execute=fixtures.ConditionTests.execute
    response=fixtures.ConditionTests.response

    def manifest(self, policy='defer_and_continue', tiny_bytes=False, tiny_money=False):
        fixtures.ConditionTests.manifest(self)
        self.frozen.unlink()
        from test_biotracebench import source_fixture
        from biotracebench.materials import prepare
        dataset = self.root / 'dataset'
        shutil.copytree(dataset / 'tasks/basic/B001', dataset / 'tasks/basic/B002')
        shutil.copytree(dataset / 'materials/basic/B001', dataset / 'materials/basic/B002')
        data = read(dataset / 'tasks/basic/B002/task.json'); data.update(case_id='B002', doi='10.synthetic/2')
        write(dataset / 'tasks/basic/B002/task.json', data)
        data = read(dataset / 'materials/basic/B002/materials.json'); data['case']['case_id'] = 'B002'
        write(dataset / 'materials/basic/B002/materials.json', data)
        prompt = dataset / 'tasks/basic/B002/complete-prompt.md'
        prompt.write_text('CAPACITY_SECOND_TASK\n' + prompt.read_text())
        second = self.root / 'prepared2'
        prepare(dataset, 'B002', second)
        draft=read(self.root/'draft.json')
        draft['model'].setdefault('api_limits',{})['provider_max_output_tokens']=8000
        draft.update(capacity_policy=policy)
        draft['tasks'].append({'case_id':'B002','prepared':str(second),'required_reads':[]})
        if tiny_bytes:draft['model']['max_request_bytes']=20
        if tiny_money:
            for stage in draft['budgets'].values():stage['max_cost']='0.000001'
        write(self.root/'draft.json',draft)
        return freeze(self.root/'draft.json',self.frozen)

    def send(self, endpoint, raw, headers, timeout):
        body=json.loads(raw)
        if 'estimate' in endpoint:
            self.provider.estimates+=1
            huge='CAPACITY_SECOND_TASK' not in str(body) and getattr(self,'oversize_first',True)
            return 200,{},encoded({'data':{'total_tokens':100000 if huge else 200}})
        self.wire.append(body)
        ir=any(m.get('content')==SSR for m in body['messages'])
        answer={'graph':{'nodes':[],'edges':[]},'review':{'changes':[],'unresolved':[]},'database':ANSWER} if ir else ANSWER
        return self.response(json.dumps(answer))

    def test_capacity_deferred_other_task_completes_and_replay_is_offline(self):
        self.manifest();result=self.execute()
        self.assertIsNone(result['failure'])
        self.assertEqual(result['queue_status'],'finished_with_deferred_tasks')
        self.assertEqual(result['tasks']['B001']['i0'],'paused_capacity')
        self.assertEqual(result['tasks']['B001']['gsr'],'deferred_capacity')
        self.assertTrue(all(s=='completed' for s in result['tasks']['B002'].values()))
        self.assertEqual(self.provider.completions,3)
        self.assertTrue(all('CAPACITY_SECOND_TASK' in str(b) for b in self.wire))
        self.assertFalse((self.out/'B001/i0/calls/00000/completion').exists())
        count=self.provider.estimates
        replay=self.execute(sender=lambda *a:self.fail('Network used during replay'),offline=True)
        self.assertEqual(replay['tasks'],result['tasks'])
        self.assertEqual(replay['deferred'],result['deferred'])
        self.assertEqual(self.provider.estimates,count)

    def test_stop_policy_still_stops(self):
        self.manifest(policy='stop');result=self.execute()
        self.assertEqual(result['failure']['status'],'paused_capacity')
        self.assertEqual(self.provider.completions,0)
        self.assertTrue(all(s=='not_started' for s in result['tasks']['B002'].values()))

    def test_byte_limit_defers_without_estimator_or_generation(self):
        manifest=self.manifest(tiny_bytes=True)
        self.assertTrue(all(t['capacity_precheck']['status']=='deferred_capacity' for t in manifest['tasks']))
        result=self.execute(sender=lambda *a:self.fail('A local byte failure must not call network'))
        self.assertIsNone(result['failure']);self.assertEqual(len(result['deferred']),2)
        self.assertEqual(self.provider.completions,0);self.assertEqual(self.provider.estimates,0)

    def test_budget_exhaustion_stops_queue_not_treated_as_capacity(self):
        self.oversize_first=False
        self.manifest(tiny_money=True);result=self.execute()
        self.assertEqual(result['failure']['status'],'paused_budget')
        self.assertEqual(result['deferred'],[]);self.assertEqual(self.provider.completions,0)
        self.assertTrue(all(s=='not_started' for s in result['tasks']['B002'].values()))

    def test_ssr_capacity_keeps_initial_and_generic_outputs(self):
        self.oversize_first=False;self.manifest()
        def sender(endpoint,raw,*args):
            value=json.loads(raw)
            if 'estimate' in endpoint and 'CAPACITY_SECOND_TASK' not in str(value) and any(m.get('content')==SSR for m in value['messages']):
                return 200,{},encoded({'data':{'total_tokens':100000}})
            return self.send(endpoint,raw,*args)
        result=self.execute(sender)
        self.assertEqual(result['tasks']['B001']['i0'],'completed')
        self.assertEqual(result['tasks']['B001']['gsr'],'completed')
        self.assertEqual(result['tasks']['B001']['ssr'],'paused_capacity')
        self.assertEqual(read(self.out/'B001/i0/final/database.json'),ANSWER)
        self.assertTrue(all(s=='completed' for s in result['tasks']['B002'].values()))

    def test_all_deferred_tasks_resume_after_byte_limit_extension(self):
        manifest = self.manifest(tiny_bytes=True)
        self.execute(sender=lambda *args: self.fail('No request should fit the byte limit'))
        self.oversize_first = False
        entry = increase_limits(self.frozen, self.out, {'max_request_bytes': 2000000})
        self.assertEqual(entry['reason']['scope'], 'deferred_tasks')
        self.assertEqual(len(entry['reason']['tasks']), 2)
        result = self.execute()
        self.assertIsNone(result['failure'])
        self.assertEqual(result['queue_status'], 'finished')
        self.assertEqual(result['deferred'], [])
        self.assertEqual(self.provider.completions, 6)
        self.assertEqual(read(self.out / 'manifest.json')['max_total_cost'], manifest['max_total_cost'])
        self.assertEqual(read(self.out / 'manifest.json')['budgets'], manifest['budgets'])

    def test_partial_deferral_preserves_completed_task_without_resubmission(self):
        self.manifest()
        result = self.execute()
        self.assertEqual(result['queue_status'], 'finished_with_deferred_tasks')
        completed = {str(p): sha(p) for p in (self.out / 'B002').glob('*/final/*') if p.is_file()}
        increase_limits(self.frozen, self.out, {'context_tokens': 200000, 'max_total_tokens': 200000},
                        targets=['B001/i0','B001/gsr','B001/ssr'])
        result = self.execute()
        self.assertIsNone(result['failure'])
        self.assertEqual(result['deferred'], [])
        self.assertEqual(self.provider.completions, 6)
        self.assertEqual(completed, {p: sha(p) for p in completed})
        self.assertEqual(len(read(self.out / 'costs.json')['calls']), 6)
        self.execute(sender=lambda *args: self.fail('Completed tasks must not issue another request'))
        self.assertEqual(self.provider.completions, 6)

    def test_review_deferral_requires_a_new_paired_round(self):
        self.oversize_first = False
        self.manifest()
        def sender(endpoint, raw, *args):
            body = json.loads(raw)
            if ('estimate' in endpoint and 'CAPACITY_SECOND_TASK' not in str(body)
                    and any(m.get('content') == SSR for m in body['messages'])):
                return 200, {}, encoded({'data': {'total_tokens': 100000}})
            return self.send(endpoint, raw, *args)
        self.execute(sender)
        self.assertEqual(self.provider.completions, 5)
        before = {str(p): sha(p) for p in self.out.glob('*/*/final/*') if p.is_file()}
        with self.assertRaises(Stop) as error:
            increase_limits(self.frozen, self.out, {'context_tokens': 200000, 'max_total_tokens': 200000})
        self.assertEqual(error.exception.status,'review_restart_required')
        from biotracebench.review_retry import prepare
        from biotracebench.runner import run
        from unittest.mock import patch
        target=self.root/'paired-round'
        prepare(self.out,['B001'],{'context_tokens':200000,'max_total_tokens':200000},target)
        with patch.dict('os.environ',{'MOONSHOT_API_KEY':'synthetic'}):
            result=run(target/'manifest.json',target,sender=sender)
        self.assertIsNone(result['failure'])
        self.assertEqual(self.provider.completions, 7)
        self.assertEqual(before, {p: sha(p) for p in before})

    def test_unverified_deferral_and_nontechnical_failures_cannot_extend(self):
        self.manifest(tiny_bytes=True)
        self.execute()
        path = self.out / 'B001/i0/capacity.json'
        value = read(path); value['reason'] = 'Changed record'; write(path, value)
        with self.assertRaises(Stop) as caught:
            increase_limits(self.frozen, self.out, {'max_request_bytes': 2000000})
        self.assertEqual(caught.exception.status, 'tampered')
        self.assertFalse((self.out / 'limit-extensions').exists())
        state = read(self.out / 'status.json')
        state['failure'] = {'status': 'paused_account', 'message': 'Synthetic account stop'}
        write(self.out / 'status.json', state)
        with self.assertRaises(Stop) as caught:
            increase_limits(self.frozen, self.out, {'max_request_bytes': 2000000})
        self.assertEqual(caught.exception.status, 'extension_not_applicable')

    def test_unknown_consumption_blocks_extension_of_a_deferred_queue(self):
        self.manifest(tiny_bytes=True)
        self.execute()
        write(self.out / 'B001/i0/calls/00000/completion/request.json', {'synthetic': 'incomplete attempt'})
        with self.assertRaises(Stop) as caught:
            increase_limits(self.frozen, self.out, {'max_request_bytes': 2000000})
        self.assertEqual(caught.exception.status, 'paused_unknown_cost')
        self.assertFalse((self.out / 'limit-extensions').exists())

    def test_missing_deferred_record_blocks_extension(self):
        self.manifest(tiny_bytes=True)
        self.execute()
        (self.out / 'deferred-capacity.json').unlink()
        with self.assertRaises(Stop) as caught:
            increase_limits(self.frozen, self.out, {'max_request_bytes': 2000000})
        self.assertEqual(caught.exception.status, 'tampered')
        self.assertFalse((self.out / 'limit-extensions').exists())
