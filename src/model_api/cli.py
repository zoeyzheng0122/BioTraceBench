"""Generic model invocation; callers own payloads, schemas and interpretation."""
import argparse,json
from dataclasses import asdict
from pathlib import Path
from . import Backend, implementation_identity
from ._json import loads

def main(argv=None):
    parser=argparse.ArgumentParser(description="Model API transport (no table pipeline)")
    parser.add_argument("command",choices=("describe","preflight","invoke","recover"))
    parser.add_argument("--profile",required=True)
    parser.add_argument("--request",help="UTF-8 JSON request envelope supplied by the caller")
    parser.add_argument("--attempt-dir",help="Unique directory for one physical invocation")
    args=parser.parse_args(argv)
    backend=Backend(args.profile)
    if args.command=="describe":
        result={"backend":asdict(backend.describe()),"implementation":implementation_identity()}
    else:
        if not args.request: parser.error("--request is required")
        request=loads(Path(args.request).read_text(encoding="utf-8"))
        if args.command=="preflight":
            backend.preflight(request)
            result={"valid":True,"network_requests":0}
        else:
            if not args.attempt_dir: parser.error("--attempt-dir is required")
            result=getattr(backend,args.command)(request,args.attempt_dir)
            result=result.as_dict() if result is not None else None
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    return 0
