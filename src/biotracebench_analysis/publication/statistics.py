"""Study-stratified bootstrap summaries and recorded resource accounting."""
from collections import defaultdict
from decimal import Decimal
from itertools import combinations
import platform
METRICS=tuple(f"{level}_{metric}" for level in ("field","record") for metric in ("precision","recall","f1"))

def summarize(rows,parameters):
    import numpy as np
    domains=('basic','clinical');models=sorted({r['model'] for r in rows})
    cases={d:sorted({r['case'] for r in rows if r['domain']==d}) for d in domains}
    keys={(r['model'],r['case']):r for r in rows}
    if len(keys)!=len(rows) or set(keys)!={(m,c) for m in models for d in domains for c in cases[d]}:
        raise ValueError('Missing or duplicate model/study result')
    rng=np.random.default_rng(parameters['seed'])
    indices={d:rng.integers(0,len(cases[d]),(parameters['resamples'],len(cases[d]))) for d in domains}
    summary=[];cross=[];arrays={}
    def estimates(x,meta,dest):
        means={d:np.nanmean(x[d],axis=0) for d in domains};boots={d:np.nanmean(x[d][indices[d]],axis=1) for d in domains}
        means['overall']=(means['basic']+means['clinical'])/2;boots['overall']=(boots['basic']+boots['clinical'])/2
        for d in (*domains,'overall'):
            lo,hi=np.nanquantile(boots[d],parameters['interval'],axis=0,method='linear')
            r={**meta,'domain':d,'n':sum(len(v) for v in x.values()) if d=='overall' else len(x[d])}
            for i,q in enumerate(METRICS):r[q]={'mean':float(means[d][i]),'low':float(lo[i]),'high':float(hi[i])}
            dest.append(r)
    for m in models:
        arrays[m]={d:np.array([[float(keys[m,c][q]) if keys[m,c][q] not in (None,'') else np.nan for q in METRICS] for c in cases[d]]) for d in domains}
        if any(np.isinf(a).any() or (a[np.isfinite(a)]<0).any() or (a>1).any() for a in arrays[m].values()):raise ValueError('Invalid score')
        estimates(arrays[m],{'model':m},summary)
    for a,b in combinations(models,2):estimates({d:arrays[a][d]-arrays[b][d] for d in domains},{'model_a':a,'model_b':b},cross)
    order=sorted([r for r in summary if r['domain']=='overall'],key=lambda r:(-r['field_f1']['mean'],r['model']))
    return {'summary':summary,'cross_model':cross,'field_f1_order':[r['model'] for r in order],
            'parameters':parameters,'runtime':{'python':platform.python_version(),'numpy':np.__version__}}

def resources(data):
    metrics=('input_tokens','output_tokens','total_tokens','tariff_estimate','cost_upper_bound','reserved_amount','billed_actual')
    groups=defaultdict(list)
    for r in data['requests']:
        if r['included']:groups[r['model'],r['case']].append(r)
    study=[]
    for p in data['positions']:
        rs=groups[p['model'],p['case']];r={k:v for k,v in p.items() if k!='condition'}
        for q in metrics:
            vals=[v.get(q) for v in rs]
            r[q]=str(sum((Decimal(str(v)) for v in vals),Decimal(0))) if p['eligible'] and vals and all(v is not None for v in vals) and all(v['confirmed'] for v in rs) else None
        study.append(r)
    summary=[]
    for m in sorted({p['model'] for p in study}):
        ps=[p for p in study if p['model']==m];r={'model':m,'currency':ps[0]['currency'],'planned_n':len(ps)}
        for q in metrics:
            vals=[Decimal(p[q]) for p in ps if p[q] is not None]
            r[q]={'n':len(vals),'sum':str(sum(vals,Decimal(0))) if vals else None,'mean':str(sum(vals,Decimal(0))/len(vals)) if vals else None}
        summary.append(r)
    return {'summary':summary,'studies':study,'basis':data.get('basis')}
