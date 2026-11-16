"""Convert independently recorded human assessments to the field/record contract."""
from collections import defaultdict
from biotracebench_scoring.task_grading_contract import mark_all


def cellkey(g,p,f):return (g or '-')+'|'+(p or '-')+'|'+f

def convert(inv,s):
    if not s.get('complete'):raise ValueError('Human review validation: ')
    rows={r['id']:r for r in inv['rows']};byrow=defaultdict(dict)
    for c in inv['cells']:byrow[c['row']][c['field']]=c
    pairs=[];used=set();matches=s.get('matches',{})
    for r in inv['rows']:
        if r['side']!='reference':continue
        choice=matches.get(r['id'])
        if not choice:raise ValueError('Human review validation: ：'+r['id'])
        p=None if choice.startswith('_') else choice
        if choice.startswith('_') and choice not in ('_missing','_uncertain'):raise ValueError('Human review validation: ')
        if p:
            if p not in rows or rows[p]['side']!='prediction' or rows[p]['table']!=r['table'] or p in used:raise ValueError('Human review validation: ')
            used.add(p)
        reason=s.get('row_notes',{}).get(r['id'],'').strip()
        if choice=='_uncertain' and not reason:raise ValueError('Human review validation: ')
        pairs.append({'prediction_row':p,'reference_row':r['id'],'verdict':'missing' if choice=='_missing' else 'uncertain' if choice=='_uncertain' else 'matched','reason':reason or 'Human review validation: '})
    for r in inv['rows']:
        if r['side']=='prediction' and r['id'] not in used:
            if not s.get('extras',{}).get(r['id'],{}).get('checked'):raise ValueError('Human review validation: ：'+r['id'])
            pairs.append({'prediction_row':r['id'],'reference_row':None,'verdict':'extra','reason':'Human review validation: '})
    marks=[]
    for pair in pairs:
        p,g=pair['prediction_row'],pair['reference_row'];pc,gc=byrow[p],byrow[g]
        for f in sorted(set(pc)|set(gc)):
            left,right=pc.get(f),gc.get(f);key=cellkey(g,p,f)
            fixed=next((c['role'] for c in (right,left) if c and c['role']!='unclassified'),None)
            cat=fixed or s.get('categories',{}).get(key)
            if not cat:raise ValueError('Human review validation: ：'+key)
            d=s.get('cells',{}).get(key,{})
            reason=d.get('reason','').strip()
            pp=bool(cat=='scientific' and left and left['nonempty']);pg=bool(cat=='scientific' and right and right['nonempty'])
            if cat=='uncertain':v='uncertain'
            elif cat!='scientific':v='not_scored'
            elif pair['verdict']=='uncertain' and (pp or pg):v='uncertain'
            elif not pp and not pg:v='not_scored'
            elif not pp:v='missing'
            elif not pg:v='extra'
            else:
                v=d.get('verdict')
                if v not in ('correct','incorrect','uncertain'):raise ValueError('Human review validation: ：'+key)
                if v!='correct' and not reason:raise ValueError('Human review validation: ：'+key)
            if cat=='uncertain' and not reason:raise ValueError('Human review validation: ：'+key)
            marks.append({'prediction_cell':left['id'] if left else None,'reference_cell':right['id'] if right else None,'category':cat,'verdict':v,'reason':reason or ('Human review validation: ' if v=='correct' else 'Human review validation: ')})
    reply={'records':pairs,'cells':marks,'reference_issues':[]}
    result=mark_all(inv,reply)
    return reply,result
