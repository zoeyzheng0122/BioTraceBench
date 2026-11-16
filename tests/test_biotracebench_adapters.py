"""Offline protocol and runner acceptance. Fake providers only; sockets forbidden."""
import copy
import json
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from biotracebench.adapters import Adapter
from biotracebench.common import Stop, encoded, read, write
from biotracebench.conversation import Conversation
from biotracebench.cost import calculate, validate_tariff
from biotracebench.profiles import load
from biotracebench.runner import freeze, run
from biotracebench.materials import prepare
from test_biotracebench import MODEL, TARIFF, SyntheticProvider, source_fixture

SPECS = [{"type":"function","function":{"name":"read_material","description":"Read local material","parameters":{"type":"object","properties":{"material":{"type":"string"}},"required":["material"]}}}]
PNG = "data:image/png;base64,iVBORw0KGgo="


def model(protocol):
    provider = {"chat_completions":"qwen","responses":"openai","anthropic":"anthropic","gemini":"gemini"}[protocol]
    c = dict(MODEL)
    c.pop("reasoning_effort")
    c.update(provider=provider,protocol=protocol,key_env={"qwen":"DASHSCOPE_API_KEY","openai":"OPENAI_API_KEY","anthropic":"ANTHROPIC_API_KEY","gemini":"GEMINI_API_KEY"}[provider],
             endpoint="https://example.invalid/fixture:generateContent" if protocol=="gemini" else "https://example.invalid/api",
             model="fixture", accepted_response_models=["fixture"], generation={},
             capabilities={"vision":True,"tools":True,"json_object":protocol!="anthropic"},
             estimator={"kind":"fixed_upper_bound","input_tokens":500,"basis":"Synthetic fixture only; not a production estimate"})
    if protocol=="chat_completions": c["output_token_field"]="max_tokens"
    if protocol=="anthropic": c["api_version"]="2023-06-01"
    return c


def wire_response(protocol, assistant, finish="stop"):
    calls=assistant.get("tool_calls",[]); content=assistant.get("content") or ""
    usage={"prompt_tokens":200,"completion_tokens":20,"cached_tokens":0,"cache_write_tokens":0}
    if protocol=="chat_completions":
        return {"model":"fixture","choices":[{"message":assistant,"finish_reason":finish}],"usage":usage}
    if protocol=="responses":
        items=[{"id":"rs_test","type":"reasoning","summary":[],"encrypted_content":"opaque-reasoning"}]
        items += [{"type":"function_call","id":"fc_"+c["id"],"call_id":c["id"],"name":c["function"]["name"],"arguments":c["function"]["arguments"]} for c in calls]
        if content: items.append({"type":"message","id":"msg_test","role":"assistant","status":"completed","content":[{"type":"output_text","text":content,"annotations":[]}]})
        return {"model":"fixture","status":"completed" if finish!="length" else "incomplete","incomplete_details":{"reason":"max_output_tokens"},"output":items,"usage":usage}
    if protocol=="anthropic":
        blocks=[{"type":"thinking","thinking":"private synthetic thought","signature":"opaque-signature"}]
        blocks += [{"type":"tool_use","id":c["id"],"name":c["function"]["name"],"input":json.loads(c["function"]["arguments"])} for c in calls]
        if content: blocks.append({"type":"text","text":content})
        return {"model":"fixture","role":"assistant","content":blocks,"stop_reason":"max_tokens" if finish=="length" else "tool_use" if calls else "end_turn","usage":usage}
    parts=[{"text":"private synthetic thought","thought":True,"thoughtSignature":"opaque-signature"}]
    parts += [{"functionCall":{"id":c["id"],"name":c["function"]["name"],"args":json.loads(c["function"]["arguments"])},"thoughtSignature":"call-signature"} for c in calls]
    if content: parts.append({"text":content})
    return {"modelVersion":"fixture","candidates":[{"content":{"role":"model","parts":parts},"finishReason":"MAX_TOKENS" if finish=="length" else "STOP"}],"usageMetadata":usage}


def canonical_input(protocol, body):
    """Test fixture reader; independent of production encoding, feeds scenario."""
    if protocol=="chat_completions": return body["messages"]
    messages=[]
    if protocol=="responses":
        messages.append({"role":"system","content":body["instructions"]})
        for item in body["input"]:
            typ=item.get("type")
            if typ=="function_call_output": messages.append({"role":"tool","content":item["output"]})
            elif item.get("role") in {"user","assistant"}:
                for part in item["content"]:
                    if "text" in part: messages.append({"role":item["role"],"content":part["text"]})
    else:
        for m in body["messages" if protocol=="anthropic" else "contents"]:
            for block in m["content" if protocol=="anthropic" else "parts"]:
                if block.get("type")=="tool_result":messages.append({"role":"tool","content":block["content"]})
                elif "functionResponse" in block:messages.append({"role":"tool","content":json.dumps(block["functionResponse"]["response"])})
                elif "text" in block and not block.get("thought"):messages.append({"role":"assistant" if m["role"]=="model" else m["role"],"content":block["text"]})
    return messages


class Bridge:
    def __init__(self,protocol):self.protocol=protocol;self.fixture=SyntheticProvider();self.bodies=[]
    def __call__(self,endpoint,body,headers,timeout):
        value=json.loads(body);self.bodies.append(value)
        _,_,raw=self.fixture(endpoint,encoded({"messages":canonical_input(self.protocol,value)}),headers,timeout)
        raw=json.loads(raw);choice=raw["choices"][0]
        return 200,{},encoded(wire_response(self.protocol,choice["message"],choice["finish_reason"]))


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.network=patch.object(socket,"socket",side_effect=AssertionError("Live network forbidden"));self.network.start()
    def tearDown(self):self.network.stop();self.temp.cleanup()

    def test_four_protocols_tool_roundtrip_images_native_history(self):
        for protocol in ("chat_completions","responses","anthropic","gemini"):
            with self.subTest(protocol=protocol):
                backend=Conversation(model(protocol));a=backend.adapter
                call={"id":"tool1","type":"function","function":{"name":"read_material","arguments":'{"material":"m1"}'}}
                raw=wire_response(protocol,{"role":"assistant","content":None,"tool_calls":[call]},"tool_calls")
                result=a.parse(raw);self.assertEqual(result["status"],"ok")
                history=[{"role":"system","content":"Return JSON"},{"role":"user","content":"read"},result["message"],
                         {"role":"tool","tool_call_id":"tool1","content":'{"count":0}'},
                         {"role":"user","content":[{"type":"text","text":"中文"},{"type":"image_url","image_url":{"url":PNG}}]}]
                before=copy.deepcopy(history);body=backend.preflight(history,SPECS)
                self.assertEqual(before,history)
                serialized=json.dumps(body,ensure_ascii=False)
                self.assertIn('中文',serialized);self.assertIn('iVBORw0KGgo=',serialized)
                if protocol=="responses":self.assertIn("opaque-reasoning",serialized);self.assertIn("function_call_output",serialized)
                elif protocol=="anthropic":self.assertIn("opaque-signature",serialized);self.assertIn("tool_result",serialized)
                elif protocol=="gemini":self.assertIn("call-signature",serialized);self.assertIn("functionResponse",serialized)
                final=a.parse(wire_response(protocol,{"role":"assistant","content":'{"count":0,"text":"中文"}'}))
                self.assertEqual(json.loads(final["message"]["content"])["count"],0)
                self.assertNotIn("private synthetic thought",final["message"]["content"])
                self.assertEqual(a.parse(wire_response(protocol,{"role":"assistant","content":"{"},"length"))["status"],"paused_truncated")

    def test_all_protocols_archives_redaction_offline_recovery(self):
        for protocol in ("chat_completions","responses","anthropic","gemini"):
            cfg=model(protocol);key="synthetic-secret-ONLY"
            raw=wire_response(protocol,{"role":"assistant","content":'{"ok":true}'})
            raw["echo"]=key
            def sender(endpoint,body,headers,timeout):
                self.assertIn(key,headers.values() if protocol in {"anthropic","gemini"} else [headers["Authorization"].removeprefix("Bearer ")])
                return 200,{"x-request-id":key},encoded(raw)
            c=Conversation(cfg,sender);msgs=[{"role":"user","content":"JSON"}];folder=self.root/protocol
            with patch.dict(os.environ,{cfg["key_env"]:key}):result=c.invoke(msgs,[],folder)
            with patch.dict(os.environ,{},clear=True):self.assertEqual(c.recover(msgs,[],folder),result)
            for p in folder.rglob('*'):
                if p.is_file():self.assertNotIn(key.encode(),p.read_bytes())
            with self.assertRaises(Stop):c.invoke(msgs,[],folder)
            (folder/'response.bin').write_text('{}')
            with self.assertRaises(Stop):c.recover(msgs,[],folder)

    def test_capability_identity_and_history_fail_closed(self):
        for protocol in ("chat_completions","responses","anthropic","gemini"):
            cfg=model(protocol);cfg["capabilities"]["vision"]=False
            with self.assertRaises(Stop):Conversation(cfg).preflight([{"role":"user","content":[{"type":"image_url","image_url":{"url":PNG}}]}],[])
            cfg["accepted_response_models"]=["different"]
            self.assertEqual(Adapter(cfg).parse(wire_response(protocol,{"role":"assistant","content":"{}"}))["status"],"failed_model_identity")
            with self.assertRaises(ValueError):Conversation(cfg).preflight([{"role":"tool","tool_call_id":"unknown","content":"{}"}],[])
        with self.assertRaises(ValueError):Conversation(model("anthropic")).preflight([{"role":"assistant","content":"lost native history"}],[])

    def test_billing_cache_semantics_unknown_and_reasoning(self):
        t=copy.deepcopy(TARIFF);t["input_accounting"]="excludes_cache"
        raw={"prompt_tokens":10,"cached_tokens":30,"cache_write_tokens":20,"completion_tokens":5}
        result=calculate(raw,t);self.assertEqual(result["tokens"]["input"],60);self.assertEqual(result["billing_buckets"]["input"],10)
        t["usage_paths"]["cache_write"]={"not_applicable":True,"basis":"fixture no cache write"};t["per_million"]["cache_write"]=0
        t["usage_paths"]["output"]=["visible","thought"]
        validate_tariff(t)
        raw.update(visible=0,thought=5)
        self.assertEqual(calculate(raw,t)["tokens"]["output"],5)
        del raw['thought'];self.assertIsNone(calculate(raw,t)["amount"])
        del raw['cached_tokens'];self.assertIsNone(calculate(raw,t)["tokens"]["cache_hit"])


    def test_native_token_counts_use_actual_tools_images_and_recover(self):
        for protocol in ("responses", "anthropic", "gemini"):
            cfg=model(protocol);cfg["estimator"]={"kind":"native_count","reserve_tokens":100,"basis":"synthetic reserve"}
            calls=[]
            def sender(endpoint, body, headers, timeout):
                calls.append((endpoint,json.loads(body)))
                return 200,{},encoded({"totalTokens" if protocol=="gemini" else "input_tokens":321})
            backend=Conversation(cfg,sender)
            messages=[{"role":"user","content":[{"type":"text","text":"JSON count"},{"type":"image_url","image_url":{"url":PNG}}]}]
            folder=self.root/protocol
            with patch.dict(os.environ,{cfg["key_env"]:"fixture-private-token-78341"}):estimate=backend.estimate(messages,SPECS,folder)
            self.assertEqual(estimate["reserved_input_tokens"],421)
            payload=json.dumps(calls[0][1]);self.assertIn("read_material",payload);self.assertIn("iVBORw0KGgo=",payload)
            self.assertNotIn("max_output_tokens",payload)
            with patch.dict(os.environ,{},clear=True):self.assertEqual(backend.estimate(messages,SPECS,folder,offline=True),estimate)
            self.assertEqual(len(calls),1)

    def test_failures_never_retry_in_each_protocol(self):
        for protocol in ("chat_completions","responses","anthropic","gemini"):
            cfg=model(protocol)
            for status,expected in [(400,"paused_configuration"),(401,"paused_account"),(429,"paused_rate_limit")]:
                calls=[]
                def sender(*args):calls.append(1);return status,{},b'{"error":"synthetic"}'
                backend=Conversation(cfg,sender)
                with patch.dict(os.environ,{cfg["key_env"]:"fixture-private-token-78341"}),self.assertRaises(Stop) as exc:
                    backend.invoke([{"role":"user","content":"JSON"}],[],self.root/(protocol+str(status)))
                self.assertEqual(exc.exception.status,expected);self.assertEqual(len(calls),1)
            calls=[]
            def timeout(*args):calls.append(1);raise TimeoutError()
            backend=Conversation(cfg,timeout);folder=self.root/(protocol+'-timeout')
            with patch.dict(os.environ,{cfg["key_env"]:"fixture-private-token-78341"}),self.assertRaises(Stop) as exc:
                backend.invoke([{"role":"user","content":"JSON"}],[],folder)
            self.assertEqual(exc.exception.status,"paused_unknown")
            with self.assertRaises(Stop):backend.recover([{"role":"user","content":"JSON"}],[],folder)
            self.assertEqual(len(calls),1)

    def test_parallel_calls_and_gemini_missing_ids(self):
        for protocol in ("responses","anthropic","gemini"):
            a=Adapter(model(protocol))
            calls=[{"id":"call"+str(i),"type":"function","function":{"name":"read_material","arguments":'{}'}} for i in range(2)]
            raw=wire_response(protocol,{"role":"assistant","content":None,"tool_calls":calls},"tool_calls")
            if protocol=="gemini":
                for part in raw["candidates"][0]["content"]["parts"]:
                    if "functionCall" in part:part["functionCall"].pop("id")
            message=a.parse(raw)["message"]
            turns=[{"role":"user","content":"JSON"},message]+[{"role":"tool","tool_call_id":call["id"],"content":'{"value":0}'} for call in message["tool_calls"]]
            body=a.build(turns,SPECS)
            if protocol=="anthropic":self.assertEqual(len(body["messages"][-1]["content"]),2)
            if protocol=="gemini":
                self.assertEqual(len(body["contents"][-1]["parts"]),2)
                self.assertNotIn("id",body["contents"][-1]["parts"][0]["functionResponse"])
            with self.assertRaises(ValueError):a.build(turns[:-1],SPECS)

    def test_compatible_vendors_have_explicit_credentials_and_no_parameter_leak(self):
        for provider,key in (("qwen","DASHSCOPE_API_KEY"),("zhipu","ZHIPU_API_KEY")):
            cfg=model("chat_completions");cfg.update(provider=provider,key_env=key)
            backend=Conversation(cfg)
            body=backend.preflight([{"role":"user","content":"JSON"}],SPECS)
            self.assertEqual(backend.key_env,key)
            self.assertEqual(body["model"],"fixture")
            for name in ("reasoning_effort","thinking","temperature","top_p"):
                self.assertNotIn(name,body)
        body=Conversation(MODEL).preflight([{"role":"user","content":"JSON"}],SPECS)
        self.assertEqual(body["reasoning_effort"],"high")
        self.assertIn("max_completion_tokens",body);self.assertNotIn("max_tokens",body)

    def test_acceptance_can_require_tool_before_json_final(self):
        from biotracebench.profiles import load
        cfg=load(Path(__file__).resolve().parents[1]/"configs/models/conversation-profiles/kimi-task-draft.json")
        cfg.update(max_output_tokens=8192,max_request_bytes=240000,tool_choice="required",response_format="text")
        first=Conversation(cfg).preflight([{"role":"user","content":"Call tool first"}],SPECS)
        self.assertEqual(first["tool_choice"],"required");self.assertNotIn("response_format",first)
        with self.assertRaises(ValueError):Conversation(cfg).preflight([{"role":"user","content":"JSON"}],[])
        cfg.update(tool_choice="none",response_format="json_object")
        final=Conversation(cfg).preflight([{"role":"user","content":"JSON"}],[])
        self.assertNotIn("tools",final);self.assertEqual(final["response_format"],{"type":"json_object"})

    def test_tool_query_mode_uses_auto_without_final_json_constraints(self):
        for protocol in ('chat_completions','responses','anthropic','gemini'):
            cfg=model(protocol);cfg['execution_mode']='tool_query'
            body=Conversation(cfg).preflight([{'role':'user','content':'Query, then JSON'}],SPECS)
            if protocol=='chat_completions':
                self.assertEqual(body['tool_choice'],'auto');self.assertNotIn('response_format',body)
            elif protocol=='responses':
                self.assertEqual(body['tool_choice'],'auto');self.assertNotIn('text',body)
            elif protocol=='anthropic':self.assertEqual(body['tool_choice'],{'type':'auto'})
            else:
                self.assertEqual(body['toolConfig']['functionCallingConfig']['mode'],'AUTO')
                self.assertNotIn('responseMimeType',body['generationConfig'])
            with self.assertRaises(ValueError):Conversation(cfg).preflight([{'role':'user','content':'Query'}],[])
            cfg['execution_mode']='final'
            final=Conversation(cfg).preflight([{'role':'user','content':'Final JSON'}],[])
            self.assertNotIn('tools',final)
            if protocol=='chat_completions':self.assertEqual(final['response_format'],{'type':'json_object'})

    def test_profiles_remain_non_executable_drafts(self):
        root=Path(__file__).resolve().parents[1]
        for path in (root/'configs/models/conversation-profiles').glob('*.json'):
            settings=load(path)
            if settings.get('estimator', {}).get('kind') == 'offline_only':
                backend = Conversation(settings)
                with self.assertRaises(Stop):
                    backend.invoke([{'role':'user','content':'JSON'}], [], Path('unused-offline-call'))
            elif settings['provider']!='kimi':
                with self.assertRaises(ValueError):Conversation(settings)
                self.assertIsNone(settings['max_output_tokens'])
            else:
                self.assertEqual(settings['context_tokens'], 1000000)
                self.assertEqual(settings['max_output_tokens'], 32768)
                self.assertIsNone(settings['max_request_bytes'])


if __name__=='__main__':unittest.main()
