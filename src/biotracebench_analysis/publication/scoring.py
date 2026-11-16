"""Published whole-field and complete-record counter."""
from collections import defaultdict

def projected(inv,mark,case,dispositions=()):
 """Exact published v16 eligibility projection and whole-field/record count."""
 cs={r['id']:r for r in inv['cells']};rs={r['id']:r for r in inv['rows']}
 masks={(r['table'],r['row_index']):set(r['field_exclusions'])for r in dispositions if r['case']==case and r['main_record_scoring']=='excluded'}
 pair={r['prediction_row']:r['reference_row']for r in mark['records']if r.get('prediction_row')and r.get('reference_row')}
 def canonical(r):return rs.get(pair.get(r['id']))if r['side']=='prediction'else r
 er={r['id']for r in inv['rows']if(lambda g:g and(g['table'],g['row_index'])in masks)(canonical(r))};ec=set()
 for cell in inv['cells']:
  g=canonical(rs[cell['row']]);fs=masks.get((g['table'],g['row_index']),set())if g else set()
  if cell['field']in fs or'*'in fs:ec.add(cell['id'])
 cats={i:m['category']for m in mark['cells']for i in[m.get('prediction_cell'),m.get('reference_cell')]if i}
 gold={c['id']for c in inv['cells']if c['side']=='reference'and c['nonempty']and cats[c['id']]=='scientific'and c['id']not in ec};pred={c['id']for c in inv['cells']if c['side']=='prediction'and c['nonempty']and cats[c['id']]=='scientific'and c['id']not in ec}
 tp=sum(m['verdict']=='correct'and m.get('prediction_cell')in pred and m.get('reference_cell')in gold for m in mark['cells']);gr=({r['id']for r in inv['rows']if r['side']=='reference'and r['declared_table']}|{cs[i]['row']for i in gold})-er;pr=({r['id']for r in inv['rows']if r['side']=='prediction'and r['declared_table']}|{cs[i]['row']for i in pred})-er
 by=defaultdict(list)
 for m in mark['cells']:
  for i in[m.get('prediction_cell'),m.get('reference_cell')]:
   if i:by[cs[i]['row']].append(m)
 complete=0
 for m in mark['records']:
  if m.get('reference_row')not in gr:continue
  mm=by[m['reference_row']]+by.get(m.get('prediction_row'),[]);complete+=m['verdict']=='matched'and all(x['verdict']in['correct','not_scored']for x in mm)
 def metrics(m,p,g):
  assert m<=min(p,g)
  return {'tp':m,'predicted':p,'gold':g,'precision':(m/p if p else 0)if g else None,'recall':m/g if g else None,'f1':2*m/(p+g)if g else None}
 return {'field':metrics(tp,len(pred),len(gold)),'record':metrics(complete,len(pr),len(gr))}
