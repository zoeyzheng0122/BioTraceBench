#!/usr/bin/env python3
"""Build a deterministic allowlisted source archive with SHA-256 file identities."""
from pathlib import Path
import argparse,hashlib,json,zipfile
from check_repository import ROOT,check,publication_files

def build(out):
 check();out=Path(out).resolve()
 if out.is_relative_to(ROOT):raise ValueError('Build outside the repository')
 out.mkdir(parents=True,exist_ok=True);target=out/'BioTraceBench-source.zip'
 if target.exists():raise FileExistsError(target)
 data={str(p.relative_to(ROOT)):p.read_bytes()for p in publication_files()}
 identity={name:hashlib.sha256(b).hexdigest()for name,b in data.items()}
 manifest={'format':'biotracebench-source-archive-1','files':identity}
 with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED)as archive:
  for name,b in sorted(data.items()):
   info=zipfile.ZipInfo('BioTraceBench/'+name,date_time=(2026,11,16,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;archive.writestr(info,b)
  archive.writestr('source-manifest.json',json.dumps(manifest,indent=2)+'\n')
 digest=hashlib.sha256(target.read_bytes()).hexdigest();target.with_suffix('.zip.sha256').write_text(digest+'  '+target.name+'\n')
 return {'archive':str(target),'sha256':digest,'files':len(data)}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);print(json.dumps(build(p.parse_args().out),indent=2))
