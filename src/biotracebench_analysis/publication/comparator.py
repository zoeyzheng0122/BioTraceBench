"""Explicit Doc2DB-inspired adaptation, not the authors' original metric runner.

The paper's Appendix C supplies thresholded global greedy row assignment.
Entity and relation coverage are implemented on the shipped schema mapping.
No LLM semantic-quality score is reproduced. Local identifiers are canonicalized.
"""
import csv
import json
import sys
from functools import lru_cache
from collections import Counter
from pathlib import Path

from .attribution import read, write, csv_write, norm, database_edges


@lru_cache(maxsize=100000)
def edit_similarity(left, right):
    left = ' '.join(str(left).lower().split())
    right = ' '.join(str(right).lower().split())
    if left == right:
        return 1.0
    # Unchanged strings dominate these single-change variants. Exact DP is used otherwise.
    if len(left) > len(right):
        left, right = right, left
    if not left:
        return 0.0
    masks={}
    for i,a in enumerate(left):masks[a]=masks.get(a,0)|(1<<i)
    positive,negative,distance=~0,0,len(left)
    high=1<<(len(left)-1)
    for char in right:
        eq=masks.get(char,0)
        vertical=eq|negative
        horizontal=(((eq&positive)+positive)^positive)|eq
        plus=negative|~(horizontal|positive)
        minus=positive&horizontal
        distance+=int(bool(plus&high))-int(bool(minus&high))
        plus=(plus<<1)|1
        minus=minus<<1
        positive=minus|~(vertical|plus)
        negative=plus&vertical
    return 1-distance/max(len(left),len(right),1)


def matching(pred, gold, fields):
    candidates=[]
    for i,p in enumerate(pred):
        for j,g in enumerate(gold):
            scores=[]
            for field in fields:
                a,b=p.get(field),g.get(field)
                if a is None or b is None:
                    scores.append(0.0)
                elif norm(a)==norm(b):
                    scores.append(1.0)
                elif isinstance(a,str) and isinstance(b,str):
                    scores.append(edit_similarity(a,b))
                else:
                    scores.append(0.0)
            score=sum(scores)/len(scores) if scores else 0
            if score>=.3:
                candidates.append((-score,j,i))
    used_p,used_g,maps=set(),set(),{}
    for _,j,i in sorted(candidates):
        if i not in used_p and j not in used_g:
            used_p.add(i);used_g.add(j);maps[i]=j
    return maps


def evaluate(pred,gold,dic):
    maps={}; idmap={};entities=0;matched_entities=0
    order=sorted(dic,key=lambda t:bool(dic[t].get('references')))
    for table in order:
        spec=dic[table]
        p=json.loads(json.dumps(pred.get(table,[])))
        for row in p:
            for field,target in spec.get('references',{}).items():
                v=row.get(field)
                if isinstance(v,list):
                    row[field]=[idmap.get((target,str(x)),f'unmatched:{x}') for x in v]
                elif v is not None:
                    row[field]=idmap.get((target,str(v)),f'unmatched:{v}')
        fields=[f['key'] for f in spec['fields'] if f['key']!=spec.get('identifier')]
        maps[table]=matching(p,gold.get(table,[]),fields)
        key=spec.get('identifier')
        if key:
            for i,j in maps[table].items():
                idmap[(table,str(pred[table][i][key]))]=gold[table][j][key]
        if not spec.get('references'):
            entities+=len(gold.get(table,[]));matched_entities+=len(maps[table])
    gi={t:{str(r[spec['identifier']]):i for i,r in enumerate(gold.get(t,[]))}
        for t,spec in dic.items() if spec.get('identifier')}
    pe=database_edges(pred,dic);ge=database_edges(gold,dic)
    gc=Counter(ge);pc=Counter()
    valid=0
    for t,i,f,target,ref in pe:
        mapped_id=idmap.get((target,ref))
        if ref in {str(r[dic[target]['identifier']]) for r in pred.get(target,[])}:
            valid+=1
        pc[(t,maps[t].get(i,-1),f,target,str(mapped_id))]+=1
    tp=sum((pc&gc).values())
    return {'doc2db_entity_coverage':matched_entities/entities if entities else None,
            'doc2db_relation_coverage':tp/len(ge) if ge else None,
            'doc2db_reference_integrity':valid/len(pe) if pe else None,
            'doc2db_relation_tp':tp,'doc2db_relation_gold':len(ge),
            'adaptation':'thresholded global row assignment plus mapped directed FK tuples'}


if __name__=='__main__':
    root=Path(sys.argv[1]);out=Path(sys.argv[2])
    art=Path(__file__).resolve().parents[1]/'v15-artifacts';registry=read(out/'variant_registry.json')
    rows=[]
    for v in registry:
        if v['validation_errors']:continue
        dic=read(art/'dictionaries'/f"{v['domain']}.json")
        gold=read(art/'references'/f"{v['case']}.json")
        result=evaluate(read(out/v['variant']),gold,dic)
        rows.append({k:v[k] for k in ['case','domain','family','blind_id']}|result)
    csv_write(out/'relational_comparator.csv',rows)
    summary=[]
    for family in dict.fromkeys(r['family'] for r in rows):
        selected=[r for r in rows if r['family']==family]
        s={'family':family,'n':len(selected)}
        for metric in ['doc2db_entity_coverage','doc2db_relation_coverage','doc2db_reference_integrity']:
            values=[r[metric] for r in selected if r[metric] is not None]
            s[metric]=sum(values)/len(values) if values else None
            s[metric+'_n']=len(values)
        summary.append(s)
    csv_write(out/'relational_comparator_summary.csv',summary)
    write(out/'comparator_protocol.json',{'implementation':'Doc2DB-inspired explicit adaptation',
        'paper':'https://arxiv.org/html/2608.08459v1','code':'https://github.com/SetonLiang/Doc2DB-Bench/tree/main/evaluation',
        'paper_code_difference':'public evaluator does not expose the three Appendix D.1 metrics under those names; adapter formulas explicitly defined here',
        'matching_threshold':.3,'entity_tables':['sample','population','measure'],
        'relation_projection':'each declared foreign-key element becomes a directed typed tuple after row/ID mapping',
        'reference_integrity':'fraction of submitted FK elements pointing to an existing submitted row',
        'semantic_quality_llm_score':'not run'})
