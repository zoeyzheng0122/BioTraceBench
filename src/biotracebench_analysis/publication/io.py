"""External material bindings and deterministic UTF-8 serialization."""
from pathlib import Path
import csv,gzip,hashlib,json

def read(p):
 p=Path(p);return json.loads(gzip.decompress(p.read_bytes())if p.suffix=='.gz'else p.read_bytes())
def write(p,data):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def rows(p):return list(csv.DictReader(Path(p).open(encoding='utf-8-sig')))
def csvwrite(p,data):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 if not data:return
 with p.open('w',encoding='utf-8-sig',newline='')as f:
  w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for row in data for k in row)));w.writeheader();w.writerows(data)
def digest(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for block in iter(lambda:f.read(4194304),b''):h.update(block)
 return h.hexdigest()
class Artifact:
 def __init__(self,root):
  self.root=Path(root).resolve();self.repro=self.root/'04_Reproducibility';self.published=self.repro/'02_Published_Evaluation';self.inputs=self.repro/'03_Experiments/inputs';self.baseline=self.inputs/'baseline';self.materials=self.root/'03_Benchmark_Data/01_Task_Materials'
  if not(self.published/'source-dispositions.json').is_file():raise ValueError('Benchmark materials not found: supply the external publication materials directory with --artifact-root')
 def policy(self,case):
  from copy import deepcopy
  config=Path(__file__).resolve().parents[3]/'configs/scoring'
  if not config.exists():
   import importlib.resources
   config=Path(str(importlib.resources.files('biotracebench')/'publication_configs/scoring'))
  domain='basic'if case.startswith('B')else'clinical';p=deepcopy(read(config/'policy.json'));p['field_roles']=read(config/'field_roles.json')[domain];p['reference_contract']='biotracebench-fixed-reference-1';p.pop('compound_fields',None);return p,read(config/(domain+'.json'))
