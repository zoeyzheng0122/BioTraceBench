#!/usr/bin/env python3
"""Build a reproducible, allowlisted source package without installing software."""
import argparse,hashlib,json,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def build(destination):
    spec=json.loads((ROOT/"configs/distribution.json").read_text())
    paths=[str(p.relative_to(ROOT))for p in ROOT.rglob('*')if p.is_file()and'__pycache__'not in p.parts and'.git'not in p.parts]
    commit='unversioned-source-tree';dirty=True
    if (ROOT/'.git').exists():
        state=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,text=True,capture_output=True)
        if state.returncode==0:commit=state.stdout.strip();dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT))
    files={}
    for name in sorted(filter(None,paths)):
        if name in spec["files"] or any(name.startswith(p) for p in spec["prefixes"]):
            path=ROOT/name
            if path.is_symlink() or not path.is_file(): raise ValueError("nonregular package input: "+name)
            files[name]=path.read_bytes()
    for name in spec["required"]:
        if name not in files: raise ValueError("package file missing or untracked: "+name)
    files["README.md"]=(ROOT/spec["guide"]).read_bytes()
    manifest={"name":spec["name"],"version":spec["version"],"interface":spec["interface"],
              "dependency":spec.get("dependency"),
              "source_dirty":dirty,
              "source_commit":commit,
              "files":{p:hashlib.sha256(v).hexdigest() for p,v in files.items()}}
    files["package-manifest.json"]=(json.dumps(manifest,sort_keys=True,indent=2)+"\n").encode()
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    target=destination/(spec["name"]+"-"+spec["version"]+".zip")
    if target.exists(): raise ValueError("package already exists; use a new output directory")
    with zipfile.ZipFile(target,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,10,21,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16;z.writestr(info,data)
    checksum=hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(checksum+"  "+target.name+"\n")
    return {"path":str(target.resolve()),"sha256":checksum,"file_count":len(files),"version":spec["version"]}

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--out",required=True)
    print(json.dumps(build(p.parse_args().out),indent=2))
