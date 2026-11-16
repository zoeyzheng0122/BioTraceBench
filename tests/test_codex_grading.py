"""Synthetic CLI campaign coverage, isolation and immutable replay checks."""
import copy
import gzip
import json
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pathlib import Path

from model_conversation.archive import digest, read, write
from biotracebench_scoring import codex_grading as cg, human_semantic
from biotracebench_scoring.task_grading_contract import inventory
from test_biotracebench_task_grading import reply_for
from test_human_semantic import DICT, POLICY, TASK, SOURCES, BASE


class CodexGradingTests(unittest.TestCase):
    def fixture(self, root, *, whole=400, encoding='expanded'):
        inv = inventory({'result': [BASE]}, {'result': [BASE]}, DICT, POLICY)
        archive = root / 'archive'; archive.mkdir()
        (archive / 'packet.json.gz').write_bytes(gzip.compress(json.dumps({
            'inventory': inv, 'marking': {'reason': 'PRIVATE_OLD_VERDICT_SENTINEL'}}).encode()))
        write(archive / 'manifest.json', {'positions': [
            {'case': 'SYNTHETIC', 'model': 'PRIVATE_MODEL_A', 'condition': 'i0',
             'domain': 'basic', 'judgment': 'packet.json.gz', 'zero_cause': None},
            {'case': 'SYNTHETIC', 'model': 'PRIVATE_MODEL_B', 'condition': 'gsr',
             'domain': 'basic', 'judgment': 'packet.json.gz', 'zero_cause': None}]})
        context = {'task_definition': TASK, 'dictionary': DICT, 'policy': POLICY,
                   'sources': SOURCES,
                   'field_rubric': human_semantic.build_rubric(TASK, DICT, SOURCES, POLICY),
                   'input_identity': [{'path': 'PRIVATE_LOCAL_PATH'}]}
        write(root / 'contexts.json', {'SYNTHETIC': context})
        prepared = cg.prepare(archive / 'manifest.json', root / 'contexts.json', root / 'plan',
                              model='synthetic-test-model', reasoning_effort='high',
                              whole_cell_limit=whole,reply_encoding=encoding)
        return inv, prepared

    def many(self, root, n=9):
        inv,_=self.fixture(root)
        manifest={'positions':[]}
        for i in range(n):
            variant=copy.deepcopy(inv)
            for cell in variant['cells']:
                if cell['field']=='statistical_method':
                    cell['value_json']=json.dumps('Synthetic variant '+str(i))
            name=f'packet-{i}.json.gz'
            (root/'archive'/name).write_bytes(gzip.compress(json.dumps({'inventory':variant}).encode()))
            manifest['positions'].append({'case':'SYNTHETIC','model':f'PRIVATE_MODEL_{i}',
                'condition':'i0','domain':'basic','judgment':name,'zero_cause':None})
        write(root/'archive/many.json',manifest)
        cg.prepare(root/'archive/many.json',root/'contexts.json',root/'many-plan',
                   model='synthetic-test-model',reasoning_effort='high')

    def mock(self, request, attempt, profile):
        inv = request['payload']['inventory']
        complete = reply_for(inv)
        if request['phase'] == 'pair':
            return {'records': complete['records']}
        if request['phase'] == 'cells':
            expected = {(p['prediction_cell'],p['reference_cell'])
                        for p in request['payload']['batch_scope']['expected_cell_pairs']}
            complete = {'cells': [c for c in complete['cells'] if
                                 (c['prediction_cell'],c['reference_cell']) in expected],
                        'reference_issues': []}
        return self.compact(complete,inv,records=request['payload'].get('frozen_record_pairs'),
                            batch=request['payload'].get('batch_scope')) if request.get('reply_encoding')=='compact' else complete

    def compact(self, canonical, inv, *, records=None, batch=None):
        plan=cg.staged.record_plan(inv,canonical.get('records',records))
        if batch is not None:plan=[plan[i] for i in batch['record_indices']]
        marked={(c['prediction_cell'],c['reference_cell']):c for c in canonical['cells']}
        groups=[]
        for record in plan:
            pairs=record['expected_cell_pairs']
            cells=[marked[(p['prediction_cell'],p['reference_cell'])] for p in pairs]
            groups.append({'record_index':record['record_index'],'fields':[p['field'] for p in pairs],
                'verdicts':[c['verdict'] for c in cells],'categories':[c['category'] for c in cells],
                'reasons':[c['reason'] for c in cells]})
        result={'cell_groups':groups,
                'reference_issues':copy.deepcopy(canonical['reference_issues'])}
        if 'records' in canonical:result['records']=copy.deepcopy(canonical['records'])
        return result

    def test_prepare_blinds_routes_and_old_labels_and_deduplicates_full_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, prepared = self.fixture(root)
            self.assertEqual((prepared['positions'],prepared['unique_jobs']), (2,1))
            text = (root/'plan/jobs/o-00001/packet.json').read_text()
            for private in ('PRIVATE_MODEL','PRIVATE_OLD_VERDICT','PRIVATE_LOCAL_PATH'):
                self.assertNotIn(private, text)
            self.assertIn('PRIVATE_MODEL_A', (root/'plan/routes.json').read_text())

    def test_new_score_replays_without_executor_or_changing_saved_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); self.fixture(root)
            calls=[]
            def execute(*args): calls.append(1); return self.mock(*args)
            result=cg.execute(root/'plan',root/'run',workers=2,executor=execute)
            self.assertEqual(result['completed_positions'],2)
            self.assertEqual(len(calls),1)
            saved=root/'run/jobs/o-00001/result.json'; before=saved.read_bytes()
            cg.execute(root/'plan',root/'run',offline=True,executor=lambda *a:self.fail('Sent offline request'))
            self.assertEqual(saved.read_bytes(),before)
            index=read(root/'run/campaign-index.json')
            self.assertEqual(len(index['positions']),2)
            self.assertEqual(index['positions'][0]['score']['field']['f1'],1.0)

    def test_staged_pairing_cells_and_global_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); self.fixture(root,whole=1)
            phases=[]
            def execute(request,*args): phases.append(request['phase']); return self.mock(request,*args)
            result=cg.execute(root/'plan',root/'run',executor=execute)
            self.assertEqual(result['completed_jobs'],1)
            self.assertEqual(phases,['pair','cells'])

    def test_offline_missing_response_never_sends_and_then_explicit_run_recovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); self.fixture(root)
            result=cg.execute(root/'plan',root/'run',offline=True,
                              executor=lambda *a:self.fail('Sent offline request'))
            self.assertEqual(result['incomplete_jobs'],1)
            self.assertEqual(cg.execute(root/'plan',root/'run',executor=self.mock)['completed_jobs'],1)

    def test_tampered_input_and_concurrency_fail_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); self.fixture(root)
            with self.assertRaises(ValueError): cg.execute(root/'plan',root/'run',workers=4)
            packet=root/'plan/jobs/o-00001/packet.json'; value=read(packet)
            value['payload']['task_definition']='Changed task';write(packet,value)
            with self.assertRaises(ValueError): cg.execute(root/'plan',root/'run',executor=self.mock)

    def test_invalid_reply_is_preserved_and_not_published_as_a_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            result=cg.execute(root/'plan',root/'run',executor=lambda *a:{'records':[],'cells':[],'reference_issues':[]})
            self.assertEqual(result['incomplete_jobs'],1)
            self.assertFalse((root/'run/jobs/o-00001/result.json').exists())
            self.assertTrue((root/'run/jobs/o-00001/whole/attempt-001/reply.json').exists())
            result=cg.execute(root/'plan',root/'run',executor=self.mock)
            self.assertEqual(result['completed_jobs'],1)
            self.assertTrue((root/'run/jobs/o-00001/whole/attempt-002/reply.json').exists())

    def test_crash_after_transport_recovers_complete_response_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); inv,_=self.fixture(root)
            packet=read(root/'plan/jobs/o-00001/packet.json');request=cg._request(packet)
            attempt=root/'run/jobs/o-00001/whole/attempt-001';attempt.mkdir(parents=True)
            write(attempt/'request.json',request)
            write(attempt/'response.txt',reply_for(inv))
            from model_conversation.archive import sha
            write(attempt/'transport.json',{'response_sha256':sha(attempt/'response.txt'),'tool_events':0})
            result=cg.execute(root/'plan',root/'run',offline=True,executor=lambda *a:self.fail('Sent offline'))
            self.assertEqual(result['completed_jobs'],1)

    def test_tools_are_rejected_in_transport_events(self):
        self.assertEqual(cg._tool_events([{'type':'item.completed','item':{'type':'agent_message'}}]),[])
        self.assertEqual(len(cg._tool_events([{'type':'item.started','item':{'type':'command_execution'}}])),1)

    def test_quota_stops_scheduling_with_at_most_three_requests_in_flight(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.many(root)
            calls=[];mutex=threading.Lock()
            def quota(*args):
                with mutex:calls.append(1)
                raise cg.CodexTransportError('quota_exhausted','Synthetic usage limit')
            result=cg.execute(root/'many-plan',root/'run',workers=3,executor=quota)
            self.assertEqual(result['status'],'blocked')
            self.assertLessEqual(len(calls),3)
            self.assertGreaterEqual(result['waiting_jobs'],6)
            self.assertTrue((root/'run/campaign-blocked.json').exists())
            before=len(calls)
            blocked=cg.execute(root/'many-plan',root/'run',executor=quota)
            self.assertEqual(blocked['status'],'blocked');self.assertEqual(len(calls),before)
            cg.execute(root/'many-plan',root/'run',offline=True,
                       executor=lambda *a:self.fail('Offline recovery called Codex'))
            resumed=cg.execute(root/'many-plan',root/'run',resume_blocked=True,executor=self.mock)
            self.assertEqual(resumed['completed_jobs'],9)

    def test_context_failure_is_local_and_does_not_stop_unaffected_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.many(root)
            def context(request,*args):
                value=request['payload']['inventory']['cells']
                if any(c['field']=='statistical_method' and 'variant 0' in c['value_json'] for c in value):
                    raise cg.CodexTransportError('context_too_large','Synthetic large input',stop_campaign=False)
                return self.mock(request,*args)
            result=cg.execute(root/'many-plan',root/'run',workers=3,executor=context)
            self.assertEqual(result['completed_jobs'],8)
            self.assertEqual(result['waiting_jobs'],0)
            self.assertFalse((root/'run/campaign-blocked.json').exists())

    def test_three_service_failures_pause_new_scheduling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.many(root)
            calls=[]
            def unavailable(*args):
                calls.append(1)
                raise cg.CodexTransportError('transport_failure','Synthetic service outage',stop_campaign=False)
            result=cg.execute(root/'many-plan',root/'run',workers=3,executor=unavailable)
            self.assertEqual(result['status'],'blocked')
            self.assertEqual(result['blocked_reason']['transport_status'],'service_unavailable')
            self.assertLessEqual(len(calls),5)
            self.assertGreaterEqual(result['waiting_jobs'],4)

    def test_native_error_classification_ignores_successful_scientific_text(self):
        self.assertEqual(cg._transport_error([{'type':'error','message':'Usage limit reached'}],'').status,'quota_exhausted')
        self.assertTrue(cg._transport_error([{'type':'turn.failed','error':{'code':'model_not_found'}}],'').stop_campaign)
        self.assertFalse(cg._transport_error([{'type':'error','message':'context_length_exceeded'}],'').stop_campaign)

    def test_private_priority_changes_only_host_scheduling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.many(root)
            seen=[]
            def record(request,*args):
                cell=next(c for c in request['payload']['inventory']['cells'] if c['field']=='statistical_method')
                seen.append(cell['value_json']);return self.mock(request,*args)
            result=cg.execute(root/'many-plan',root/'run',workers=1,limit=1,executor=record,
                priority_keys=[{'case':'SYNTHETIC','model':'PRIVATE_MODEL_8','condition':'i0'}])
            self.assertEqual(result['completed_jobs'],1)
            self.assertIn('variant 8',seen[0])

    def test_compact_expansion_is_exactly_the_explicit_canonical_judgment(self):
        inv=inventory({'result':[BASE]},{'result':[BASE]},DICT,POLICY)
        canonical=reply_for(inv)
        packet={'payload':{'inventory':inv},'reply_encoding':'compact','compact_adapter':cg.COMPACT_ADAPTER}
        self.assertEqual(cg.expand_reply(packet,'whole',self.compact(canonical,inv)),canonical)
        raw=self.compact(canonical,inv);raw['cell_groups'][0]['verdicts'][0]='incorrect'
        expanded=cg.expand_reply(packet,'whole',raw)
        self.assertEqual(expanded['cells'][0]['verdict'],'incorrect')
        # The adapter never supplies an expected verdict or declared role.
        raw=self.compact(canonical,inv);raw['cell_groups'][0]['categories'][0]='scientific'
        self.assertEqual(cg.expand_reply(packet,'whole',raw)['cells'][0]['category'],'scientific')

    def test_compact_wrong_lengths_and_missing_arrays_are_rejected(self):
        inv=inventory({'result':[BASE]},{'result':[BASE]},DICT,POLICY)
        packet={'payload':{'inventory':inv},'reply_encoding':'compact','compact_adapter':cg.COMPACT_ADAPTER}
        for key in ('categories','verdicts','reasons'):
            raw=self.compact(reply_for(inv),inv);raw['cell_groups'][0][key].pop()
            with self.subTest(key=key),self.assertRaises(ValueError):cg.expand_reply(packet,'whole',raw)
        raw=self.compact(reply_for(inv),inv);raw['cell_groups'][0].pop('reasons')
        with self.assertRaises(ValueError):cg.expand_reply(packet,'whole',raw)

    def test_compact_mapping_order_and_sorted_fields_determine_pointers(self):
        rows=[BASE,{**BASE,'id':'R2','analysis':'Dose Group'}]
        inv=inventory({'result':rows},{'result':rows},DICT,POLICY)
        sides={s:[r for r in inv['rows'] if r['side']==s] for s in ('prediction','reference')}
        canonical=reply_for(inv,pairs=list(reversed(list(zip(sides['prediction'],sides['reference'])))))
        packet={'payload':{'inventory':inv},'reply_encoding':'compact','compact_adapter':cg.COMPACT_ADAPTER}
        expanded=cg.expand_reply(packet,'whole',self.compact(canonical,inv))
        self.assertEqual(expanded,canonical)
        self.assertNotEqual(expanded['cells'][0]['prediction_cell'],reply_for(inv)['cells'][0]['prediction_cell'])

    def test_compact_record_field_keys_order_and_indices_are_enforced(self):
        rows=[BASE,{**BASE,'id':'R2','analysis':'Dose Group'}]
        inv=inventory({'result':rows},{'result':rows},DICT,POLICY)
        packet={'payload':{'inventory':inv},'reply_encoding':'compact','compact_adapter':cg.COMPACT_ADAPTER}
        original=self.compact(reply_for(inv),inv)
        variants=[]
        raw=copy.deepcopy(original);raw['cell_groups'][0]['fields'][0]='invented';variants.append(raw)
        raw=copy.deepcopy(original);raw['cell_groups'][0]['fields'].reverse();variants.append(raw)
        raw=copy.deepcopy(original);raw['cell_groups'][0]['record_index']=1;variants.append(raw)
        raw=copy.deepcopy(original);raw['cell_groups'][0]['record_index']=False;variants.append(raw)
        raw=copy.deepcopy(original);raw['cell_groups'].reverse();variants.append(raw)
        raw=copy.deepcopy(original);raw['cell_groups'].pop();variants.append(raw)
        for raw in variants:
            with self.subTest(raw=raw),self.assertRaises(ValueError):cg.expand_reply(packet,'whole',raw)
        old=copy.deepcopy(packet);old['compact_adapter']='biotracebench-compact-cell-arrays-1'
        with self.assertRaises(ValueError):cg.expand_reply(old,'whole',original)

    def test_staged_compact_indices_remain_global_to_the_frozen_mapping(self):
        rows=[{**BASE,'id':f'R{i}','analysis':f'Synthetic analysis {i}'} for i in range(51)]
        inv=inventory({'result':rows},{'result':rows},DICT,POLICY)
        canonical=reply_for(inv);records=canonical['records']
        batch=cg.staged.batches(inv,records)[-1]
        self.assertGreater(batch['record_indices'][0],0)
        keys={(p['prediction_cell'],p['reference_cell']) for p in batch['expected_cell_pairs']}
        scoped={'cells':[c for c in canonical['cells'] if (c['prediction_cell'],c['reference_cell']) in keys],
                'reference_issues':[]}
        raw=self.compact(scoped,inv,records=records,batch=batch)
        packet={'payload':{'inventory':inv},'reply_encoding':'compact','compact_adapter':cg.COMPACT_ADAPTER}
        self.assertEqual(cg.expand_reply(packet,'cells',raw,records=records,batch=batch),scoped)
        raw['cell_groups'][0]['record_index']=0
        with self.assertRaises(ValueError):cg.expand_reply(packet,'cells',raw,records=records,batch=batch)

    def test_compact_raw_reply_is_retained_and_offline_conversion_replays(self):
        for whole in (400,1):
            with self.subTest(whole=whole),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);inv,_=self.fixture(root,whole=whole,encoding='compact')
                result=cg.execute(root/'plan',root/'run',executor=self.mock)
                self.assertEqual(result['completed_jobs'],1)
                published=read(root/'run/jobs/o-00001/result.json')
                self.assertEqual(published['marking'],reply_for(inv))
                self.assertEqual(published['compact_adapter'],cg.COMPACT_ADAPTER)
                phases=sorted((root/'run/jobs/o-00001').rglob('accepted.json'))
                cell_phase=next(p for p in phases if p.parent.name!='pair')
                raw=read(cell_phase)['reply']
                self.assertNotIn('cells',raw);self.assertIn('cell_groups',raw)
                self.assertTrue(published['phase_reply_archives'])
                before=(root/'run/jobs/o-00001/result.json').read_bytes()
                cg.execute(root/'plan',root/'run',offline=True,executor=lambda *a:self.fail('Offline call'))
                self.assertEqual((root/'run/jobs/o-00001/result.json').read_bytes(),before)

    def test_transport_uses_the_constant_empty_directory_and_absolute_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);inv,_=self.fixture(root)
            attempt=root/'attempt';attempt.mkdir();cwd=root/'empty';cwd.mkdir()
            packet=read(root/'plan/jobs/o-00001/packet.json')
            def native(command,**kwargs):
                self.assertEqual(Path(kwargs['cwd']),cwd.resolve())
                self.assertEqual(command[command.index('--cd')+1],str(cwd.resolve()))
                self.assertTrue(Path(command[command.index('--output-schema')+1]).is_absolute())
                response=Path(command[command.index('-o')+1]);self.assertTrue(response.is_absolute())
                response.write_text(json.dumps(reply_for(inv)))
                kwargs['stdout'].write(b'{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}\n')
                return SimpleNamespace(returncode=0)
            with patch.object(cg.subprocess,'run',native):
                actual=cg._invoke(cg._request(packet),attempt,{'model':None,'reasoning_effort':'high',
                                  'disabled_features':list(cg.NO_TOOLS)},working_directory=cwd)
            self.assertEqual(actual,reply_for(inv));self.assertEqual(list(cwd.iterdir()),[])


if __name__=='__main__': unittest.main()
