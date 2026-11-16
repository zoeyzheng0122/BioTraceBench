"""Build and exercise the released layout, outside the repository checkout."""
import hashlib,json,os,subprocess,sys,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class DistributionTests(unittest.TestCase):
    def test_source_distribution_is_complete_and_runs_outside_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            built=subprocess.run([sys.executable,"-B",str(ROOT/"scripts/build_component.py"),"--out",str(root)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            package=Path(json.loads(built.stdout)["path"])
            unpacked=root/"unpacked"
            with zipfile.ZipFile(package) as z:z.extractall(unpacked)
            manifest=json.loads((unpacked/"package-manifest.json").read_text())
            for name,sha in manifest["files"].items():
                self.assertEqual(hashlib.sha256((unpacked/name).read_bytes()).hexdigest(),sha,name)
            self.assertFalse((unpacked/"src/curation_core").exists())
            code="import sys;sys.path.insert(0,sys.argv[1]);import model_api,importlib.util;assert importlib.util.find_spec('curation_core') is None;assert model_api.__version__=='1.0.0'"
            p=subprocess.run([sys.executable,"-I","-B","-c",code,str(unpacked/"src")],cwd=root,capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            env={**os.environ,"PYTHONPATH":str(unpacked/"src")}
            p=subprocess.run([sys.executable,"-B","-m","model_api","describe","--profile",str(unpacked/"configs/models/profiles/openai-text-example.json")],cwd=root,env=env,capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(json.loads(p.stdout)["implementation"]["version"],"1.0.0")
            for name in ["configs/models/profiles/kimi-k3-text.json", "configs/models/vendors/kimi.json",
                         "scripts/kimi_api_smoke.py", "tests/fixtures/kimi-api-smoke.json", "tests/test_sdk_kimi.py",
                         "docs/development/kimi-api.md"]:
                self.assertIn(name, manifest["files"])
            env.pop("MOONSHOT_API_KEY", None)
            p=subprocess.run([sys.executable,"-I","-B",str(unpacked/"scripts/kimi_api_smoke.py"),"preflight"],
                             cwd=root,env=env,capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(json.loads(p.stdout)["network_requests"],0)
            p=subprocess.run([sys.executable,"-B","-m","unittest","discover","-s",str(unpacked/"tests"),"-p","test_sdk_kimi.py"],
                             cwd=root,env=env,capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
