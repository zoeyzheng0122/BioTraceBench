"""Content attribution and relationship recovery under frozen eligibility."""
import csv,gzip,json,re
from pathlib import Path
from collections import Counter,defaultdict
from decimal import Decimal,InvalidOperation
import numpy as np
SEED=20261110
ANCHORS = {
    'sample': ('sample_accession', 'sample_name', 'biological_source', 'biological_model', 'sample_material'),
    'population': ('population_name', 'population_definition', 'intervention', 'population_time_frame'),
    'measure': ('measure_name', 'measure_definition'),
    'condition': ('condition_target', 'experimental_factor', 'time'),
    'assay_run': ('experiment_run_accession', 'assay_type', 'platform', 'method'),
    'result': ('assessment_time', 'statistic_type', 'statistical_method', 'comparison'),
}

def read(path):
    with (gzip.open(path, 'rt') if str(path).endswith('.gz') else open(path)) as f:
        return json.load(f)

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def csv_write(path, rows):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        fields = sorted({k for row in rows for k in row})
        writer = csv.DictWriter(f, fields)
        writer.writeheader()
        writer.writerows(rows)

def norm(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return ('number', str(Decimal(str(value)).normalize()))
    if isinstance(value, str):
        s = re.sub(r'\s+', ' ', value).strip()
        try:
            return ('number', str(Decimal(s).normalize()))
        except InvalidOperation:
            return ('text', s)
    if isinstance(value, list):
        return ('list', tuple(sorted((norm(x) for x in value), key=repr)))
    return ('json', json.dumps(value, sort_keys=True))

def content_bag(database, dictionary):
    result = Counter()
    for table, spec in dictionary.items():
        refs = spec.get('references', {})
        for row in database.get(table, []):
            for field, value in row.items():
                if field == spec.get('identifier') or field in refs or field.startswith('evidence'):
                    continue
                if value is not None:
                    if field=='comparison' and isinstance(value,str):
                        lookup={str(r['population_id']):str(r.get('population_name')) for r in database.get('population',[])}
                        if lookup:
                            pattern=r'(?<![A-Za-z0-9_])('+'|'.join(re.escape(k) for k in sorted(lookup,key=len,reverse=True))+r')(?![A-Za-z0-9_])'
                            value=re.sub(pattern,lambda m:lookup[m.group(0)],value)
                    result[(table, field, norm(value))] += 1
    return result

def database_edges(database, dictionary):
    edges = []
    for table, spec in dictionary.items():
        for i, row in enumerate(database.get(table, [])):
            for field, target in spec.get('references', {}).items():
                value = row.get(field)
                for ref in value if isinstance(value, list) else [value]:
                    if ref is not None:
                        edges.append((table, i, field, target, str(ref)))
    return edges

def actual(root,out,*,baseline,published):
    art = baseline/'v15-artifacts'
    dictionaries = {d:read(art/'dictionaries'/f'{d}.json') for d in ['basic','clinical']}
    positions = list(csv.DictReader((baseline/'four-class/diagnostics/positions.csv').open(encoding='utf-8-sig')))
    bindings={(r['model'],r['case']):r['status'] for r in csv.DictReader((root/'06_Error_Analysis/output_view_bindings.csv').open(encoding='utf-8-sig'))}
    counts, facts, links, recovered_rows, unresolved = [], [], [], [], []
    for pos in positions:
        if pos['zero_cause']:
            continue
        model,case,domain = pos['model'],pos['case'],pos['domain']
        dic = dictionaries[domain]
        data = read(published/'projection/judgments'/model/'i0'/f'{case}.json.gz')
        inv, marking = data['inventory'],data['marking']
        cells = {c['id']:c for c in inv['cells']}
        rows = {r['id']:r for r in inv['rows']}
        db = defaultdict(dict)
        verdicts = defaultdict(dict)
        for c in inv['cells']:
            if c['present']:
                db[c['row']][c['field']] = json.loads(c['value_json'])
        pairs = {r['prediction_row']:r['reference_row'] for r in marking['records']
                 if r.get('prediction_row') and r.get('reference_row') and r['verdict']=='matched'}
        mapped_gold = set(pairs.values())

        dispositions=read(published/'source-dispositions.json')
        masks={(x['table'],x['row_index']):set(x['field_exclusions']) for x in dispositions if x['case']==case and x['main_record_scoring']=='excluded'}
        reference_for_pred={r['prediction_row']:r['reference_row'] for r in marking['records'] if r.get('prediction_row') and r.get('reference_row')}
        def eligible_field(rid,field):
            meta=rows[rid]
            ref=rows.get(reference_for_pred.get(rid)) if meta['side']=='prediction' else meta
            if ref:
                excluded=masks.get((ref['table'],ref['row_index']),set())
                return '*' not in excluded and field not in excluded
            # No unmatched prediction is credited or penalized for a source-
            # unassessable association merely because its local IDs differ.
            return not any(t==meta['table'] and ('*' in fs or field in fs) for (t,i),fs in masks.items())
        def eligible_attribution(rid):
            table=rows[rid]['table']
            return all(eligible_field(rid,f) for f in dic.get(table,{}).get('references',{}))

        for mark in marking['cells']:
            pc,rc = cells.get(mark.get('prediction_cell')),cells.get(mark.get('reference_cell'))
            if pc:
                verdicts[pc['row']][pc['field']] = mark['verdict']
        # Certify endpoint identity with correct non-link identity fields, unique among reference objects.
        certified = {}
        for pr,gr in pairs.items():
            table = rows[pr]['table']
            fields = [f for f in ANCHORS.get(table,()) if eligible_field(gr,f) and verdicts[pr].get(f)=='correct'
                      and db[gr].get(f) is not None and db[pr].get(f) is not None]
            if fields:
                candidates = [r for r in rows if rows[r]['side']=='reference' and rows[r]['table']==table
                    and all(norm(db[r].get(f))==norm(db[gr][f]) for f in fields)]
                if candidates == [gr]:
                    certified[pr] = gr
        ids = {'prediction':{},'reference':{}}
        for rid,meta in rows.items():
            key = dic.get(meta['table'],{}).get('identifier')
            if key and db[rid].get(key) is not None:
                ids[meta['side']][(meta['table'],str(db[rid][key]))] = rid
        c = Counter()
        c['evaluable']=1
        c['original_database']=int(bindings[model,case]=='original_fields_match')
        c['predicted_objects']=sum(r['side']=='prediction' for r in rows.values())
        c['reference_objects']=sum(r['side']=='reference' for r in rows.values())
        c['independent_identity_objects']=len(certified)
        c['aligned_objects']=len(pairs)
        ref_edges, pred_edges = [], []
        def edge_key(a,t,b):
            if t[0]=='population_relation' and any(v in str(t[1]).lower() for v in ['disjoint','overlap','same participants']):
                return (min(a,b),t,max(a,b))
            return a,t,b
        for rid,meta in rows.items():
            table = meta['table']
            if table=='population_relation':
                if not all(eligible_field(rid,f) for f in ['population_a_id','population_b_id','relationship']):continue
                a=ids[meta['side']].get(('population',str(db[rid].get('population_a_id'))))
                b=ids[meta['side']].get(('population',str(db[rid].get('population_b_id'))))
                if a and b:
                    relation_value=db[rid].get('relationship')
                    if meta['side']=='prediction' and verdicts[rid].get('relationship')=='correct' and rid in pairs:
                        relation_value=db[pairs[rid]].get('relationship')
                    e=(a,('population_relation',norm(relation_value)),b,rid)
                    (pred_edges if meta['side']=='prediction' else ref_edges).append(e)
                else:
                    c['unresolved_edges']+=1
                continue
            for field,target in dic.get(table,{}).get('references',{}).items():
                if not eligible_field(rid,field):continue
                val=db[rid].get(field)
                values=val if isinstance(val,list) else [val]
                for value in values:
                    if value is None:
                        continue
                    dest=ids[meta['side']].get((target,str(value)))
                    if dest:
                        e=(rid,(table,field),dest,rid)
                        (pred_edges if meta['side']=='prediction' else ref_edges).append(e)
                    else:
                        c['dangling_edges']+=1
        # Logical endpoints are represented by source-adjudicated comparison
        # roles. A pooled/subject pointer is canonical only in this exact row.
        def mapped_edge(a,t,b):
            ma,mb=pairs.get(a,'missing:'+a),pairs.get(b,'missing:'+b)
            if t==('result','population_id') and a in pairs and verdicts[a].get('population_id')=='correct' and verdicts[a].get('comparison')=='correct':
                gr=pairs[a]
                expected=ids['reference'].get(('population',str(db[gr].get('population_id'))))
                if expected and expected!=mb:
                    mb=expected
            return ma,t,mb
        def conditional_edge(a,t,b):
            ma,_,mb=mapped_edge(a,t,b)
            if a not in certified or mb not in cert_gold:return False
            if b in certified:return True
            # An unmatched pooled representation can express the same contrast
            # only when both actual arms have independently certified objects.
            if t!=('result','population_id') or ma not in db:return False
            comp=str(db[ma].get('comparison') or '')
            arms=[r for (table,pid),r in ids['reference'].items() if table=='population' and re.search(r'(?<![A-Za-z0-9_])'+re.escape(pid)+r'(?![A-Za-z0-9_])',comp)]
            return len(set(arms))>=2 and all(r in cert_gold for r in arms) and verdicts[a].get('population_id')=='correct' and verdicts[a].get('comparison')=='correct'
        gold_counter=Counter(edge_key(a,t,b) for a,t,b,_ in ref_edges)
        all_pred=Counter(edge_key(*mapped_edge(a,t,b)) for a,t,b,_ in pred_edges)
        matched=gold_counter & all_pred
        c['relation_tp']=sum(matched.values());c['relation_pred']=len(pred_edges)+c['dangling_edges'];c['relation_gold']=len(ref_edges)
        cert_gold=set(certified.values())
        cg=Counter(edge_key(a,t,b) for a,t,b,_ in ref_edges if a in cert_gold and b in cert_gold)
        cp=Counter(edge_key(*mapped_edge(a,t,b)) for a,t,b,_ in pred_edges if conditional_edge(a,t,b))
        c['conditional_tp']=sum((cg&cp).values());c['conditional_pred']=sum(cp.values());c['conditional_gold']=sum(cg.values())
        c['comparative_edges_canonicalized']=sum(mapped_edge(a,t,b)[2]!=pairs.get(b,'missing:'+b) for a,t,b,_ in pred_edges)
        missing_gold=gold_counter-all_pred
        used_missing=Counter()
        remaining_correct=matched.copy()
        bad_rows=set()
        for a,t,b,owner in pred_edges:
            ma,_,mb=mapped_edge(a,t,b)
            key=edge_key(ma,t,mb)
            if remaining_correct[key]>0:
                status='correct'
                remaining_correct[key]-=1
            elif str(ma).startswith('missing:') or str(mb).startswith('missing:'):
                status='object_missing_or_unaligned'
            else:
                alternatives=[k for k,v in missing_gold.items() if v>used_missing[k] and k[0]==ma and k[1]==t]
                status='wrong_link' if alternatives else 'additional_link'
                if alternatives:
                    used_missing[alternatives[0]]+=1
            if status!='correct':
                bad_rows.add(owner)
            links.append({'model':model,'case':case,'domain':domain,'source_row':a,'target_row':b,
                'relation':repr(t),'reference_source':ma,'reference_target':mb,'status':status,
                'independent_endpoints':conditional_edge(a,t,b),'owner':owner})
            c['pred_'+status]+=1
        for (a,t,b),n in missing_gold.items():
            status='missing_object' if a not in mapped_gold or b not in mapped_gold else 'omitted_link'
            remaining=n-used_missing[(a,t,b)]
            c['gold_'+status]+=remaining
            if remaining:
                links.append({'model':model,'case':case,'domain':domain,'reference_source':a,'reference_target':b,
                    'relation':repr(t),'status':status,'count':remaining,'independent_endpoints':a in cert_gold and b in cert_gold})
        # Whole scientific facts. Frozen correct decisions supply semantic equivalence.
        # New cross-object matches require identical canonical literals and compatible units/type.
        available=defaultdict(list)
        for rid,meta in rows.items():
            if meta['side']!='reference':continue
            for field,value in db[rid].items():
                if not eligible_field(rid,field) or not eligible_attribution(rid):continue
                if field==dic.get(meta['table'],{}).get('identifier') or field in dic.get(meta['table'],{}).get('references',{}) or value is None:continue
                available[(meta['table'],field,norm(value))].append(rid)
        used=set()
        ordered=sorted(marking['cells'],key=lambda m:m.get('verdict')!='correct')
        for mark in ordered:
            pc,rc=cells.get(mark.get('prediction_cell')),cells.get(mark.get('reference_cell'))
            if not pc or pc['role']!='scientific' or not pc['nonempty']:continue
            table,field,pr=pc['table'],pc['field'],pc['row']
            if not eligible_field(pr,field) or not eligible_attribution(pr):continue
            if field in dic.get(table,{}).get('references',{}):continue
            c['scientific_content_fields']+=1
            gr=None;basis=''
            if mark['verdict']=='correct' and rc:
                gr=rc['row'];basis='frozen_semantic_equivalence'
            else:
                candidates=[]
                for candidate in available[(table,field,norm(json.loads(pc['value_json'])))]:
                    if (candidate,field) in used:continue
                    guards=('result_unit','statistic_type') if table=='result' else ('factor_unit','experimental_factor') if table=='condition' else ()
                    if all(verdicts[pr].get(g)=='correct' or norm(db[pr].get(g))==norm(db[candidate].get(g)) for g in guards):
                        candidates.append(candidate)
                if len(candidates)==1:
                    gr=candidates[0];basis='unique_literal_and_role_match'
                else:
                    reason='ambiguous_content' if candidates else 'not_uniquely_recoverable_under_literal_comparator'
                    unresolved.append({'model':model,'case':case,'row':pr,'table':table,'field':field,'status':reason})
                    c[reason]+=1
            if gr is None or (gr,field) in used:continue
            used.add((gr,field));c['content_recovered']+=1
            wrong = pairs.get(pr)!=gr
            relation_fields=dic.get(table,{}).get('references',{})
            for fk,target in relation_fields.items():
                pval,gval=db[pr].get(fk),db[gr].get(fk)
                pvals=pval if isinstance(pval,list) else [pval]
                gvals=gval if isinstance(gval,list) else [gval]
                mapped=[pairs.get(ids['prediction'].get((target,str(v)))) for v in pvals if v is not None]
                expected=[ids['reference'].get((target,str(v))) for v in gvals if v is not None]
                if Counter(mapped)!=Counter(expected) and verdicts[pr].get(fk)!='correct':wrong=True
            c['misattributed']+=int(wrong)
            if (table,field) in [('result','result_value'),('condition','factor_value'),('population','population_size')]:
                c['value_content_recovered']+=1
                c['value_misattributed']+=int(wrong)
            facts.append({'model':model,'case':case,'domain':domain,'table':table,'field':field,
                'prediction_cell':pc['id'],'prediction_row':pr,'reference_row':gr,'basis':basis,
                'misattributed':wrong,'frozen_verdict':mark['verdict']})
        for pr,gr in pairs.items():
            if (rows[gr]['table'],rows[gr]['row_index']) in masks:continue
            marks=[m for m in marking['cells'] if cells.get(m.get('prediction_cell'),{}).get('row')==pr and m.get('category')!='identifier']
            failures=[m for m in marks if m['verdict'] not in ['correct','not_scored']]
            if failures:
                c['incomplete_aligned_records']+=1
                relation_fields=dic.get(rows[pr]['table'],{}).get('references',{})
                only_refs=all(cells.get(m.get('prediction_cell'),cells.get(m.get('reference_cell'),{})).get('field') in relation_fields for m in failures)
                # Include reference-only omissions in this row, and reject surplus/unmatched fields.
                missing=[m for m in marking['cells'] if not m.get('prediction_cell') and cells.get(m.get('reference_cell'),{}).get('row')==gr and m['verdict']!='not_scored']
                replaceable=True
                for fk,target in relation_fields.items():
                    value=db[gr].get(fk)
                    values=value if isinstance(value,list) else [value]
                    if any(ids['reference'].get((target,str(v))) not in mapped_gold for v in values if v is not None):
                        replaceable=False
                if only_refs and not missing and pr in bad_rows and replaceable:
                    c['link_only_recoverable_records']+=1
                    recovered_rows.append({'model':model,'case':case,'domain':domain,'prediction_row':pr,'reference_row':gr,
                        'assumption':'frozen scientific row correspondence retained; only incorrect references replaced',
                        'failed_fields':';'.join(cells[m['prediction_cell']]['field'] for m in failures)})
        counts.append({'model':model,'case':case,'domain':domain,**dict(c)})
    keys=set(k for r in counts for k in r)-{'model','case','domain'}
    for r in counts:
        for key in keys:r.setdefault(key,0)
    csv_write(out/'study_counts.csv',counts)
    csv_write(out/'facts.csv',facts);csv_write(out/'relations.csv',links)
    csv_write(out/'link_only_records.csv',recovered_rows);csv_write(out/'literal-comparator-exclusions.csv',unresolved)
    return counts

def summarize(counts,out):
    measures={'misattribution_rate':('misattributed','content_recovered'),
        'value_misattribution_rate':('value_misattributed','value_content_recovered'),
        'relation_precision':('relation_tp','relation_pred'),'relation_recall':('relation_tp','relation_gold'),
        'conditional_precision':('conditional_tp','conditional_pred'),'conditional_recall':('conditional_tp','conditional_gold'),
        'link_only_record_rate':('link_only_recoverable_records','incomplete_aligned_records')}
    rng=np.random.default_rng(SEED)
    studies={d:sorted({r['case'] for r in counts if r['domain']==d}) for d in ['basic','clinical']}
    indices={d:rng.integers(0,50,(10000,50)) for d in studies}
    summary=[]
    for model in sorted({r['model'] for r in counts}):
        bycase={r['case']:r for r in counts if r['model']==model}
        for measure,(num,den) in measures.items():
            estimates={};boots={};totals={}
            for domain,cases in studies.items():
                # Failed generation positions have no observable scientific facts; absence is not an error-free answer.
                a=np.array([[bycase.get(case,{}).get(num,0),bycase.get(case,{}).get(den,0)] for case in cases],dtype=float)
                total=a.sum(0);totals[domain]=total
                estimates[domain]=total[0]/total[1] if total[1] else np.nan
                b=a[indices[domain]].sum(1)
                boots[domain]=np.divide(b[:,0],b[:,1],out=np.full(10000,np.nan),where=b[:,1]>0)
            for domain in ['basic','clinical','overall']:
                mean=(estimates['basic']+estimates['clinical'])/2 if domain=='overall' else estimates[domain]
                b=(boots['basic']+boots['clinical'])/2 if domain=='overall' else boots[domain]
                n,d=totals['basic']+totals['clinical'] if domain=='overall' else totals[domain]
                valid=b[np.isfinite(b)];lo,hi=np.quantile(valid,[.025,.975],method='linear') if len(valid) else [np.nan,np.nan]
                summary.append({'model':model,'domain':domain,'metric':measure,'numerator':int(n),'denominator':int(d),
                    'estimate':float(mean) if np.isfinite(mean) else None,'low':float(lo) if np.isfinite(lo) else None,
                    'high':float(hi) if np.isfinite(hi) else None,'valid_resamples':len(valid),
                    'aggregation':'equal-domain ratios' if domain=='overall' else 'ratio of counts'})
    csv_write(out/'model_summary.csv',summary)
    return summary
