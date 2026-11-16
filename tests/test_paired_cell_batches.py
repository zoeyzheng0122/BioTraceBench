"""Synthetic mapping and cell phases; no live providers or scientific fixtures."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from biotracebench_scoring.task_grading_batches import (
    batches,record_plan,pair_request,cell_request,check_pair_reply,check_cell_reply,
    combine,PAIR_INSTRUCTION,CELL_INSTRUCTION)
from biotracebench_scoring.task_grading_contract import inventory,mark_all,PROMPT
import test_biotracebench_task_grading as f


class BatchContractTests(unittest.TestCase):
    def fixture(self,count=60):
        db={'sample':[{'id':f'S{i}','label':str(i),'value':i,'optional':None} for i in range(count)]}
        inv=inventory(db,db,f.DICT,f.POLICY);reply=f.reply_for(inv)
        base={'protocol_version':'base','stage':'task_grading','instruction':PROMPT,
            'payload':{'inventory':inv,'task_definition':'Synthetic full task','dictionary_json':'frozen',
                'scoring_policy_json':'frozen','sources':[]},'response_schema':{},'images':[]}
        return inv,reply,base

    def test_batches_preserve_whole_records_and_exact_global_pairs(self):
        inv,reply,_=self.fixture();scopes=batches(inv,reply['records'])
        self.assertEqual(len(scopes),2)
        self.assertTrue(all(len(b['expected_cell_pairs'])<=200 for b in scopes))
        self.assertEqual([i for b in scopes for i in b['record_indices']],list(range(60)))
        pairs=[(p['prediction_cell'],p['reference_cell']) for b in scopes for p in b['expected_cell_pairs']]
        self.assertEqual(len(pairs),240);self.assertEqual(len(set(pairs)),240)

    def test_model_mapping_is_required_and_never_inferred(self):
        inv,reply,_=self.fixture(2)
        for malformed in [reply['records'][:-1],reply['records']+[reply['records'][0]]]:
            with self.assertRaises(ValueError):record_plan(inv,malformed)

    def test_wrong_direction_and_wrong_side_rejected(self):
        inv,reply,_=self.fixture(1)
        for changes in [{'verdict':'missing'},{'reference_row':'p0'},{'prediction_row':None,'verdict':'extra'}]:
            r=copy.deepcopy(reply['records']);r[0].update(changes)
            with self.assertRaises(ValueError):record_plan(inv,r)

    def test_phase_envelopes_are_exact(self):
        inv,reply,_=self.fixture(1)
        self.assertEqual(check_pair_reply(inv,{'records':reply['records']}),reply['records'])
        with self.assertRaises(ValueError):check_pair_reply(inv,reply)

    def test_each_request_preserves_all_original_task_context(self):
        inv,reply,base=self.fixture();before=copy.deepcopy(base)
        pair=pair_request(base);self.assertEqual(pair['payload'],base['payload'])
        scope=batches(inv,reply['records'])[0];cell=cell_request(base,reply['records'],scope)
        for k,v in base['payload'].items():self.assertEqual(cell['payload'][k],v)
        self.assertEqual(cell['payload']['frozen_record_pairs'],reply['records'])
        self.assertEqual(base,before)
        self.assertIn(PROMPT,PAIR_INSTRUCTION);self.assertIn(PROMPT,CELL_INSTRUCTION)

    def test_complete_batches_equal_original_whole_task_metrics(self):
        inv,reply,_=self.fixture();scopes=batches(inv,reply['records']);responses=[]
        for b in scopes:
            ids={(p['prediction_cell'],p['reference_cell']) for p in b['expected_cell_pairs']}
            responses.append({'cells':[x for x in reply['cells'] if (x['prediction_cell'],x['reference_cell']) in ids],
                'reference_issues':[]})
        complete,result=combine(inv,reply['records'],scopes,responses)
        self.assertEqual(complete,reply);self.assertEqual(result,mark_all(inv,reply))

    def test_missing_duplicate_wrong_id_or_reclassified_cell_is_rejected(self):
        inv,reply,_=self.fixture(1);scope=batches(inv,reply['records'])[0]
        good={'cells':reply['cells'],'reference_issues':[]};variants=[]
        v=copy.deepcopy(good);v['cells'].pop();variants.append(v)
        v=copy.deepcopy(good);v['cells'].append(v['cells'][0]);variants.append(v)
        v=copy.deepcopy(good);v['cells'][0]['prediction_cell']='c9999';variants.append(v)
        v=copy.deepcopy(good);v['cells'][0]['category']='out_of_scope';variants.append(v)
        for v in variants:
            with self.assertRaises(ValueError):check_cell_reply(inv,reply['records'],scope,v)

    def test_incomplete_batch_set_never_becomes_a_score(self):
        inv,reply,_=self.fixture();scopes=batches(inv,reply['records'])
        with self.assertRaises(ValueError):combine(inv,reply['records'],scopes,[])

    def test_changed_frozen_scope_cannot_be_requested(self):
        inv,reply,base=self.fixture();scope=batches(inv,reply['records'])[0]
        scope['expected_cell_pairs'][0]['reference_cell']='c9999'
        with self.assertRaises(ValueError):cell_request(base,reply['records'],scope)

    def test_oversize_record_is_not_split(self):
        inv,reply,_=self.fixture(1)
        with self.assertRaisesRegex(ValueError,'no field splitting'):batches(inv,reply['records'],limit=3)


if __name__=='__main__':unittest.main()
