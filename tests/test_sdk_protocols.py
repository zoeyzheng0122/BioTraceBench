"""Offline service boundaries: never submit a model request."""
import base64
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from model_api import Backend, ApiFailure, load_profile


def profile(protocol='chat_completions', **changes):
    value={'profile_version':1,'name':'synthetic','provider':'synthetic','protocol':protocol,
           'endpoint':'https://example.invalid/v1/chat/completions','model':'synthetic-model',
           'key_env':'SYNTHETIC_API_KEY','vision':False,'structured_output':'json_object',
           'context_tokens':100000,'max_output_tokens':1000,'max_input_bytes':50000,
           'max_images':0,'image_token_reserve':0,'output_token_field':'max_tokens',
           'generation':{},'timeout':900}
    value.update(changes)
    if protocol=='gemini' and 'endpoint' not in changes:value['endpoint']='https://example.invalid/v1beta/models/'+value['model']+':generateContent'
    return value


def request():
    return {'protocol_version':'qwen-evidence-3','stage':'read','instruction':'Return one JSON object.',
            'payload':{'text':'剂量 0 mg 🧪'},'response_schema':{'type':'object'},'images':[]}


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'SYNTHETIC_API_KEY':'secret-never-save'});self.env.start()
    def tearDown(self):
        self.env.stop();self.tmp.cleanup()
    def backend(self, protocol, response, **changes):
        self.sent=[]
        def send(url, body, headers, timeout):
            self.sent.append((url,json.loads(body),headers,timeout))
            return 200,{'content-type':'application/json','x-request-id':'req-1'},json.dumps(response,ensure_ascii=False).encode()
        return Backend(load_profile(profile(protocol,**changes)),sender=send)
    def test_chat_preserves_zero_unicode_and_raw_model_text(self):
        b=self.backend('chat_completions',{'model':'actual','choices':[{'message':{'content':'```json\n{"n":0}\n```'},'finish_reason':'stop'}], 'usage':{'prompt_tokens':0,'completion_tokens':2}})
        result=b.invoke(request(),self.root/'attempt')
        self.assertEqual(result.text,'```json\n{"n":0}\n```')
        self.assertEqual(result.usage['input_tokens'],0)
        self.assertIsNone(result.usage['total_tokens'])
        self.assertEqual(result.actual_model,'actual')
        self.assertIn('剂量 0 mg 🧪',self.sent[0][1]['messages'][1]['content'][0]['text'])
        self.assertNotIn('effort',self.sent[0][1])
        recovered=b.recover(request(),self.root/'attempt')
        self.assertEqual(recovered.text,result.text);self.assertEqual(len(self.sent),1)
    def test_four_protocols_send_their_own_envelopes_and_extract_text(self):
        fixtures=[('responses',{'id':'r','model':'m','status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'{"n":0}'}]}]},'input'),
                  ('anthropic',{'id':'r','model':'m','stop_reason':'end_turn','content':[{'type':'text','text':'{"n":0}'}]},'messages'),
                  ('gemini',{'modelVersion':'m','candidates':[{'content':{'parts':[{'text':'{"n":0}'}]},'finishReason':'STOP'}]},'contents')]
        for protocol,response,key in fixtures:
            with self.subTest(protocol=protocol):
                b=self.backend(protocol,response,structured_output='json_schema',output_token_field={'responses':'max_output_tokens','gemini':'maxOutputTokens','anthropic':'max_tokens'}[protocol])
                result=b.invoke(request(),self.root/protocol)
                self.assertEqual(result.text,'{"n":0}')
                self.assertIn(key,self.sent[0][1]);self.assertNotIn('tools',self.sent[0][1])
    def test_image_hash_is_verified_before_submission_and_native_image_is_sent(self):
        import hashlib
        image=self.root/'x.png';image.write_bytes(b'\x89PNG\r\n\x1a\nimage')
        req=request();req['images']=[{'path':str(image),'sha256':hashlib.sha256(image.read_bytes()).hexdigest()}]
        b=self.backend('chat_completions',{'choices':[{'message':{'content':'{}'},'finish_reason':'stop'}]},vision=True,max_images=1,image_token_reserve=100)
        b.invoke(req,self.root/'image')
        self.assertEqual(self.sent[0][1]['messages'][1]['content'][1]['image_url']['url'],'data:image/png;base64,'+base64.b64encode(image.read_bytes()).decode())
        image.write_bytes(b'changed')
        with self.assertRaises(ApiFailure):b.invoke(req,self.root/'changed')
        self.assertEqual(len(self.sent),1)
    def test_truncation_and_refusal_are_archived_and_never_decoded_as_success(self):
        for name,choice in [('truncated',{'message':{'content':'{"n":'},'finish_reason':'length'}),('refusal',{'message':{'content':None,'refusal':'declined'},'finish_reason':'stop'})]:
            b=self.backend('chat_completions',{'choices':[choice]})
            with self.assertRaises(ApiFailure):b.invoke(request(),self.root/name)
            with self.assertRaises(ApiFailure):b.recover(request(),self.root/name)
            self.assertEqual(len(self.sent),1)
            self.assertTrue((self.root/name/'api-response.bin').exists())
    def test_non_json_200_and_secret_echo_are_archived_without_secret(self):
        b=Backend(load_profile(profile()),sender=lambda *args:(200,{'content-type':'text/event-stream'},b'secret-never-save invalid body'))
        with self.assertRaises(ApiFailure):b.invoke(request(),self.root/'bad')
        for f in (self.root/'bad').iterdir():self.assertNotIn(b'secret-never-save',f.read_bytes())
    def test_unknown_submission_cannot_be_invoked_again_and_recovery_is_read_only(self):
        calls=[]
        def fail(*args):calls.append(1);raise TimeoutError('secret-never-save')
        b=Backend(load_profile(profile()),sender=fail)
        with self.assertRaises(ApiFailure):b.invoke(request(),self.root/'timeout')
        self.assertIsNone(b.recover(request(),self.root/'timeout'))
        with self.assertRaises(ApiFailure):b.invoke(request(),self.root/'timeout')
        self.assertEqual(len(calls),1)
    def test_non_json_auth_failure_is_credential_scoped_and_raw_timeout_has_no_retry(self):
        b=Backend(load_profile(profile()),sender=lambda *a:(401,{'content-type':'text/html'},b'Login denied secret-never-save'))
        with self.assertRaises(ApiFailure) as error:b.invoke(request(),self.root/'unauthorized')
        self.assertEqual(error.exception.scope,'credential')
        self.assertFalse(error.exception.retryable)
    def test_recovery_checks_frozen_request_body_and_archived_bytes(self):
        b=self.backend('chat_completions',{'choices':[{'message':{'content':'{}'},'finish_reason':'stop'}]})
        folder=self.root/'bound';b.invoke(request(),folder)
        (folder/'api-response.bin').write_bytes(b'{"choices":[]}')
        with self.assertRaises(ValueError):b.recover(request(),folder)
    def test_truncated_response_still_retains_usage_and_finish_reason(self):
        b=self.backend('chat_completions',{'model':'actual','choices':[{'message':{'content':'{'},'finish_reason':'length'}],'usage':{'prompt_tokens':0,'completion_tokens':1000}})
        folder=self.root/'truncated-usage'
        with self.assertRaises(ApiFailure):b.invoke(request(),folder)
        saved=json.loads((folder/'api-result.json').read_text())
        self.assertEqual(saved['usage']['input_tokens'],0);self.assertEqual(saved['finish_reason'],'length')
    def test_configuration_rejects_secret_fields_tools_unsafe_urls_and_unknown_parameters(self):
        for changes in [{'api_key':'oops'},{'endpoint':'http://example.com/v1'},{'endpoint':'https://x.test/?key=oops'},{'generation':{'tools':[]}},{'generation':{'temperature':False}},{'vision':False,'max_images':1},{'max_output_tokens':100000}]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):load_profile(profile(**changes))
    def test_all_vendor_templates_are_loadable_without_keys_or_inference(self):
        root=Path(__file__).resolve().parents[1]/'configs/models/vendors'
        values=list(root.glob('*.json'));self.assertEqual(len(values),13)
        for p in values:
            cfg=json.loads(p.read_text());cfg.pop('template_notes',None)
            cfg.update(name='test',model='actual-selected-model',vision=False,structured_output='none',context_tokens=8192,max_output_tokens=1024,max_input_bytes=4096,max_images=0,image_token_reserve=0,generation={})
            if cfg['protocol']=='gemini':cfg['endpoint']='https://generativelanguage.googleapis.com/v1beta/models/actual-selected-model:generateContent'
            self.assertEqual(load_profile(cfg).describe()['model'],'actual-selected-model')
    def test_gemini_profile_cannot_silently_send_another_model_from_endpoint(self):
        with self.assertRaises(ValueError):load_profile(profile('gemini',output_token_field='maxOutputTokens',endpoint='https://example.invalid/v1beta/models/other-model:generateContent'))
    def test_json_escaped_secret_echo_is_redacted_in_raw_and_nested_derived_content(self):
        encoded=b'{"model":"synthetic-model","choices":[{"message":{"content":"\\u0073ecret-never-save"},"finish_reason":"stop"}]}'
        for name,raw in [('outer',encoded),('nested',json.dumps({'choices':[{'message':{'content':'{"echo":"\\u0073ecret-never-save"}'},'finish_reason':'stop'}]}).encode())]:
            b=Backend(load_profile(profile()),sender=lambda *a,raw=raw:(200,{},raw))
            result=b.invoke(request(),self.root/name)
            self.assertNotIn('secret-never-save',result.text)
            for f in (self.root/name).iterdir():self.assertNotIn(b'secret-never-save',f.read_bytes())
            self.assertTrue(json.loads((self.root/name/'api-http.json').read_text())['credential_echo_redacted'])
    def test_native_schema_is_counted_in_full_capacity_before_any_http(self):
        req=request();req['instruction']='JSON';req['payload']={};req['response_schema']={'type':'object','description':'x'*2000}
        for protocol,field in [('responses','max_output_tokens'),('chat_completions','max_tokens'),('anthropic','max_tokens'),('gemini','maxOutputTokens')]:
            b=self.backend(protocol,{},structured_output='json_schema',output_token_field=field,max_input_bytes=2500,context_tokens=3500)
            with self.subTest(protocol=protocol),self.assertRaises(ApiFailure):b.invoke(req,self.root/('capacity-'+protocol))
            self.assertEqual(self.sent,[])


if __name__=='__main__':unittest.main()
