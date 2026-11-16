"""Publication contracts exercised entirely with synthetic values."""
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
from contextlib import redirect_stdout
import json,tempfile,unittest,io
from biotracebench_analysis.publication.demo import fixture,supplied_judgment
from biotracebench_analysis.publication.scoring import projected
from biotracebench_analysis.publication.controlled import evaluate
from biotracebench_analysis.publication.structure import parse,structural
from biotracebench_analysis.publication.io import Artifact,write,read
from biotracebench_analysis.publication.score_output import prepare,finalize
from biotracebench_scoring.task_grading_contract import inventory,mark_all
from model_conversation.archive import exact_json

class PublicationTests(unittest.TestCase):
 def setUp(self):
  self.dic,self.policy,self.gold,self.pred=fixture();self.inv=inventory(self.pred,self.gold,self.dic,self.policy);self.reply=supplied_judgment(self.inv)
 def test_whole_fields_and_complete_records(self):
  mark_all(self.inv,self.reply);score=projected(self.inv,self.reply,'SYNTHETIC');self.assertEqual([score['field'][x]for x in['tp','predicted','gold']],[4,5,6]);self.assertEqual([score['record'][x]for x in['tp','predicted','gold']],[1,2,2])
 def test_missing_cell_cannot_be_finalized(self):
  self.reply['cells'].pop()
  with self.assertRaises(ValueError):mark_all(self.inv,self.reply)
 def test_duplicate_mark_cannot_be_finalized(self):
  self.reply['cells'].append(self.reply['cells'][0])
  with self.assertRaises(ValueError):mark_all(self.inv,self.reply)
 def test_explicit_null_is_missing_for_a_reported_fact(self):
  self.pred['population'][0]['population_size']=None;inv=inventory(self.pred,self.gold,self.dic,self.policy);r=supplied_judgment(inv);self.assertEqual(projected(inv,r,'SYNTHETIC')['field']['tp'],3)
 def test_zero_reference_targets_are_undefined(self):
  masks=[{'case':'SYNTHETIC','table':'population','row_index':i,'field_exclusions':['*'],'main_record_scoring':'excluded'}for i in range(2)];x=projected(self.inv,self.reply,'SYNTHETIC',masks)
  for level in['field','record']:
   for metric in['precision','recall','f1']:self.assertIsNone(x[level][metric])
 def test_lexical_number_precision_survives(self):self.assertEqual(str(exact_json('{"value":2.00}')['value']),'2.00')
 def test_row_order_and_local_ids_are_equivalent(self):
  pred=deepcopy(self.gold);pred['population'].reverse()
  for i,r in enumerate(pred['population']):r['population_id']='submitted-'+str(i)
  score=evaluate(pred,self.gold,self.dic);self.assertEqual(score['rule_field_f1'],1);self.assertEqual(score['rule_record_f1'],1)
 def test_a_merged_object_cannot_match_two_objects(self):
  pred=deepcopy(self.gold);pred['population']=[pred['population'][0]];score=evaluate(pred,self.gold,self.dic);self.assertEqual(score['rule_record_tp'],1);self.assertEqual(score['rule_record_gold'],2)
 def test_surplus_duplicate_remains_a_prediction(self):
  pred=deepcopy(self.gold);pred['population'].append(deepcopy(pred['population'][0]));score=evaluate(pred,self.gold,self.dic);self.assertEqual(score['rule_record_predicted'],3);self.assertLess(score['rule_record_f1'],1)
 def test_wrong_number_loses_the_whole_field(self):
  pred=deepcopy(self.gold);pred['population'][0]['population_size']=41;score=evaluate(pred,self.gold,self.dic);self.assertEqual(score['rule_field_tp'],5);self.assertEqual(score['rule_record_tp'],1)
 def test_duplicate_keys_and_nonfinite_numbers_rejected(self):
  for raw in[b'{"x":1,"x":2}',b'{"x":NaN}']:
   with self.assertRaises(ValueError):parse(raw)
 def test_declared_foreign_key_target_checked(self):
  dic=deepcopy(self.dic);dic['result']={'identifier':'result_id','references':{'population_id':'population'},'fields':[{'key':'result_id'},{'key':'population_id'}]};db=deepcopy(self.gold);db['result']=[{'result_id':'X','population_id':'missing'}];errors,_,_=structural(db,{'type':'object'},dic);self.assertTrue(errors)

class OutputInterfaceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.artifact=self.root/'materials';self.case='C000';self.ref={'population':[{**{f['key']:None for f in read(Path(__file__).parents[1]/'configs/scoring/clinical.json')['population']['fields']},'population_id':'R1','population_name':'Synthetic arm','population_size':3}]};self.db=self.root/'submission.json';write(self.db,self.ref)
  write(self.artifact/'04_Reproducibility/02_Published_Evaluation/source-dispositions.json',[]);write(self.artifact/'04_Reproducibility/02_Published_Evaluation/projection/references/C000.json',self.ref);write(self.artifact/'03_Benchmark_Data/01_Task_Materials/tasks/clinical/C000/task.json',{'case_id':self.case,'scope':'Synthetic test only'});write(self.artifact/'03_Benchmark_Data/01_Task_Materials/metadata/manifests/clinical/C000.json',{'files':[]})
  self.plan=self.root/'plan'
  with redirect_stdout(io.StringIO()):prepare(SimpleNamespace(artifact_root=self.artifact,out=self.plan,case=self.case,database=self.db))
  self.packet=read(self.plan/'packet.json');self.reply=supplied_judgment(self.packet['inventory'])
 def tearDown(self):self.tmp.cleanup()
 def finish(self):
  q=self.root/'judgment.json';write(q,self.reply)
  with redirect_stdout(io.StringIO()):finalize(SimpleNamespace(artifact_root=self.artifact,plan=self.plan,judgment=q,actor='Synthetic test',out=self.root/'score'))
 def test_prepare_needs_no_previous_model_judgments(self):
  self.assertFalse((self.artifact/'04_Reproducibility/02_Published_Evaluation/projection/judgments').exists());self.finish();self.assertEqual(read(self.root/'score/score.json')['metrics']['field']['f1'],1)
 def test_packet_tampering_rejected(self):
  self.packet['case']='invalid';write(self.plan/'packet.json',self.packet)
  with self.assertRaises(ValueError):self.finish()
 def test_reference_tampering_rejected(self):
  write(self.artifact/'04_Reproducibility/02_Published_Evaluation/projection/references/C000.json',{})
  with self.assertRaises(ValueError):self.finish()
 def test_uncertain_scientific_judgment_rejected(self):
  next(x for x in self.reply['cells']if x['verdict']=='correct')['verdict']='uncertain'
  with self.assertRaises(ValueError):self.finish()

if __name__=='__main__':unittest.main()
