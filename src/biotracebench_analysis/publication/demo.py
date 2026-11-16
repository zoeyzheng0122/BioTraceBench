"""Synthetic whole-field and complete-record demonstration; no model calls."""
from copy import deepcopy
from pathlib import Path
import argparse,json
from biotracebench_scoring.task_grading_contract import inventory,mark_all
from .scoring import projected
from .io import write

def fixture():
 dictionary={'population':{'identifier':'population_id','references':{},'fields':[{'key':x}for x in['population_id','population_name','population_size','intervention']]}}
 policy={'reference_contract':'biotracebench-fixed-reference-1','field_roles':{'population.'+f:('identifier'if f=='population_id'else'scientific')for f in['population_id','population_name','population_size','intervention']}}
 reference={'population':[{'population_id':'R1','population_name':'Synthetic arm A','population_size':40,'intervention':'Treatment X'},{'population_id':'R2','population_name':'Synthetic arm B','population_size':60,'intervention':'Control'}]}
 submitted=deepcopy(reference);submitted['population'][0]['population_id']='P1';submitted['population'][1]['population_id']='P2';del submitted['population'][1]['population_size'];submitted['population'][1]['intervention']='Treatment X'
 return dictionary,policy,reference,submitted

def supplied_judgment(inv):
 # This is a synthetic fixture's explicit known pairing, not an automatic scientific judge.
 records=[];marks=[];cells={(c['row'],c['field']):c for c in inv['cells']}
 predictions={r['row_index']:r for r in inv['rows']if r['side']=='prediction'}
 for ref in [r for r in inv['rows']if r['side']=='reference']:
  pred=predictions[ref['row_index']];records.append({'prediction_row':pred['id'],'reference_row':ref['id'],'verdict':'matched','reason':'Explicit synthetic fixture identity.'})
  fields=sorted({c['field']for c in inv['cells']if c['row']in[pred['id'],ref['id']]})
  for field in fields:
   p,g=cells.get((pred['id'],field)),cells.get((ref['id'],field));role=(g or p)['role'];pn=bool(p and p['nonempty']);gn=bool(g and g['nonempty'])
   verdict='not_scored'if role!='scientific'or not pn and not gn else'missing'if not pn else'extra'if not gn else'correct'if p['value_json']==g['value_json']else'incorrect'
   marks.append({'prediction_cell':p['id']if p else None,'reference_cell':g['id']if g else None,'category':role,'verdict':verdict,'reason':'Explicit synthetic whole-field assessment.'})
 return {'records':records,'cells':marks,'reference_issues':[]}
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args(argv)
 if a.out.exists():raise FileExistsError('Output directory must not exist')
 dic,policy,gold,pred=fixture();inv=inventory(pred,gold,dic,policy);reply=supplied_judgment(inv);mark_all(inv,reply);metrics=projected(inv,reply,'SYNTHETIC')
 write(a.out/'synthetic_input.json',{'dictionary':dic,'policy':policy,'reference':gold,'submission':pred});write(a.out/'synthetic_judgment.json',reply);write(a.out/'synthetic_score.json',{'synthetic_only':True,'metrics':metrics});print(json.dumps({'synthetic_only':True,'metrics':metrics},indent=2))
if __name__=='__main__':main()
