"""Reproduce publication experiments from a separately supplied materials package."""
from pathlib import Path
from collections import Counter,defaultdict
from decimal import Decimal
import argparse,json,shutil,sys,time,platform,socket
from .io import Artifact,read,write,rows,csvwrite,digest

def compare(actual,expected):
 left,right=rows(actual),rows(expected)
 if len(left)!=len(right):raise ValueError(f'Row count differs: {actual.name}')
 if left and set(left[0])!=set(right[0]):raise ValueError(f'Column set differs: {actual.name}')
 for i,(x,y)in enumerate(zip(left,right)):
  for k in x:
   if x[k]==y[k]:continue
   try:ok=abs(float(x[k])-float(y[k]))<1e-12
   except (ValueError,TypeError):ok=False
   if not ok:raise ValueError(f'Publication mismatch: {actual.name}, row {i}, column {k}')
 return len(left)
def score_counts(artifact,out):
 from biotracebench_scoring.task_grading_contract import mark_all
 from .scoring import projected
 data=rows(artifact.published/'projection/scores.csv');dispositions=read(artifact.published/'source-dispositions.json');n=zero=0
 for row in data:
  if row['zero_output']=='True':
   zero+=1
   if any(int(row[q])for q in['field_tp','field_predicted','record_tp','record_predicted']):raise ValueError('Invalid assigned-zero position')
   continue
  packet=read(artifact.published/'projection/judgments'/row['model']/'i0'/(row['case']+'.json.gz'));inv=packet['inventory'];mark_all(inv,packet['marking']);actual=projected(inv,packet['marking'],row['case'],dispositions)
  policy,_=artifact.policy(row['case'])
  for cell in inv['cells']:
   if cell['side']=='reference'and cell['role']!=policy['field_roles'].get(cell['table']+'.'+cell['field'],cell['role']):raise ValueError('Frozen field-role policy does not match the reference contract')
  for level in['field','record']:
   for key in['tp','predicted','gold','precision','recall','f1']:
    want=row[level+'_'+key];value=actual[level][key]
    if not((value is None and want=='')or(value is not None and abs(value-float(want))<1e-12)):raise ValueError('Published field/record count differs')
    row[level+'_'+key]=''if value is None else value
  n+=1
 csvwrite(out/'projection/scores.csv',data)
 return data,{'positions':len(data),'scientific_judgments_replayed':n,'assigned_zeros':zero,'field_role_policy':'passed'}
def diagnostic_incidence(artifact,out,scores):
 categories=defaultdict(set);details=rows(artifact.published/'diagnostic-dispositions.csv')
 for r in details:
  if r['category']:categories[r['model'],r['case']].add(r['category'])
 result=[]
 for domain in['overall','clinical','basic']:
  for model in['ALL']+sorted({r['model']for r in scores}):
   rr=[r for r in scores if(domain=='overall'or r['domain']==domain)and(model=='ALL'or r['model']==model)];eligible=[r for r in rr if r['zero_output']=='False']
   for category in['omission','constraint','binding','grounding']:
    hits=[r for r in eligible if category in categories[r['model'],r['case']]];result.append({'domain':domain,'model':model,'category':category,'answer_cases':len(hits),'evaluable_answers':len(eligible),'percentage':100*len(hits)/len(eligible),'distinct_tasks':len({r['case']for r in hits})})
 csvwrite(out/'diagnostic-summary.csv',result);csvwrite(out/'diagnostic-dispositions.csv',details)
 return categories

def controlled_experiment(artifact,out):
 from .controlled import evaluate
 from .comparator import evaluate as comparator
 from .attribution import content_bag
 registry=read(artifact.baseline/'efe-controlled/variant_registry.json');prior={r['blind_id']:r for r in rows(artifact.baseline/'efe-controlled/controlled_rule_replay.csv')};original={};records=[];details=[]
 revision=read(artifact.published/'current-result-contract.json')['version']
 for v in registry:
  dic=read(artifact.baseline/'v15-artifacts/dictionaries'/(v['domain']+'.json'));gold=read(artifact.published/'projection/references'/(v['case']+'.json'));override=artifact.inputs/'status/controlled-variants'/(v['blind_id']+'.json');database=read(override if override.exists()else artifact.baseline/'efe-controlled'/v['variant']);result=evaluate(database,gold,dic)
  if v['family']=='original':original[v['case']]=result
  baseline=original[v['case']];eligible=not result['ambiguous']and not baseline['ambiguous'];row={k:v[k]for k in['case','domain','family','blind_id']};row.update({k:x for k,x in result.items()if k!='ambiguous'});comparison=comparator(database,gold,dic);availability=next(x for x in read(artifact.published/'controlled-dispositions.json')if x['blind_id']==v['blind_id']);row.update({k:value for k,value in comparison.items()if k in availability});pg,gg=content_bag(database,dic),content_bag(gold,dic);row['content_f1']=2*sum((pg&gg).values())/(sum(pg.values())+sum(gg.values()))
  # Reasons and scientific eligibility decisions are frozen external evidence.
  disposition=next(x for x in read(artifact.published/'controlled-dispositions.json')if x['blind_id']==v['blind_id']);row.update(eligible=eligible,status=disposition['status'],revision=revision,reason=disposition['reason'],old_eligible=prior[v['blind_id']]['determinate_pair']=='True')
  if bool(disposition['eligible'])!=eligible:raise ValueError('Controlled identity eligibility differs from the frozen evidence')
  for level in['field','record']:row['rule_'+level+'_drop']=baseline['rule_'+level+'_f1']-result['rule_'+level+'_f1']if eligible else None
  records.append(row);details.append({**row,'remaining_identity_collisions':result['ambiguous'],'baseline_identity_collisions':baseline['ambiguous']})
 if any(x['ambiguous']for x in original.values()):raise ValueError('Original controlled reference has unresolved identity')
 baselines={r['case']:r for r in records if r['family']=='original'}
 for r in records:
  for metric in['content_f1','doc2db_entity_coverage','doc2db_relation_coverage','doc2db_reference_integrity']:r[metric+'_drop']=baselines[r['case']][metric]-r[metric]if r['eligible']else None
 summary=[]
 for family in dict.fromkeys(r['family']for r in records):
  rs=[r for r in records if r['family']==family];e=[r for r in rs if r['eligible']];record={'family':family,'total':len(rs),'eligible':len(e),'excluded':len(rs)-len(e),'field_detected':sum(r['rule_field_drop']>1e-12 for r in e),'record_detected':sum(r['rule_record_drop']>1e-12 for r in e),'field_and_relation_detected':sum(r['rule_field_drop']>1e-12 and r['doc2db_relation_coverage_drop']>1e-12 for r in e),'content_unchanged':sum(abs(r['content_f1_drop'])<1e-12 for r in e),'relation_unchanged':sum(abs(r['doc2db_relation_coverage_drop'])<1e-12 for r in e)}
  for key,metric in[('content','content_f1_drop'),('entity','doc2db_entity_coverage_drop'),('relation','doc2db_relation_coverage_drop'),('integrity','doc2db_reference_integrity_drop'),('field','rule_field_drop'),('record','rule_record_drop')]:record['mean_'+key+'_drop']=sum(r[metric]for r in e)/len(e)if e else None
  summary.append(record)
 csvwrite(out/'controlled-results.csv',records);csvwrite(out/'controlled-summary.csv',summary);write(out/'controlled-dispositions.json',details)
 return {'databases':len(records),'eligible':sum(r['eligible']for r in records),'excluded':sum(not r['eligible']for r in records)}

def quality(artifact,out,scores):
 from .statistics import summarize,METRICS
 parameters=read(artifact.published/'projection/analysis-parameters.json');actual=summarize(scores,parameters);expected=read(artifact.published/'quality-analysis/i0/analysis.json')
 for section in['summary','cross_model']:
  if len(actual[section])!=len(expected[section]):raise ValueError('Quality coverage differs')
  for x,y in zip(actual[section],expected[section]):
   for metric in METRICS:
    for k in['mean','low','high']:
     if abs(x[metric][k]-y[metric][k])>1e-12:raise ValueError('Quality bootstrap differs')
 write(out/'quality-analysis/i0/analysis.json',actual);return actual

def attribution_analysis(artifact,out,categories):
 from .attribution import actual,summarize
 from .record_analysis import intervals
 import numpy as np
 dest=out/'efe-actual';dest.mkdir();counts=actual(artifact.baseline.parent/'package',dest,baseline=artifact.baseline,published=artifact.published);summarize(counts,dest)
 totals={k:sum(r.get(k,0)for r in counts)for k in['content_recovered','misattributed','relation_tp','relation_gold','relation_pred','conditional_tp','conditional_gold','conditional_pred','incomplete_aligned_records','link_only_recoverable_records']};write(out/'efe-summary.json',totals)
 relation=[]
 for domain in['clinical','basic']:
  cases=sorted({r['case']for r in counts if r['domain']==domain});rng=np.random.default_rng(20261110);ix=rng.integers(0,len(cases),(10000,len(cases)))
  for num,den,metric in[('relation_tp','relation_gold','recall'),('relation_tp','relation_pred','precision'),('conditional_tp','conditional_gold','conditional_recall'),('conditional_tp','conditional_pred','conditional_precision')]:
   by=defaultdict(list)
   for r in counts:
    if r['domain']==domain and r.get(den,0):by[r['case']].append(r[num]/r[den])
   values={c:float(np.mean(v))for c,v in by.items()};mean,low,high=intervals(values,cases,ix);relation.append({'domain':domain,'metric':metric,'estimate':mean,'low':low,'high':high,'studies':len(values)})
 csvwrite(out/'relation-summary.csv',relation)
 structure=rows(artifact.baseline/'structure/output_results.csv');passed=[r for r in structure if r['structural_status']=='pass'];hits=[r for r in passed if 'binding'in categories[r['model'],r['case']]];checked=[r for r in structure if r['structural_status']in['pass','fail']]
 write(out/'structure-summary.json',{'original_databases':len(checked),'passed':len(passed),'failed':len(checked)-len(passed),'passed_with_binding':len(hits),'by_domain':{d:{'passed':sum(r['domain']==d for r in passed),'binding':sum(r['domain']==d for r in hits)}for d in['clinical','basic']}})
 return totals

def structure_check(artifact,out):
 from .structure import parse,structural,validate_tests
 validate_tests();checked=[]
 for old in rows(artifact.baseline/'structure/output_results.csv'):
  if old['structural_status']not in['pass','fail']:continue
  path=artifact.root/'03_Benchmark_Data/02_Model_Outputs'/old['model']/old['case']/'database.json'
  if digest(path)!=old['original_sha256']:raise ValueError('Structural cohort input changed')
  schema=read(artifact.materials/'schemas'/('basic-three.schema.json'if old['domain']=='basic'else'clinical-four-compact.schema.json'));dic=read(artifact.baseline/'v15-artifacts/dictionaries'/(old['domain']+'.json'));errors,nrows,nrefs=structural(parse(path.read_bytes()),schema,dic);status='fail'if errors else'pass'
  if status!=old['structural_status']:raise ValueError('Structural validation differs')
  checked.append({'model':old['model'],'case':old['case'],'status':status,'records':nrows,'foreign_keys':nrefs,'errors':errors})
 write(out/'structure-recomputed.json',checked);return {'checked':len(checked),'passed':sum(r['status']=='pass'for r in checked)}

def resources(artifact,out):
 from .statistics import resources as summarize
 data=read(artifact.baseline/'v15-artifacts/resources/accounting.json');result=summarize(data);fx=Decimal(str(read(artifact.inputs/'currency-conversion.json')['CNY_per_USD']));expected={r['model']:r for r in rows(artifact.root/'02_Figures/02_Plot_Data/quality_cost.csv')}
 for r in result['summary']:
  cost=r['tariff_estimate'];usd=Decimal(cost['mean'])/(fx if r['currency']=='CNY'else Decimal(1));want=expected[r['model']]
  if cost['n']!=int(want['cost_n'])or abs(usd-Decimal(want['cost']))>Decimal('1e-12'):raise ValueError('Published cost accounting differs')
  r['display_cost_usd']=str(usd)
 write(out/'resource-summary.json',result);return {'positions':len(data['positions']),'request_records':len(data['requests']),'models':len(result['summary'])}

def run(a):
 start=time.time();artifact=Artifact(a.artifact_root);out=Path(a.out).resolve()
 if out.exists():raise FileExistsError('Output directory must not exist')
 if out.is_relative_to(artifact.root):raise ValueError('Write results outside the immutable material bundle')
 out.mkdir(parents=True);(out/'projection').mkdir();scores,report=score_counts(artifact,out);report={'scores':report};print('Score counts verified',flush=True)
 # Bind already adjudicated inputs; all analysis code is shipped in this repository.
 for name in['record-observations.csv','manifest.json']:shutil.copy2(artifact.inputs/'status/projection'/name,out/'projection'/name)
 shutil.copy2(artifact.published/'source-dispositions.json',out/'source-dispositions.json')
 categories=diagnostic_incidence(artifact,out,scores);report['controls']=controlled_experiment(artifact,out);print('Controlled variants verified',flush=True)
 quality(artifact,out,scores)
 from .record_analysis import record_analyses
 record_analyses(scores,artifact,out);attribution_analysis(artifact,out,categories);report['structure']=structure_check(artifact,out);report['resources']=resources(artifact,out)
 from .human import agreement
 report['human_agreement']=agreement(artifact,out/'human-agreement')
 from .diagnostics import run as diagnostics
 if (artifact.repro/'03_Experiments/reviewed_diagnostics/annotation_manifest.json').exists():
  detail,coverage=diagnostics(artifact,out/'reviewed-diagnostics');report['reviewed_diagnostics']={'binding':detail,'task_coverage':coverage}
 from .workload import summarize
 report['workload']=summarize(artifact,out/'tables')
 checks={}
 for name in['diagnostic-summary.csv','controlled-results.csv','controlled-summary.csv','width-results.csv','source-rates.csv','source-paired.csv','relation-summary.csv']:checks[name]=compare(out/name,artifact.published/name)
 for name in['study_counts.csv','model_summary.csv']:checks['efe-actual/'+name]=compare(out/'efe-actual'/name,artifact.published/'efe-actual'/name)
 for name in['source-summary.json','structure-summary.json','efe-summary.json']:
  if read(out/name)!=read(artifact.published/name):raise ValueError('Publication JSON differs: '+name)
 if a.figures:
  import subprocess
  subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('plot.py')),'--artifact-root',str(artifact.root),'--out',str(out/'figures')],check=True)
  source=Path(__file__).resolve().parents[3]/'figures'
  if source.exists():shutil.copytree(source,out/'figures/manuscript-layout')
 report.update(checks=checks,status='passed',elapsed_seconds=time.time()-start,python=platform.python_version());write(out/'verification.json',report);print(json.dumps(report,indent=2));return report

def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--artifact-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--figures',action='store_true');a=p.parse_args(argv)
 def disabled(*args,**kwargs):raise RuntimeError('Network access is disabled during paper replay')
 socket.create_connection=disabled;socket.socket.connect=disabled
 run(a)
if __name__=='__main__':main()
