"""Independent standard-library API acceptance; no benchmark fixture imports."""
import ast
import copy
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
from model_conversation import Conversation, Adapter, Stop, load_profile
from model_conversation.archive import encoded

CONFIG={'endpoint':'https://api.moonshot.cn/v1/chat/completions','model':'kimi-k3','reasoning_effort':'high','timeout':900,'retries':0,'context_tokens':32768,'max_output_tokens':512,'max_request_bytes':100000}
SPEC=[{'type':'function','function':{'name':'lookup','description':'Synthetic local lookup','parameters':{'type':'object','properties':{'term':{'type':'string'}},'required':['term']}}}]

class ConnectionTests(unittest.TestCase):
    def test_no_tool_model_accepts_final_but_rejects_tool_definitions(self):
        config = Adapter(CONFIG).c
        config['capabilities']['tools'] = False
        config['execution_mode'] = 'final'
        backend = Conversation(config)
        messages = [{'role': 'user', 'content': 'Return JSON.'}]
        self.assertNotIn('tools', backend.preflight(messages, []))
        with self.assertRaises(Stop):
            backend.preflight(messages, SPEC)

    def test_no_benchmark_imports(self):
        import model_conversation,model_api
        for root in (Path(model_conversation.__file__).parent,Path(model_api.__file__).parent):
            for path in root.glob('*.py'):
                for node in ast.walk(ast.parse(path.read_text())):
                    names=[node.module or ''] if isinstance(node,ast.ImportFrom) else [x.name for x in node.names] if isinstance(node,ast.Import) else []
                    self.assertFalse(any(name.startswith('biotracebench') for name in names),str(path))

    def test_archive_native_tools_and_recover_without_key_or_network(self):
        count=0
        def sender(endpoint,body,headers,timeout):
            nonlocal count
            count+=1
            return 200,{'x-request-id':'synthetic-id'},encoded({'model':'kimi-k3','choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'reasoning_content':'native evidence','tool_calls':[{'id':'t1','type':'function','function':{'name':'lookup','arguments':'{"term":"x"}'}}]}}],'usage':{'prompt_tokens':12,'completion_tokens':8}})
        messages=[{'role':'user','content':'Use lookup; synthetic example'}]
        with tempfile.TemporaryDirectory() as tmp, patch.object(socket,'socket',side_effect=AssertionError('Network forbidden')):
            client=Conversation(CONFIG,sender=sender);folder=Path(tmp)/'call'
            with patch.dict(os.environ,{'MOONSHOT_API_KEY':'test-key-not-in-message'}):result=client.invoke(messages,SPEC,folder)
            self.assertEqual(result['message']['reasoning_content'],'native evidence')
            with patch.dict(os.environ,{},clear=True):self.assertEqual(client.recover(messages,SPEC,folder),result)
            self.assertEqual(count,1)
            with patch.dict(os.environ,{'MOONSHOT_API_KEY':'test-key-not-in-message'}):
                with self.assertRaises(Stop):client.invoke(messages,SPEC,folder)
            self.assertEqual(count,1)
            self.assertTrue((folder/'http.json').exists());self.assertTrue((folder/'response.bin').exists())

    def test_four_protocols_accept_tool_results_and_native_history(self):
        for protocol,provider in [('chat_completions','qwen'),('responses','openai'),('anthropic','anthropic'),('gemini','gemini')]:
            config={'provider':provider,'protocol':protocol,'key_env':{'qwen':'DASHSCOPE_API_KEY','openai':'OPENAI_API_KEY','anthropic':'ANTHROPIC_API_KEY','gemini':'GEMINI_API_KEY'}[provider],
                    'endpoint':'https://example.invalid/models/fixture:generateContent' if protocol=='gemini' else 'https://example.invalid/api','model':'fixture','accepted_response_models':['fixture'],
                    'generation':{},'context_tokens':32768,'max_output_tokens':512,'max_request_bytes':100000,'timeout':900,'retries':0,
                    'capabilities':{'vision':True,'tools':True,'json_object':protocol!='anthropic'},'estimator':{'kind':'fixed_upper_bound','input_tokens':100,'basis':'Synthetic only'}}
            if protocol=='chat_completions':config['output_token_field']='max_tokens'
            if protocol=='anthropic':config['api_version']='2023-06-01'
            call={'id':'t1','type':'function','function':{'name':'lookup','arguments':'{"term":"x"}'}}
            if protocol=='chat_completions':raw={'model':'fixture','choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[call]}}],'usage':{}}
            elif protocol=='responses':raw={'model':'fixture','status':'completed','output':[{'type':'function_call','id':'fc1','call_id':'t1','name':'lookup','arguments':'{"term":"x"}'}],'usage':{}}
            elif protocol=='anthropic':raw={'role':'assistant','model':'fixture','stop_reason':'tool_use','content':[{'type':'tool_use','id':'t1','name':'lookup','input':{'term':'x'}}],'usage':{}}
            else:raw={'modelVersion':'fixture','candidates':[{'finishReason':'STOP','content':{'role':'model','parts':[{'functionCall':{'id':'t1','name':'lookup','args':{'term':'x'}},'thoughtSignature':'opaque'}]}}],'usageMetadata':{}}
            adapter=Adapter(config);message=adapter.parse(raw)['message']
            cid=message['tool_calls'][0]['id']
            body=adapter.build([{'role':'user','content':'Use lookup'},message,{'role':'tool','tool_call_id':cid,'content':'{"matches":[]}'}],SPEC)
            self.assertIn('lookup',json.dumps(body))
            if protocol=='gemini':self.assertIn('opaque',json.dumps(body))

    def test_provider_profile_load_is_independent(self):
        root=Path(__file__).resolve().parents[1]
        profile=load_profile(root/'configs/models/conversation-profiles/kimi-task-draft.json')
        self.assertEqual(profile['provider'],'kimi')
        self.assertEqual(profile['context_tokens'],1000000)

    def test_query_mode_and_final_submission_are_separate(self):
        config=dict(CONFIG,execution_mode='tool_query')
        first=Conversation(config).preflight([{'role':'user','content':'Choose local lookup; final JSON later'}],SPEC)
        self.assertEqual(first['tool_choice'],'auto')
        self.assertNotIn('response_format',first)
        with self.assertRaises(ValueError):Conversation(config).preflight([{'role':'user','content':'Query'}],[])
        config['execution_mode']='final'
        final=Conversation(config).preflight([{'role':'user','content':'Submit JSON'}],[])
        self.assertNotIn('tools',final)
        self.assertEqual(final['response_format'],{'type':'json_object'})

class StructuredTests(unittest.TestCase):
    def config(self, mode='final'):
        c=Adapter(CONFIG).c
        c['capabilities']['json_schema']=True
        c['execution_mode']=mode
        if mode=='final': c['output_schema']={'name':'fixture','schema':{'type':'object','properties':{'count':{'type':'integer'}},'required':['count'],'additionalProperties':False}}
        return c

    def test_native_format_roundtrip_and_schema_tamper_rejected(self):
        c=self.config(); messages=[{'role':'user','content':'Return JSON with count 0'}]
        def sender(*args):
            body=json.loads(args[1]); self.assertEqual(body['response_format']['type'],'json_schema')
            self.assertIs(body['response_format']['json_schema']['strict'],True)
            return 200,{},encoded({'model':'kimi-k3','choices':[{'finish_reason':'stop','message':{'role':'assistant','content':'{"count":0}'}}],'usage':{'prompt_tokens':20,'completion_tokens':5}})
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'MOONSHOT_API_KEY':'synthetic-only'}),patch.object(socket,'socket',side_effect=AssertionError('No network')):
            folder=Path(tmp)/'call'; client=Conversation(c,sender=sender)
            result=client.invoke(messages,[],folder)
            with patch.dict(os.environ,{},clear=True): self.assertEqual(client.recover(messages,[],folder),result)
            c['output_schema']['schema']['properties']['count']['type']='string'
            with self.assertRaises(Stop): Conversation(c).recover(messages,[],folder)

    def test_estimator_reserves_schema_and_query_has_none(self):
        c=self.config(); seen=[]
        def sender(*args):
            seen.append(json.loads(args[1])); return 200,{},encoded({'data':{'total_tokens':50}})
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'MOONSHOT_API_KEY':'synthetic-only'}):
            client=Conversation(c,sender=sender)
            result=client.estimate([{'role':'user','content':'JSON'}],[],Path(tmp)/'estimate')
            self.assertGreater(result['reserved_input_tokens'],50)
            self.assertIn('json_schema',seen[0]['messages'][-1]['content'])
            with patch.dict(os.environ,{},clear=True): self.assertEqual(client.estimate([{'role':'user','content':'JSON'}],[],Path(tmp)/'estimate',offline=True),result)
        body=Conversation(self.config('tool_query')).preflight([{'role':'user','content':'Choose queries'}],SPEC)
        self.assertNotIn('response_format',body)

    def test_unsupported_policy_schema_or_protocol_fail_closed(self):
        c=self.config();c['capabilities'].pop('json_schema')
        with self.assertRaises(ValueError): Conversation(c)
        c=self.config(); c['output_schema']['schema']['oneOf']=[]
        with self.assertRaises(ValueError): Conversation(c)
        c=self.config();c['execution_mode']='continuation'
        with self.assertRaises(ValueError): Conversation(c)
        c=self.config();c['protocol']='responses'
        with self.assertRaises(ValueError): Conversation(c)


class GenerationParameterTests(unittest.TestCase):
    def config(self, protocol):
        provider = {'chat_completions': 'qwen', 'responses': 'openai', 'anthropic': 'anthropic', 'gemini': 'gemini'}[protocol]
        config = {'provider': provider, 'protocol': protocol,
                  'key_env': {'qwen': 'DASHSCOPE_API_KEY', 'openai': 'OPENAI_API_KEY', 'anthropic': 'ANTHROPIC_API_KEY', 'gemini': 'GEMINI_API_KEY'}[provider],
                  'endpoint': 'https://example.invalid/models/fixture:generateContent' if protocol == 'gemini' else 'https://example.invalid/api',
                  'model': 'fixture', 'accepted_response_models': ['fixture'], 'generation': {},
                  'context_tokens': 32768, 'max_output_tokens': 4096, 'max_request_bytes': 100000,
                  'timeout': 900, 'retries': 0, 'execution_mode': 'final',
                  'capabilities': {'vision': True, 'tools': True, 'json_object': protocol != 'anthropic'},
                  'estimator': {'kind': 'fixed_upper_bound', 'input_tokens': 100, 'basis': 'Synthetic only'}}
        if protocol == 'chat_completions': config['output_token_field'] = 'max_tokens'
        if protocol == 'anthropic': config['api_version'] = '2023-06-01'
        return config

    def test_invalid_parameters_fail_before_any_transport_or_estimation(self):
        cases = [
            ('chat_completions', {'enable_thinking': 'false'}, 'generation.enable_thinking'),
            ('chat_completions', {'reasoning_effort': 1}, 'generation.reasoning_effort'),
            ('chat_completions', {'thinking': {'type': 'unknown'}}, 'generation.thinking.type'),
            ('responses', {'reasoning': 'high'}, 'generation.reasoning'),
            ('responses', {'reasoning': {'effort': 'unknown'}}, 'generation.reasoning.effort'),
            ('responses', {'reasoning': {'invented': True}}, 'generation.reasoning.invented'),
            ('anthropic', {'thinking': {'type': 'enabled', 'budget_tokens': -1}}, 'generation.thinking.budget_tokens'),
            ('anthropic', {'thinking': {'type': 'enabled', 'budget_tokens': True}}, 'generation.thinking.budget_tokens'),
            ('anthropic', {'thinking': {'type': 'enabled', 'budget_tokens': 1023}}, 'generation.thinking.budget_tokens'),
            ('anthropic', {'thinking': {'type': 'enabled', 'budget_tokens': 4096}}, 'generation.thinking.budget_tokens'),
            ('anthropic', {'thinking': {'type': 'adaptive', 'budget_tokens': 1024}}, 'generation.thinking.budget_tokens'),
            ('anthropic', {'output_config': {'effort': 'unknown'}}, 'generation.output_config.effort'),
            ('gemini', {'thinkingConfig': {'thinkingBudget': True}}, 'generation.thinkingConfig.thinkingBudget'),
            ('gemini', {'thinkingConfig': {'thinkingBudget': -2}}, 'generation.thinkingConfig.thinkingBudget'),
            ('gemini', {'thinkingConfig': {'includeThoughts': 'true'}}, 'generation.thinkingConfig.includeThoughts'),
            ('gemini', {'thinkingConfig': {'thinkingBudget': 0, 'thinkingLevel': 'low'}}, 'generation.thinkingConfig'),
        ]
        with patch.object(socket, 'socket', side_effect=AssertionError('Network forbidden')):
            for protocol, generation, field in cases:
                with self.subTest(protocol=protocol, generation=generation):
                    config = self.config(protocol); config['generation'] = generation
                    with self.assertRaises(ValueError) as caught:
                        Conversation(config, sender=lambda *args: self.fail('Transport was called'))
                    self.assertIn(field, str(caught.exception))

    def test_valid_parameters_preserve_values_and_declared_defaults(self):
        cases = [
            ('chat_completions', {'enable_thinking': False}),
            ('chat_completions', {'thinking': {'type': 'disabled'}}),
            ('responses', {'reasoning': {'effort': 'max'}}),
            ('anthropic', {'thinking': {'type': 'enabled', 'budget_tokens': 1024}}),
            ('anthropic', {'thinking': {'type': 'adaptive'}, 'output_config': {'effort': 'high'}}),
            ('gemini', {'thinkingConfig': {'thinkingBudget': -1}}),
            ('gemini', {'thinkingConfig': {'thinkingBudget': 0, 'includeThoughts': False}}),
            ('gemini', {'thinkingConfig': {'thinkingLevel': 'low'}}),
        ]
        for protocol, generation in cases:
            with self.subTest(protocol=protocol, generation=generation):
                config = self.config(protocol); config['generation'] = generation
                original = copy.deepcopy(config)
                body = Conversation(config).preflight([{'role': 'user', 'content': 'Return JSON.'}], [])
                self.assertEqual(config, original)
                output = body['generationConfig'] if protocol == 'gemini' else body
                for key, value in generation.items(): self.assertEqual(output[key], value)
        for protocol in ('chat_completions', 'responses', 'anthropic', 'gemini'):
            config = self.config(protocol)
            self.assertEqual(Conversation(config).profile['generation'], {})

    def test_loading_a_profile_validates_generation_even_in_a_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'vendor.json').write_text(json.dumps({'name': 'qwen', 'defaults': {'provider': 'qwen', 'protocol': 'chat_completions'}}))
            path = root / 'profile.json'
            path.write_text(json.dumps({'provider_template': 'vendor.json', 'settings': {'generation': {'enable_thinking': 'false'}, 'max_output_tokens': None}}))
            with self.assertRaisesRegex(ValueError, 'generation.enable_thinking'):
                load_profile(path)

class NativeSchemaTests(unittest.TestCase):
    def test_all_protocols_preserve_patterns_and_never_add_tools(self):
        schema = {"type": "object", "properties": {
            "value": {"anyOf": [{"type": "number"}, {"type": "string", "pattern": r"^[<>]?\d+$"}]},
            "ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True}},
            "required": ["value", "ids"], "additionalProperties": False}
        for protocol in ("chat_completions", "responses", "anthropic", "gemini"):
            config = GenerationParameterTests().config(protocol)
            config["capabilities"]["json_schema"] = True
            config["output_schema"] = {"name": "fixture", "schema": copy.deepcopy(schema)}
            if protocol == "anthropic":
                config["generation"] = {"output_config": {"effort": "high"}}
            original = copy.deepcopy(config)
            body = Conversation(config).preflight([{"role": "user", "content": "Return JSON."}], [])
            projected = (body["response_format"]["json_schema"]["schema"] if protocol == "chat_completions" else
                         body["text"]["format"]["schema"] if protocol == "responses" else
                         body["output_config"]["format"]["schema"] if protocol == "anthropic" else
                         body["generationConfig"]["responseJsonSchema"])
            self.assertEqual(projected, schema)
            self.assertNotIn("tools", body)
            self.assertEqual(config["output_schema"]["schema"], schema)
            self.assertEqual(config, original)
            if protocol == "anthropic":
                self.assertEqual(body["output_config"]["effort"], "high")
            config["capabilities"]["json_schema"] = False
            with self.assertRaises(ValueError):
                Adapter(config)

if __name__=='__main__':unittest.main()
