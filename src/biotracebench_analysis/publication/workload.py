"""Descriptive task workload and distinct supplied sources."""
from pathlib import Path
import re
from .io import read,rows,write

def source_groups(manifest):
 files=[f for f in manifest['files']if f.get('input_use')=='model'];groups={}
 repo_pat=r'(NCT\d+|GSE\d+|PXD\d+|PRJ[A-Z]+\d+|E-[A-Z]+-\d+|ERP\d+|EGAS\d+|SRP\d+|Zenodo-\d+|Figshare-(?:m9\.figshare\.)?\d+|ACTRN\d+|DRKS\d+|ISRCTN\d+|ChiCTR\d+|CTRI-\d+-\d+-\d+)'
 repository_ids=set()
 for f in files:
  if f['path'].startswith('records/'):
   found=re.findall(repo_pat,f['path'])
   if found:repository_ids.add(found[0].replace('m9.figshare.',''))
 for f in files:
  path=f['path'];parts=path.split('/')
  if parts[0]in['sources','figures']:g='article'
  elif parts[0]=='supplements':g='supplement:'+parts[1].split('__refine')[0]
  elif parts[0]=='records':
   found=re.findall(repo_pat,path)
   if found:g='repository:'+found[0].replace('m9.figshare.','')
   elif 'Dryad' in path or'DOI-dryad.'in path:g='repository:Dryad-'+next(x.split('dryad.')[-1].split('/')[0].split('.')[0]for x in [q['path']for q in files]if'DOI-dryad.'in x)
   elif path.startswith('records/DOI-'):g='repository:'+Path(parts[1]).stem
   elif parts[1]in['CE-MS-sample-header-metadata.csv','Sample_Code__refine']:
    candidates=[x for x in repository_ids if x.startswith('PXD')];assert len(candidates)==1;g='repository:'+candidates[0]
   else:g='repository:'+parts[1].split('__refine')[0].rsplit('.',1)[0]
  else:raise ValueError('Unmapped source: '+path)
  groups[path]={'source_group':g,'sha256':f['sha256']}
 return groups

def summarize(artifact,out):
 import numpy as np
 from model_conversation.archive import read_exact
 from biotracebench_scoring.task_grading_contract import inventory
 data=rows(artifact.baseline/'complexity/task_complexity.csv');sources={}
 for p in sorted((artifact.materials/'metadata/manifests').rglob('*.json')):
  d=read(p);sources[p.stem]={'domain':d['case']['domain'],'file_groups':source_groups(d)}
 for row in data:
  case=row['case'];policy,dic=artifact.policy(case);inv=inventory({},read_exact(artifact.published/'projection/references'/(case+'.json')),dic,policy);rr=[r for r in inv['rows']if r['side']=='reference'];ww=[sum(c['row']==r['id']and c['nonempty']and c['role']=='scientific'for c in inv['cells'])for r in rr]
  if len(rr)!=int(row['record_count'])or float(np.median(ww))!=float(row['width_median']):raise ValueError('Reference workload differs from the bound task inventory')
 result={}
 for domain in['clinical','basic','overall']:
  rr=[r for r in data if domain=='overall'or r['domain']==domain];cases={r['case']for r in rr};counts=[len({x['source_group']for x in sources[c]['file_groups'].values()})for c in cases]
  result[domain]={'tasks':len(rr),'reference_records':sum(int(r['record_count'])for r in rr),'width_quartiles':np.quantile([float(r['width_median'])for r in rr],[.25,.5,.75],method='linear').tolist(),'links_quartiles':np.quantile([int(r['relation_count'])for r in rr],[.25,.5,.75],method='linear').tolist(),'sources_min_median_max':np.quantile(counts,[0,.5,1],method='linear').tolist(),'median_records':float(np.median([int(r['record_count'])for r in rr]))}
 write(out/'workload.json',result);write(out/'source-groups.json',sources);return result
