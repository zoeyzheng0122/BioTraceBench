"""Exercise the SDK with no pipeline code on the import path."""
import os,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class IsolationTests(unittest.TestCase):
    def test_two_unrelated_callers_and_offline_recovery_without_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);shutil.copytree(ROOT/"src/model_api",root/"model_api")
            code=r'''import importlib.util,json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
assert importlib.util.find_spec("curation_core") is None
from model_api import Backend,implementation_identity
p={"profile_version":1,"name":"offline","provider":"synthetic","protocol":"chat_completions","endpoint":"https://example.invalid/v1/chat/completions","model":"synthetic-model","key_env":"SDK_TEST_KEY","vision":False,"structured_output":"json_object","context_tokens":100000,"max_output_tokens":1000,"max_input_bytes":50000,"max_images":0,"image_token_reserve":0,"output_token_field":"max_tokens","generation":{},"timeout":30}
seen=[]
def sender(url,body,headers,timeout):
    seen.append(json.loads(body))
    return 200,{},json.dumps({"choices":[{"message":{"content":"{\"ok\":true}"},"finish_reason":"stop"}]}).encode()
b=Backend(p,sender=sender)
for i,(stage,payload) in enumerate([("translate",{"text":"hello"}),("classify",{"ticket":"printer offline"})]):
    req={"protocol_version":"independent-caller-1","stage":stage,"instruction":stage,"payload":payload,"response_schema":{"type":"object"},"images":[]}
    folder=Path(sys.argv[1])/str(i)
    result=b.invoke(req,folder)
    assert json.loads(result.text)=={"ok":True}
    def forbidden(*a): raise AssertionError("recovery attempted network")
    assert Backend(p,sender=forbidden).recover(req,folder).text==result.text
assert len(seen)==2 and seen[0]!=seen[1]
assert not any(k.startswith(("curation_core","basic_curation","risk_curation","openpyxl")) for k in sys.modules)
assert implementation_identity()["interface"]=="model-api-1"
'''
            env={**os.environ,"SDK_TEST_KEY":"synthetic-credential"}
            run=subprocess.run([sys.executable,"-I","-B","-c",code,str(root)],cwd=root,env=env,capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_api_distribution_excludes_business_sources(self):
        import json
        spec=json.loads((ROOT/"configs/distribution.json").read_text())
        self.assertEqual(spec["name"],"eab-model-api")
        self.assertEqual(spec["version"],"1.0.0")
        self.assertEqual([p for p in spec["prefixes"] if p.startswith("src/")],["src/model_api/"])
