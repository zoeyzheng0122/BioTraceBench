"""Original independent reviewer agreement from an external review bundle."""
from pathlib import Path
from collections import Counter,defaultdict
import csv,json
from biotracebench_scoring.task_grading_contract import mark_all
from .human_converter import convert
from .io import read,digest
def agreement(artifact,D):
 D.mkdir(parents=True);W=artifact.repro/'04_Human_Review/01_Analysis/inputs';paths={'A':W/'reviewer_A.json','B':W/'reviewer_B.json'};bundles=read(W/'bundles.json');returns={k:read(p)for k,p in paths.items()}
 rows=[];coverage=[];differences=[]
 for aid,b in bundles.items():
  old=mark_all(b['inventory'],b['marking'])
  for lev in ['field','record']:
   for met in ['tp','predicted','gold','precision','recall','f1']:
    assert abs(old[lev][met]-b['expected'][lev+'_'+met])<1e-12,(aid,lev,met)
  parsed={k:convert(b['inventory'],v['answers'][aid]) for k,v in returns.items()}
  invrows={r['id']:r for r in b['inventory']['rows']}
  states={}
  for k,(reply,result) in parsed.items():
   fields={}
   for c in result['cells']:
    ref=c.get('reference')
    if c['category']=='scientific' and ref and ref['nonempty']:
     fields[(ref['table'],ref['row_index'],ref['field'])]=None if c['verdict']=='uncertain' else c['verdict']=='correct'
   records={}
   for pair in reply['records']:
    p,g=pair['prediction_row'],pair['reference_row']
    if g is None:continue
    cc=[c for c in result['cells'] if (c.get('reference') and c['reference']['row']==g) or (p is not None and c.get('prediction') and c['prediction']['row']==p)]
    if pair['verdict']=='missing':s=False
    elif pair['verdict']=='uncertain':s=None
    elif any(c['category']=='scientific' and c['verdict'] in ['incorrect','missing','extra'] for c in cc):s=False
    elif any(c['verdict']=='uncertain' or c['category']=='uncertain' for c in cc):s=None
    else:s=any(c['category']=='scientific' and any(c.get(side) and c[side]['nonempty'] for side in ['reference','prediction']) for c in cc)
    records[(invrows[g]['table'],invrows[g]['row_index'])]=s
   states[k]={'field':fields,'record':records}
  for lev in ['field','record']:
   aa,bb=states['A'][lev],states['B'][lev]
   assert set(aa)==set(bb),(aid,lev,'Different item identities')
   for key in aa:
    x,y=aa[key],bb[key]
    row={'answer_id':aid,**b['identity'],'level':lev,'item':str(key),'A':x,'B':y,'both_determinate':x is not None and y is not None,'equal':x==y}
    row={k:v for k,v in row.items() if k not in ['judgment_path','judgment_sha256']}
    rows.append(row)
    if x!=y:differences.append(row)
 summary={}
 for scope in ['i0']:
  summary[scope]={}
  for lev in ['field','record']:
   rr=[r for r in rows if r['level']==lev and (scope=='all_stages' or r['stage']=='i0')]
   det=[r for r in rr if r['both_determinate']];agree=sum(r['equal'] for r in det)
   summary[scope][lev]={'all_reference_items':len(rr),'both_determinate':len(det),'agreement_n':agree,'disagreement_n':len(det)-agree,'agreement':agree/len(det) if det else None,'uncertain_in_either':len(rr)-len(det),'three_state_equal_n':sum(r['equal'] for r in rr),'three_state_agreement':sum(r['equal'] for r in rr)/len(rr) if rr else None}
 summary['output_counts']={'i0':sum(b['identity']['stage']=='i0' for b in bundles.values()),'studies':len({b['identity']['case'] for b in bundles.values()})}
 summary['provenance']={'reviewer_mapping':'User explicitly identified the two input sources as reviewer A and reviewer B, and confirmed independent review before consolidation to the same format. Original reviewer_slot/name metadata are preserved.','reference_scope':'Frozen human-audit reference, not an adjudicated v15 human standard.','uncertainty_policy':'Binary agreement includes reference items with determinate judgments from both reviewers; coverage and uncertain counts are reported. A record is incorrect if any required item is determinately incorrect; otherwise uncertainty propagates. Missing records are incorrect.','inputs':{k:{'path':p.name,'sha256':digest(p)} for k,p in paths.items()},'converter_sha256':digest(Path(__file__).with_name('human_converter.py')),'bundles_sha256':digest(W/'bundles.json'),'baseline_replay':'All 48 frozen automatic scores exactly reproduced before human comparison.'}
 (D/'human_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 (D/'disagreements.json').write_text(json.dumps(differences,ensure_ascii=False,indent=2)+'\n')
 with (D/'item_agreement.csv').open('w',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
 return summary['i0']
