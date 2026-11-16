#!/usr/bin/env python3
"""Check the publication-code allowlist, source boundaries and figure integrity."""
from pathlib import Path
import argparse,hashlib,json,re
ROOT=Path(__file__).resolve().parents[1]
ROOT_FILES={'README.md','pyproject.toml','THIRD_PARTY.md','MANIFEST.in','.gitignore','.gitattributes'}
IGNORED={'.git','__pycache__','.venv','.pytest_cache','build','dist'}
def allowed(name):
 p=Path(name);suffix=p.suffix
 if len(p.parts)==1:return name in ROOT_FILES
 top=p.parts[0]
 return (top=='src'and(suffix=='.py'or suffix=='.json'and p.parts[1:3]==('biotracebench','publication_configs'))
  or top=='configs'and suffix in{'.json','.txt'}
  or top=='tests'and(suffix=='.py'or suffix in{'.json','.md'}and p.parts[1]=='fixtures'or name=='tests/README.md')
  or top=='scripts'and suffix=='.py'
  or top=='docs'and(suffix=='.md'or name=='docs/source_provenance.json')
  or top=='figures'and(suffix in{'.png','.svg'}or p.name in{'README.md','sha256.json'})
  or name=='.github/workflows/ci.yml')
def publication_files(root=ROOT):
 for p in sorted(root.rglob('*')):
  rel=p.relative_to(root)
  if any(x in IGNORED or x.endswith('.egg-info')for x in rel.parts):continue
  if p.is_symlink():raise ValueError('Symlink is outside the publication contract: '+str(rel))
  if p.is_file():
   if not allowed(str(rel)):raise ValueError('File is outside publication allowlist: '+str(rel))
   yield p

def check(root=ROOT):
 files=list(publication_files(root));byte_count=0
 for p in files:
  data=p.read_bytes();byte_count+=len(data)
  if p.suffix in{'.py','.json','.txt','.md','.toml','.yml','.in'}:
   text=data.decode('utf-8')
   if re.search(r'/[U]sers/|/[h]ome/(?!runner(?:/|$))',text):raise ValueError('Personal absolute path: '+str(p.relative_to(root)))
   if re.search(r'(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{32,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',text):raise ValueError('Credential material: '+str(p.relative_to(root)))
   if p.suffix=='.json':
    doc=json.loads(text)
    if isinstance(doc,dict)and doc.get('identity_task_rules'):raise ValueError('Study-specific identity decisions belong in external materials')
    if isinstance(doc,dict)and(doc.get('case_specific_existing_permission')or doc.get('unit_catalog',{}).get('case_specific_existing_permission')):raise ValueError('Study-specific unit permissions belong in external materials')
 for section in['scoring','schemas']:
  for p in(root/'configs'/section).glob('*.json'):
   if p.read_bytes()!=(root/'src/biotracebench/publication_configs'/section/p.name).read_bytes():raise ValueError('Wheel policy differs: '+p.name)
 for p in [root/'README.md',*list((root/'docs').rglob('*.md')),*list((root/'figures').glob('*.md'))]:
  for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',p.read_text()):
   if '://'in target or target.startswith('#'):continue
   path=(p.parent/target.split('#')[0]).resolve()
   if not path.exists():raise ValueError('Broken documentation link: '+str(p.relative_to(root))+' -> '+target)
 hashes=json.loads((root/'figures/sha256.json').read_text())
 for name,want in hashes.items():
  if hashlib.sha256((root/'figures'/name).read_bytes()).hexdigest()!=want:raise ValueError('Manuscript figure changed: '+name)
 if len(hashes)!=18:raise ValueError('Expected nine figures in two formats')
 return {'status':'passed','files':len(files),'bytes':byte_count,'figures':len(hashes),'scope':'publication code, synthetic tests and manuscript figures'}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT);print(json.dumps(check(p.parse_args().root.resolve()),indent=2))
