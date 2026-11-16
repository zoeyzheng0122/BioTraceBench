"""Prepare complete reviewer judgments and apply the published scoring contract."""
from pathlib import Path
import argparse,json
from .io import Artifact,read,write,digest
from .scoring import projected
from model_conversation.archive import read_exact
from biotracebench_scoring.task_grading_contract import inventory,mark_all,PROMPT,RESPONSE_SCHEMA
CONTRACT='biotracebench-publication-v16-i0-1'

def prepare(a):
 artifact=Artifact(a.artifact_root);out=Path(a.out)
 if out.resolve().is_relative_to(artifact.root):raise ValueError('Write results outside the immutable material bundle')
 if out.exists():raise FileExistsError('Output directory must not exist')
 ref=artifact.published/'projection/references'/(a.case+'.json');policy,dic=artifact.policy(a.case);submitted=read_exact(a.database)
 if isinstance(submitted,dict)and isinstance(submitted.get('database'),dict):submitted=submitted['database']
 inv=inventory(submitted,read_exact(ref),dic,policy)
 if inv['diagnostics']:raise ValueError('Malformed fragments require a reviewed partial inventory; preserve original text before scientific grading')
 domain='basic'if a.case.startswith('B')else'clinical';packet={'contract':CONTRACT,'stage':'i0','case':a.case,'inventory':inv,'task_definition':read(artifact.materials/'tasks'/domain/a.case/'task.json'),'field_dictionary':dic,'policy':policy,'reference_sha256':digest(ref),'eligibility_sha256':digest(artifact.published/'source-dispositions.json'),'submitted_sha256':digest(a.database),'source_manifest':read(artifact.materials/'metadata/manifests'/domain/(a.case+'.json')),'source_base':str(Path('03_Benchmark_Data/01_Task_Materials/materials')/domain/a.case),'actor_required':'A human or direct scientific reviewer; record the actual actor and source evidence.','instruction':PROMPT.replace('Do not browse, use tools, consult ontologies, amend gold, repair the answer, or invent missing facts.','Use the supplied task and declared local study files. Preserve the reference and answer. Do not retrieve external material, repair the answer, or invent missing facts.'),'response_schema':RESPONSE_SCHEMA}
 out.mkdir(parents=True);write(out/'packet.json',packet);write(out/'binding.json',{'contract':CONTRACT,'case':a.case,'packet_sha256':digest(out/'packet.json')});print(json.dumps({'status':'ready_for_scientific_review','cells':len(inv['cells'])}))
def finalize(a):
 artifact=Artifact(a.artifact_root);packet=read(Path(a.plan)/'packet.json');binding=read(Path(a.plan)/'binding.json')
 if binding['packet_sha256']!=digest(Path(a.plan)/'packet.json')or packet['contract']!=CONTRACT:raise ValueError('Scoring packet binding changed')
 ref=artifact.published/'projection/references'/(packet['case']+'.json');masks=artifact.published/'source-dispositions.json'
 if packet['reference_sha256']!=digest(ref)or packet['eligibility_sha256']!=digest(masks):raise ValueError('Reference or eligibility identity changed')
 reply=read(a.judgment);valid=mark_all(packet['inventory'],reply)
 if valid['unresolved_items']or any(r['verdict']=='uncertain'for r in reply['records'])or any(c['category']=='uncertain'or c['verdict']=='uncertain'for c in reply['cells']):raise ValueError('Resolve scientific uncertainty before final scoring')
 out=Path(a.out)
 if out.resolve().is_relative_to(artifact.root):raise ValueError('Write results outside the immutable material bundle')
 if out.exists():raise FileExistsError('Output directory must not exist')
 out.mkdir(parents=True);result={'contract':CONTRACT,'case':packet['case'],'actor':a.actor,'packet_sha256':binding['packet_sha256'],'judgment_sha256':digest(a.judgment),'metrics':projected(packet['inventory'],reply,packet['case'],read(masks)),'reference_issues':reply['reference_issues']};write(out/'score.json',result);write(out/'judgment.json',reply);print(json.dumps(result,ensure_ascii=False,indent=2))
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
 q=sub.add_parser('prepare');q.add_argument('--artifact-root',type=Path,required=True);q.add_argument('--case',required=True);q.add_argument('--database',type=Path,required=True);q.add_argument('--out',type=Path,required=True)
 q=sub.add_parser('finalize');q.add_argument('--artifact-root',type=Path,required=True);q.add_argument('--plan',type=Path,required=True);q.add_argument('--judgment',type=Path,required=True);q.add_argument('--actor',required=True);q.add_argument('--out',type=Path,required=True)
 a=p.parse_args(argv);{'prepare':prepare,'finalize':finalize}[a.command](a)
if __name__=='__main__':main()
