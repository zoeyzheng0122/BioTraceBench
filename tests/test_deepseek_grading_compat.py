"""Provider compatibility checks on synthetic full-task judgments; no live calls."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from model_api import Backend,load_profile
from model_conversation.archive import read,write
from biotracebench_scoring import task_grading as grading
from biotracebench_scoring.task_grading_budget import output_control
import test_biotracebench_task_grading as fixtures


def profile():
    p=load_profile(fixtures.PROFILE).describe()
    p.update(provider='deepseek',model='deepseek-flash',name='deepseek-synthetic',key_env='DEEPSEEK_API_KEY',
        endpoint='https://api.deepseek.com/chat/completions',output_token_field='max_tokens',
        generation={'thinking':{'type':'enabled'},'reasoning_effort':'high','top_p':0.95})
    return p

class DeepSeekCompatibilityTests(unittest.TestCase):
    def test_wire_and_whole_task_metrics_and_offline_reuse(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict('os.environ',{'DEEPSEEK_API_KEY':'synthetic-secret'}):
            root=Path(tmp);p=profile();write(root/'ds.json',p)
            fixtures.WorkflowTests().fixture(root,profile=root/'ds.json');calls=[]
            def send(endpoint,wire,headers,timeout):
                body=json.loads(wire);calls.append(body)
                self.assertEqual(body['thinking'],{'type':'enabled'});self.assertEqual(body['reasoning_effort'],'high')
                for k in ['enable_thinking','temperature','seed','max_completion_tokens']:self.assertNotIn(k,body)
                payload=json.loads(body['messages'][1]['content'][0]['text'])['payload']
                response={'id':'synthetic-ds','model':'deepseek-flash','usage':{'prompt_tokens':100,'completion_tokens':20,'completion_tokens_details':{'reasoning_tokens':10}},
                    'choices':[{'finish_reason':'stop','message':{'content':json.dumps(fixtures.reply_for(payload['inventory']))}}]}
                return 200,{},json.dumps(response).encode()
            backend=Backend(root/'ds.json',sender=send)
            state=grading.execute(root/'plan',root/'run',backend=backend)
            self.assertTrue(state['all_selected_outputs_graded']);self.assertEqual(len(calls),1)
            result=next((root/'run/tasks').glob('*/marking.json'));mark=read(result)['result']
            self.assertEqual(mark['field']['f1'],1);self.assertEqual(mark['record']['f1'],1)
            self.assertEqual(mark['score_basis'],'deepseek_machine_marking');self.assertEqual(mark['judge']['provider'],'deepseek')
            grading.execute(root/'plan',root/'run',offline=True,backend=backend);self.assertEqual(len(calls),1)

    def test_single_acceptance_boundary_and_full_resume_do_not_duplicate_first_call(self):
        class AcceptanceBoundary(RuntimeError):
            dispatch_state = 'not_sent'

        class OneRequestBackend(Backend):
            def __init__(self, profile, *, sender):
                self.sent = 0
                def once(*args):
                    if self.sent:
                        raise AcceptanceBoundary('Synthetic single-request boundary')
                    self.sent += 1
                    return sender(*args)
                super().__init__(profile, sender=once)

            def check_send(self, request):
                if self.sent:
                    raise AcceptanceBoundary('Synthetic single-request boundary')
                return super().check_send(request)
        with tempfile.TemporaryDirectory() as tmp,patch.dict('os.environ',{'DEEPSEEK_API_KEY':'synthetic-secret'}):
            root=Path(tmp);p=profile();write(root/'ds.json',p)
            fixtures.WorkflowTests().fixture(root,stages=('i0','gsr'),profile=root/'ds.json');calls=[]
            def send(endpoint,wire,headers,timeout):
                body=json.loads(wire);calls.append(body)
                payload=json.loads(body['messages'][1]['content'][0]['text'])['payload']
                return 200,{},json.dumps({'id':'synthetic-'+str(len(calls)),'model':'deepseek-flash',
                    'usage':{'prompt_tokens':100,'completion_tokens':20},'choices':[{'finish_reason':'stop',
                    'message':{'content':json.dumps(fixtures.reply_for(payload['inventory']))}}]}).encode()
            once=OneRequestBackend(root/'ds.json',sender=send)
            with self.assertRaises(AcceptanceBoundary):grading.execute(root/'plan',root/'run',backend=once)
            self.assertEqual(len(calls),1)
            self.assertEqual(read(root/'run/status.json')['graded_outputs'],1)
            result=grading.execute(root/'plan',root/'run',backend=Backend(root/'ds.json',sender=send))
            self.assertEqual(len(calls),2);self.assertTrue(result['all_selected_outputs_graded'])

    def test_ds_uses_total_output_cap_and_no_qwen_margin(self):
        p=profile();c=output_control(p)
        self.assertEqual(c['output_token_field'],'max_tokens');self.assertEqual(c['reserved_output_tokens'],p['max_output_tokens'])
        self.assertEqual(c['output_scope'],'reasoning_plus_final');self.assertEqual(c['provider_margin_tokens'],0)

    def test_qwen_only_output_field_rejected_for_ds(self):
        p=profile();p['output_token_field']='max_completion_tokens'
        with self.assertRaisesRegex(ValueError,'DeepSeek grading'):output_control(p)

    def test_chat_thinking_rejected_for_other_provider(self):
        p=profile();p['provider']='qwen'
        with self.assertRaisesRegex(ValueError,'explicit DeepSeek'):load_profile(p)

    def test_ds_model_identity_mismatch_stops_before_scientific_marking(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict('os.environ',{'DEEPSEEK_API_KEY':'synthetic-secret'}):
            root=Path(tmp);p=profile();write(root/'ds.json',p);fixtures.WorkflowTests().fixture(root,profile=root/'ds.json')
            def send(*args):
                return 200,{},json.dumps({'id':'synthetic-wrong-model','model':'other-model','usage':{'prompt_tokens':100,'completion_tokens':20},
                    'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]}).encode()
            with self.assertRaisesRegex(ValueError,'model identity mismatch'):
                grading.execute(root/'plan',root/'run',backend=Backend(root/'ds.json',sender=send))
            self.assertEqual(read(root/'run/status.json')['pause']['status'],'paused_model_identity')
