"""Standalone JSON and file identity utilities."""
import hashlib,json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
class Violation(ValueError): pass

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',',':'), allow_nan=False).encode()).hexdigest()

def filehash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for piece in iter(lambda:stream.read(1024*1024),b''): h.update(piece)
    return h.hexdigest()

def now(): return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')

def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))

def write(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    temp.replace(path)

def loads(text):
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise Violation('duplicate JSON key: '+k)
            out[k]=v
        return out
    def constant(value):raise Violation('nonfinite JSON constant: '+value)
    return json.loads(text,object_pairs_hook=pairs,parse_constant=constant)
