"""Export study statistics, transition counts and unresolved review locations."""
import argparse
from pathlib import Path
from model_conversation.archive import read,write,digest,seal,sha
from .statistics import aggregate,compare_conditions,condition_names
from biotracebench.conditions import CANONICAL,CONTRASTS,TO_LEGACY

def main(argv=None):
    p=argparse.ArgumentParser(prog="biotracebench_analysis")
    p.add_argument("--scores",required=True);p.add_argument("--config",required=True);p.add_argument("--out",required=True)
    a=p.parse_args(argv);studies=read(a.scores);config=read(a.config)
    result=aggregate(studies,config["bootstrap_seed"],config["bootstrap_resamples"])
    changes=[]
    stages=condition_names(studies)
    contrasts=CONTRASTS if stages==CANONICAL else [(TO_LEGACY[x],TO_LEGACY[y]) for x,y in CONTRASTS]
    for study in studies:
        changes.append({"study_id":study["study_id"],"changes":{x+"-"+y:
            compare_conditions(study["conditions"][y],study["conditions"][x])
            if x in study["conditions"] and y in study["conditions"] else
            {"status":"unavailable_output","pending_review":[{"condition":s,"reason":"missing_score"}
                for s in (y,x) if s not in study['conditions']]} for x,y in contrasts}})
    out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    pending=result.pop('pending_review')
    result['pending_review_file']='pending-review.json'
    write(out/"summary.json",result);write(out/"changes.json",changes)
    write(out/"pending-review.json",pending)
    write(out/"identity.json",{"scores":digest(studies),"config":config,"config_hash":digest(config),
        "implementation":{"statistics":sha(Path(__file__).with_name('statistics.py')),"entrypoint":sha(__file__)}})
    seal(out)
    return 0

if __name__=="__main__":raise SystemExit(main())
