"""Deterministic literal-copy rule tests with one-to-one scientific identities."""
import json,re
from .attribution import norm,content_bag
IDENTITY={
 'sample':('sample_name','sample_accession'),
 'population':('population_name',),'measure':('measure_name',),
 'condition':('sample_id','condition_target','experimental_factor','time'),
 'assay_run':('sample_ids','assay_type','experiment_run_accession','platform'),
 'result':('population_id','measure_id','assessment_time','statistic_type','statistical_method','comparison'),
 'population_relation':('population_a_id','population_b_id','relationship'),
}

def evaluate(pred,gold,dic):
    maps={};idmaps={};pairs={};ambiguous=[]
    projected={}
    order=sorted(dic,key=lambda t:bool(dic[t].get('references')))
    for table in order:
        spec=dic[table];rows=json.loads(json.dumps(pred.get(table,[])))
        for row in rows:
            for field,target in spec.get('references',{}).items():
                value=row.get(field)
                if isinstance(value,list):row[field]=[idmaps.get((target,str(v)),f'unmatched:{v}') for v in value]
                elif value is not None:row[field]=idmaps.get((target,str(value)),f'unmatched:{value}')
            if isinstance(row.get('comparison'),str):
                import re
                pop_ids={str(r['population_id']):str(idmaps.get(('population',str(r['population_id'])),r['population_id'])) for r in pred.get('population',[])}
                if pop_ids:
                    pattern=r'(?<![A-Za-z0-9_])('+'|'.join(re.escape(k) for k in sorted(pop_ids,key=len,reverse=True))+r')(?![A-Za-z0-9_])'
                    row['comparison']=re.sub(pattern,lambda m:pop_ids[m.group(0)],row['comparison'])
        projected[table]=rows
        if table=='result':
            import re
            for row in rows:
                # Gold-derived literal-copy rule test: all other identity
                # attributes and the full comparison must identify one row.
                candidates=[g for g in gold.get(table,[]) if all(norm(row.get(f))==norm(g.get(f)) for f in IDENTITY[table] if f!='population_id')]
                if len(candidates)==1:
                    g=candidates[0];comp=str(g.get('comparison') or '')
                    arms=[str(p['population_id']) for p in gold.get('population',[]) if re.search(r'(?<![A-Za-z0-9_])'+re.escape(str(p['population_id']))+r'(?![A-Za-z0-9_])',comp)]
                    if len(set(arms))>=2 and row.get('population_id') in arms:
                        row['population_id']=g['population_id']
        groups_p={};groups_g={}
        def signature(row):
            import re
            native=tuple(sorted(set(re.findall(r'[A-Za-z0-9_.-]+\.(?:raw|d|fq(?:\.gz)?)|cDNA-\d+-\d+-\d+', str(row.get('method','')))))) if table=='assay_run' else ()
            return tuple((f,norm(row.get(f))) for f in IDENTITY[table]) + (('source_native_acquisition', native),)
        for i,row in enumerate(rows):groups_p.setdefault(signature(row),[]).append(i)
        for i,row in enumerate(gold.get(table,[])):groups_g.setdefault(signature(row),[]).append(i)
        mapping={}
        for sig,ps in groups_p.items():
            gs=groups_g.get(sig,[])
            if len(ps)>1 or len(gs)>1:
                # Identical complete scientific rows are interchangeable. Heterogeneous ties stay unresolved.
                scientific=lambda r:tuple((k,norm(v)) for k,v in sorted(r.items()) if k!=spec.get('identifier'))
                if len({scientific(rows[i]) for i in ps}|{scientific(gold[table][j]) for j in gs})>1:
                    ambiguous.append({'table':table,'prediction_rows':ps,'reference_rows':gs})
                    continue
            mapping.update(zip(ps,gs))
        maps[table]=mapping
        key=spec.get('identifier')
        if key:
            for i,j in mapping.items():idmaps[(table,str(pred[table][i][key]))]=gold[table][j][key]
        pairs[table]=mapping
    tp=0;pg=0;gg=0;rtp=0;pr=0;gr=0
    for table,spec in dic.items():
        keys=[f['key'] for f in spec['fields'] if f['key']!=spec.get('identifier') and not f['key'].startswith('evidence')]
        p_rows=projected[table];g_rows=gold.get(table,[])
        pg+=sum(r.get(k) is not None for r in p_rows for k in keys)
        gg+=sum(r.get(k) is not None for r in g_rows for k in keys)
        pr+=len(p_rows);gr+=len(g_rows)
        for i,j in pairs[table].items():
            a,b=p_rows[i],g_rows[j]
            tp+=sum(a.get(k) is not None and b.get(k) is not None and norm(a[k])==norm(b[k]) for k in keys)
            rtp+=all(norm(a.get(k))==norm(b.get(k)) for k in keys)
    return {'rule_field_f1':2*tp/(pg+gg) if pg+gg else 1,
            'rule_record_f1':2*rtp/(pr+gr) if pr+gr else 1,
            'rule_field_tp':tp,'rule_field_predicted':pg,'rule_field_gold':gg,
            'rule_record_tp':rtp,'rule_record_predicted':pr,'rule_record_gold':gr,
            'ambiguous_identity_groups':len(ambiguous),'ambiguous':ambiguous}
