"""Study-equal record-width and source-combination analyses."""
from collections import Counter,defaultdict
import csv,warnings
import numpy as np
from .io import read,write,csvwrite,rows

def loadcsv(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))

def intervals(v,domain_cases,indices):
    a=np.array([v.get(c,np.nan)for c in domain_cases],dtype=float)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',RuntimeWarning);boots=np.nanmean(a[indices],axis=1)
    good=boots[np.isfinite(boots)]
    lo,hi=np.quantile(good,[.025,.975],method='linear') if len(good)else [np.nan,np.nan]
    return float(np.nanmean(a)),float(lo),float(hi)

def record_analyses(scores,artifact,out):
    ROOT=out;BASE=artifact.baseline;REVISION=read(artifact.published/'current-result-contract.json')['version']
    observations=loadcsv(ROOT/'projection/record-observations.csv')
    labels=rows(artifact.published/'source-record-labels.csv');labels=[{**r,'row_index':int(r['row_index']),'width':int(r['width'])}for r in labels];labelmap={(r['case'],r['table'],r['row_index']):r for r in labels}
    excluded={(r['case'],r['table'],r['row_index'])for r in labels if r['final_source_classification']=='excluded'}
    zero={(r['case'],r['model']):r['zero_output']=='True'for r in scores if r['condition']=='i0'}
    rec=[]
    for r in observations:
        if r['condition']!='i0' or r['eligible']!='True':continue
        key=r['case'],r['table'],int(r['row_index']);lab=labelmap[key]
        classification=lab['final_source_classification']
        if key in excluded:classification='excluded'
        rec.append(dict(case=r['case'],domain=r['domain'],model=r['model'],table=r['table'],row_index=int(r['row_index']),width=int(lab['width']),complete=int(r['complete']=='True'),evaluable=int(not zero[r['case'],r['model']]),source=classification))
    csvwrite(ROOT/'record-observations.csv',rec)
    cases={d:sorted({r['case']for r in scores if r['domain']==d})for d in ['basic','clinical']}
    rng=np.random.default_rng(20261110);idx={d:rng.integers(0,50,(10000,50))for d in ['basic','clinical']}
    width_results=[];source_rates=[];paired_results=[]
    for sensitivity in [False,True]:
        sub=[r for r in rec if sensitivity or r['evaluable']]
        groups=defaultdict(lambda:defaultdict(lambda:[0,0]))
        for r in sub:
            k=r['domain'],r['table'],r['width'];g=groups[k][r['case'],r['model']];g[0]+=r['complete'];g[1]+=1
        for (d,t,w),by in groups.items():
            studies=defaultdict(list)
            for (c,m),(n,total)in by.items():studies[c].append(n/total)
            vals={c:float(np.mean(v))for c,v in studies.items()};est,lo,hi=intervals(vals,cases[d],idx[d])
            width_results.append(dict(group=f'{d}|{t}|{w}',domain=d,table=t,width=w,n_studies=len(vals),estimate_study_equal=est,low=lo,high=hi,sensitivity=sensitivity))
        for d in ['basic','clinical']:
            for label in ['single','multiple']:
                by=defaultdict(lambda:[0,0])
                for r in sub:
                    if r['domain']==d and r['source']==label:
                        g=by[r['case'],r['model']];g[0]+=r['complete'];g[1]+=1
                study=defaultdict(list)
                for (c,m),(n,total)in by.items():study[c].append(n/total)
                vals={c:float(np.mean(v))for c,v in study.items()};est,lo,hi=intervals(vals,cases[d],idx[d])
                source_rates.append(dict(domain=d,source=label,n_studies=len(vals),recall=est,low=lo,high=hi,sensitivity=sensitivity))
            for t in sorted({r['table']for r in sub if r['domain']==d}):
                by=defaultdict(lambda:[0,0])
                for r in sub:
                    if r['domain']==d and r['table']==t and r['source']in ['single','multiple']:
                        g=by[r['case'],r['model'],r['width'],r['source']];g[0]+=r['complete'];g[1]+=1
                within=defaultdict(list)
                for c,m,w,label in by:
                    if label=='single'and(c,m,w,'multiple')in by:
                        a,an=by[c,m,w,'single'];b,bn=by[c,m,w,'multiple'];within[c,m].append(b/bn-a/an)
                study=defaultdict(list)
                for (c,m),v in within.items():study[c].append(float(np.mean(v)))
                vals={c:float(np.mean(v))for c,v in study.items()}
                if not vals:continue
                est,lo,hi=intervals(vals,cases[d],idx[d]);eligible=len(vals)>=10
                paired_results.append(dict(domain=d,table=t,paired_studies=len(vals),difference_multi_minus_single=est,ci_low=lo if eligible else None,ci_high=hi if eligible else None,interval_eligible=eligible,sensitivity=sensitivity))
    csvwrite(ROOT/'width-results.csv',width_results);csvwrite(ROOT/'source-rates.csv',source_rates);csvwrite(ROOT/'source-paired.csv',paired_results)
    source_counts=Counter(r['final_source_classification']for r in labels)
    projection=read(ROOT/'projection/manifest.json')
    final_labels=[]
    for r in labels:
        key=r['case'],r['table'],r['row_index']
        label=r['final_source_classification']
        final_labels.append({**r,'final_source_classification':label,'execution_version':REVISION})
    csvwrite(ROOT/'source-record-labels.csv',final_labels)
    by_domain={d:dict(Counter(r['final_source_classification']for r in final_labels if r['domain']==d))for d in ['basic','clinical']}
    write(ROOT/'source-summary.json',dict(counts=source_counts,by_domain=by_domain,multiple_source_studies=len({r['case']for r in final_labels if r['final_source_classification']=='multiple'}),total_reference_records=len(labels),primary_record_eligible=projection['record_eligible_reference_count'],excluded_from_source_comparison=len(excluded),content_support_excluded_records=projection['excluded_reference_records'],supported_content_source_only_exclusions=sum(r['final_disposition']=='source_combination_exclusion'for r in read(ROOT/'source-dispositions.json')),author_policy_source_exclusions=sum(r['final_disposition']=='author_adjudicated_conflict'for r in read(ROOT/'source-dispositions.json')),pending_decisions=0))
