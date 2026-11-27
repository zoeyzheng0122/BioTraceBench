"""External material bindings and deterministic UTF-8 serialization."""
from pathlib import Path
from importlib.resources import files
import csv,gzip,hashlib,json

def read(p):
 p=Path(p);return json.loads(gzip.decompress(p.read_bytes())if p.suffix=='.gz'else p.read_bytes())
def write(p,data):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def rows(p):
 with Path(p).open(encoding='utf-8-sig',newline='')as source:return list(csv.DictReader(source))
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
 def __init__(self,root,evaluation_root=None):
  self.root=Path(root).resolve()
  manifest_path=self.root/'manifest.json'
  self.formal=manifest_path.is_file() and read(manifest_path).get('format')=='biotracebench-submission-1'
  if not self.formal:
   raise ValueError('Missing submission manifest: supply --artifact-root')
  self.manifest=read(manifest_path)
  path_names=('repro','published','inputs','baseline','materials','outputs','plot_data',
              'human_inputs','reviewed_diagnostics','figure_table_index','reference_inputs',
              'analysis_package','bindings','annotations')
  paths=self.manifest['paths']
  for name in path_names:
   if name not in paths:
    if name in {'published','materials','annotations'}:
     raise ValueError('Missing material path in manifest: '+name)
    continue
   relative=Path(paths[name]);path=(self.root/relative).resolve()
   if relative.is_absolute() or '..' in relative.parts or not path.is_relative_to(self.root):
    raise ValueError('Material path leaves the package: '+name)
   setattr(self,name,path)
  if evaluation_root is not None:self.published=Path(evaluation_root).resolve()
  if not(self.published/'source-dispositions.json').is_file():raise ValueError('Benchmark materials not found: supply the external benchmark materials directory with --artifact-root')
 def policy(self,case):
  config=files('biotracebench')/'review_configs/scoring'
  domain='basic'if case.startswith('B')else'clinical';p=read(config/'policy.json');p['field_roles']=read(config/'field_roles.json')[domain];p['reference_contract']='biotracebench-fixed-reference-1';p.pop('compound_fields',None);return p,read(config/(domain+'.json'))
