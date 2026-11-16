"""Paired stratified paper statistics from offline judgment replay."""
import argparse
from collections import defaultdict
import csv
import gzip
from decimal import Decimal
import hashlib
import json
from itertools import combinations
from pathlib import Path
import platform
import numpy as np
from model_conversation.archive import exact_json
from .replay_validation import validate_replay
METRICS=tuple(f'{level}_{metric}' for level in ('field','record') for metric in ('precision','recall','f1'))

def read(path, *, lossless=False):
    raw=path.read_bytes()
    raw=gzip.decompress(raw) if path.suffix=='.gz' else raw
    return exact_json(raw) if lossless else json.loads(raw)

def bound_path(root, relative):
    p=Path(relative);target=(root/p).resolve()
    if p.is_absolute() or '..' in p.parts or not p.parts or not target.is_relative_to(root.resolve()):
        raise ValueError('Analysis artifact path must be relative and contained in the bundle')
    return target

def summarize(rows, parameters):
    domains=('basic','clinical');conditions=('i0','gsr','ssr')
    if parameters['domain_weights']!={'basic':.5,'clinical':.5}:raise ValueError('Paper protocol requires equal domain weights')
    if parameters['resamples']<1 or parameters['quantile_method']!='linear':raise ValueError('Invalid bootstrap configuration')
    models=sorted({r['model'] for r in rows});cases={d:sorted({r['case'] for r in rows if r['domain']==d}) for d in domains}
    if not all(cases.values()) or set(cases['basic']) & set(cases['clinical']):raise ValueError('Invalid domain partition')
    keys={(r['model'],r['case'],r['condition']):r for r in rows}
    expected={(m,c,s) for m in models for d in domains for c in cases[d] for s in conditions}
    if len(keys)!=len(rows) or set(keys)!=expected:raise ValueError('Incomplete paired study grid')
    rng=np.random.default_rng(parameters['seed'])
    indices={d:rng.integers(0,len(cases[d]),(parameters['resamples'],len(cases[d]))) for d in domains}
    summaries=[];changes=[];cross_model=[];initial={}
    def estimates(x,kind,meta):
        means={d:x[d].mean(0) for d in domains}
        boots={d:x[d][indices[d]].mean(1) for d in domains}
        means['overall']=(means['basic']+means['clinical'])/2
        boots['overall']=(boots['basic']+boots['clinical'])/2
        for d in (*domains,'overall'):
            values=np.concatenate(list(x.values())) if d=='overall' else x[d]
            lo,hi=np.quantile(boots[d],parameters['interval'],axis=0,method='linear')
            result={**meta,'domain':d,'n':len(values)}
            for k,q in enumerate(METRICS):
                result[q]={'mean':float(means[d][k]),'low':float(lo[k]),'high':float(hi[k])}
                if kind=='delta':result[q].update(improved=int((values[:,k]>1e-12).sum()),unchanged=int((abs(values[:,k])<=1e-12).sum()),worsened=int((values[:,k]<-1e-12).sum()))
            (changes if kind=='delta' else cross_model if kind=='cross_model' else summaries).append(result)
    for m in models:
        arrays={s:{d:np.array([[float(keys[m,c,s][q]) for q in METRICS] for c in cases[d]]) for d in domains} for s in conditions}
        initial[m]=arrays['i0']
        if any(not np.isfinite(x).all() or (x<0).any() or (x>1).any() for v in arrays.values() for x in v.values()):raise ValueError('Invalid metric values')
        for s in conditions:estimates(arrays[s],'absolute',{'model':m,'stage':s})
        for a,b in [('gsr','i0'),('ssr','i0'),('ssr','gsr')]:
            estimates({d:arrays[a][d]-arrays[b][d] for d in domains},'delta',{'model':m,'contrast':a+'-'+b})
    for a,b in combinations(models,2):
        estimates({d:initial[a][d]-initial[b][d] for d in domains},'cross_model',{'model_a':a,'model_b':b,'contrast':'i0(a)-i0(b)'})
    ranks=sorted([r for r in summaries if r['stage']=='i0' and r['domain']=='overall'],key=lambda r:(-r['field_f1']['mean'],r['model']))
    return {'summary':summaries,'delta':changes,'cross_model':cross_model,'initial_field_f1_order':[r['model'] for r in ranks],
            'parameters':parameters,'runtime':{'python':platform.python_version(),'numpy':np.__version__}}

def resource_summary(data):
    metrics=('input_tokens','output_tokens','total_tokens','tariff_estimate','cost_upper_bound','reserved_amount','billed_actual')
    groups=defaultdict(list);unknown=defaultdict(Decimal)
    for r in data['requests']:
        key=(r['model'],r['case'],r['condition'])
        if r['included']:
            groups[key].append(r)
            if r.get('tariff_estimate') is None and r.get('cost_upper_bound') is not None:
                unknown[r.get('currency','USD')]+=Decimal(str(r['cost_upper_bound']))
    stage={}
    for p in data['positions']:
        key=(p['model'],p['case'],p['condition']);rs=groups[key]
        stage[key]={**p}
        for q in metrics:
            vals=[r.get(q) for r in rs]
            stage[key][q]=sum((Decimal(str(v)) for v in vals),Decimal(0)) if p['eligible'] and vals and all(v is not None for v in vals) and all(r['confirmed'] for r in rs) else None
    summary=[]
    for m in sorted({p['model'] for p in data['positions']}):
        cases=sorted({p['case'] for p in data['positions'] if p['model']==m})
        currencies={p['currency'] for p in data['positions'] if p['model']==m}
        if len(currencies)!=1:raise ValueError('Mixed model currencies require separate summaries')
        for workflow,branches in [('i0',['i0']),('gsr',['gsr']),('ssr',['ssr']),('i0+gsr',['i0','gsr']),('i0+ssr',['i0','ssr'])]:
            out={'model':m,'workflow':workflow,'currency':next(iter(currencies)),'planned_n':len(cases)}
            for q in metrics:
                vals=[]
                for c in cases:
                    v=[stage[m,c,s][q] for s in branches]
                    if all(x is not None for x in v):vals.append(sum(v,Decimal(0)))
                out[q]={'n':len(vals),'sum':str(sum(vals,Decimal(0))) if vals else None,
                        'mean':str(sum(vals,Decimal(0))/len(vals)) if vals else None}
            summary.append(out)
    return {'summary':summary,'unknown_consumption_upper_bounds':{k:str(v) for k,v in unknown.items()},
            'basis':data.get('basis'), 'unselected_requests':sum(not r['included'] for r in data['requests'])}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--replay',required=True);p.add_argument('--manifest',required=True);p.add_argument('--out',required=True)
    p.add_argument('--corrections',help='Required for candidate analysis: the same overlay used by replay')
    a=p.parse_args(argv);manifest_path=Path(a.manifest).resolve();manifest=read(manifest_path);replayed=read(Path(a.replay))
    if replayed['baseline_manifest_sha256']!=hashlib.sha256(manifest_path.read_bytes()).hexdigest():raise ValueError('Replay and analysis manifest differ')
    for name,wanted in manifest['files'].items():
        if hashlib.sha256(bound_path(manifest_path.parent,name).read_bytes()).hexdigest()!=wanted:
            raise ValueError('Analysis bundle hash mismatch: '+name)
    reference_paths={c['reference'] for c in manifest['cases']}
    def artifact(name):
        path=bound_path(manifest_path.parent,name)
        if manifest['files'].get(name)!=hashlib.sha256(path.read_bytes()).hexdigest():raise ValueError('Analysis artifact hash mismatch')
        return read(path,lossless=name in reference_paths)
    corrections_path=Path(a.corrections) if a.corrections else None
    validate_replay(replayed,manifest,artifact,read(corrections_path) if corrections_path else None,
                    hashlib.sha256(corrections_path.read_bytes()).hexdigest() if corrections_path else None)
    result=summarize(replayed['scores'],artifact(manifest['analysis']))
    if manifest.get('resources'):result['resources']=resource_summary(artifact(manifest['resources']))
    result['baseline_manifest_sha256']=replayed['baseline_manifest_sha256'];result['candidate']=replayed['candidate']
    result['corrections_sha256']=replayed.get('corrections_sha256')
    result['consistency_signature_version']=replayed.get('consistency_signature_version','legacy-float-1')
    out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    (out/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    for name,items in [('absolute',result['summary']),('paired',result['delta']),('cross-model',result['cross_model'])]:
        if not items:continue
        flat=[{**{k:v for k,v in r.items() if k not in METRICS},**{q+'_'+k:v for q in METRICS for k,v in r[q].items()}} for r in items]
        with (out/(name+'.csv')).open('w',newline='') as f:
            w=csv.DictWriter(f,list(flat[0]));w.writeheader();w.writerows(flat)
    print(json.dumps({'summary_groups':len(result['summary']),'contrast_groups':len(result['delta']),'candidate':result['candidate']}))
    return 0

if __name__=='__main__':raise SystemExit(main())
