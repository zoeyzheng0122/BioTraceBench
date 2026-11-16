"""Offline release replay rejects broken bindings and preserves scientific context."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from model_conversation.archive import encoded, exact_json

from biotracebench_scoring.task_grading_contract import inventory
from biotracebench_scoring.archive_replay import replay, context_signature, databases, inventory_content, read

POLICY = {'reference_contract':'biotracebench-fixed-reference-1', 'field_roles':{}}
SPEC = {'sample':{'identifier':'id','fields':[{'key':'id','type':'id'}, {'key':'name','type':'text'}, {'key':'time','type':'text'}], 'references':{}}}

def fixture(root):
    ref={'sample':[{'id':'R1','name':'treated','time':'day 7'}]}
    pred={'sample':[{'id':'P1','name':'treated','time':'day 7'}]}
    inv=inventory(pred,ref,SPEC,POLICY)
    p,g=inv['rows']; cells=inv['cells']
    marks={'records':[{'prediction_row':p['id'],'reference_row':g['id'],'verdict':'matched','reason':'Same preparation.'}],
           'reference_issues':[], 'cells':[]}
    for a,b in zip(cells[:3],cells[3:]):
        marks['cells'].append({'prediction_cell':a['id'],'reference_cell':b['id'],'category':a['role'],
                              'verdict':'not_scored' if a['role']=='identifier' else 'correct','reason':'Same item.'})
    data={'policy.json':POLICY,'spec.json':SPEC,'reference.json':ref,'j.json':{'inventory':inv,'marking':marks}}
    for name,value in data.items(): (root/name).write_text(json.dumps(value))
    m={'format':'biotracebench-replay-1','models':['m'],'conditions':['i0'],
       'cases':[{'case':'B001','domain':'basic','reference':'reference.json','dictionary':'spec.json'}],
       'positions':[{'model':'m','case':'B001','condition':'i0','domain':'basic','zero_cause':None,'judgment':'j.json'}],
       'policy':'policy.json','files':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in data}}
    (root/'manifest.json').write_text(json.dumps(m));return m,inv,marks

class ArchiveReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.m,self.inv,self.marks=fixture(self.root)
    def tearDown(self):self.tmp.cleanup()
    def save(self): (self.root/'manifest.json').write_text(json.dumps(self.m))
    def test_recomputes_counts_not_expected_totals(self):
        r=replay(self.root/'manifest.json'); self.assertEqual(r['scores'][0]['field_f1'],1)
        self.assertEqual(r['scores'][0]['record_tp'],1)
    def test_rejects_missing_duplicate_and_unknown_positions(self):
        for positions in [[],self.m['positions']*2,[{**self.m['positions'][0],'model':'alien'}]]:
            with self.subTest(positions=positions):
                self.m['positions']=positions;self.save()
                with self.assertRaises(ValueError):replay(self.root/'manifest.json')
    def test_rejects_modified_evidence(self):
        (self.root/'j.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'hash'):replay(self.root/'manifest.json')
    def test_rejects_path_escape(self):
        self.m['files']['../outside']='0'*64;self.save()
        with self.assertRaises(ValueError):replay(self.root/'manifest.json')
    def test_rejects_claimed_inventory_that_differs_from_reference(self):
        self.inv['cells'][-1]['value_json']='"day 8"'
        self.replace_judgment()
        with self.assertRaisesRegex(ValueError,'inventory'):replay(self.root/'manifest.json')
    def test_rejects_incomplete_judgments(self):
        self.marks['cells'].pop();self.replace_judgment()
        with self.assertRaises(ValueError):replay(self.root/'manifest.json')
    def replace_judgment(self):
        p=self.root/'j.json';p.write_text(json.dumps({'inventory':self.inv,'marking':self.marks}))
        self.m['files']['j.json']=hashlib.sha256(p.read_bytes()).hexdigest();self.save()
    def test_zero_keeps_reference_denominator(self):
        self.m['positions'][0].pop('judgment');self.m['positions'][0]['zero_cause']='downstream_not_started';self.save()
        row=replay(self.root/'manifest.json')['scores'][0]
        self.assertEqual((row['field_gold'],row['field_f1'],row['record_gold']),(2,0,1))
    def test_signature_ignores_internal_ids_and_row_order_but_keeps_time(self):
        renamed=copy.deepcopy(self.inv)
        for c in renamed['cells']:
            if c['role']=='identifier':c['value_json']='"local-other"'
        renamed['cells'].reverse();renamed['rows'].reverse()
        self.assertEqual(context_signature(self.inv,SPEC),context_signature(renamed,SPEC))
        next(c for c in renamed['cells'] if c['side']=='prediction' and c['field']=='time')['value_json']='"day 8"'
        self.assertNotEqual(context_signature(self.inv,SPEC),context_signature(renamed,SPEC))
    def test_linked_population_is_part_of_context(self):
        spec={**SPEC,'result':{'identifier':'id','references':{'population_id':'sample'},
              'fields':[{'key':'id','type':'id'},{'key':'population_id','type':'id'},{'key':'value','type':'number'}]}}
        pred={'sample':[{'id':'A','name':'treated','time':'day 7'},{'id':'B','name':'control','time':'day 7'}],
              'result':[{'id':'X','population_id':'A','value':4}]}
        inv=inventory(pred,{},spec,POLICY)
        renamed=copy.deepcopy(pred);renamed['sample'].reverse()
        for row in renamed['sample']:row['id']='new-'+row['id']
        renamed['result'][0]['population_id']='new-A'
        self.assertEqual(context_signature(inv,spec),context_signature(inventory(renamed,{},spec,POLICY),spec))
        renamed['result'][0]['population_id']='new-B'
        self.assertNotEqual(context_signature(inv,spec),context_signature(inventory(renamed,{},spec,POLICY),spec))
    def test_candidate_overlay_recomputes_record_credit_and_checks_old_verdict(self):
        mark=next(x for x in self.marks['cells'] if x['category']=='scientific')
        change=dict(position=['m','B001','i0'],judgment_sha256=self.m['files']['j.json'],
            prediction_cell=mark['prediction_cell'],reference_cell=mark['reference_cell'],old_verdict='correct',new_verdict='incorrect',
            reason='A documented source correction.',evidence=[{'path':'reference.json','sha256':self.m['files']['reference.json']}])
        overlay={'baseline_manifest_sha256':hashlib.sha256((self.root/'manifest.json').read_bytes()).hexdigest(),'changes':[change]}
        path=self.root/'candidate.json';path.write_text(json.dumps(overlay))
        row=replay(self.root/'manifest.json',path)['scores'][0]
        self.assertEqual((row['field_tp'],row['record_tp'],row['field_f1']),(1,0,.5))
        change['old_verdict']='incorrect';path.write_text(json.dumps(overlay))
        with self.assertRaisesRegex(ValueError,'precondition'):replay(self.root/'manifest.json',path)

    def numeric_inventory(self, literal, reference=False):
        db=exact_json('{"sample":[{"id":"x","name":"treated","time":'+literal+'}]}')
        return inventory({} if reference else db,db if reference else {},SPEC,POLICY)

    def test_signatures_preserve_written_precision_and_numeric_types(self):
        pairs=[('1.0','1.00'),('1e3','1.0e3'),
               ('0.123456789012345678901','0.123456789012345678902'),
               ('{"values":[1.0]}','{"values":[1.00]}'),('1.00','"1.00"')]
        for left,right in pairs:
            with self.subTest(left=left,right=right):
                self.assertNotEqual(context_signature(self.numeric_inventory(left),SPEC),
                                    context_signature(self.numeric_inventory(right),SPEC))

    def test_inventory_integrity_preserves_exact_reference_decimals(self):
        for left,right in [('1.0','1.00'),('0.123456789012345678901','0.123456789012345678902')]:
            with self.subTest(left=left,right=right):
                self.assertNotEqual(inventory_content(self.numeric_inventory(left,True)),
                                    inventory_content(self.numeric_inventory(right,True)))

    def test_reconstruction_preserves_nested_and_diagnostic_decimals(self):
        pred=exact_json('{"sample":[{"id":"x","name":"treated","time":{"values":[1.00,1e3]}}]}')
        inv=inventory(pred,{},SPEC,POLICY)
        self.assertEqual(encoded(databases(inv)['prediction']),encoded(pred))
        malformed=exact_json('{"sample":[[1.00,0.123456789012345678901]]}')
        self.assertEqual(encoded(databases(inventory(malformed,{},SPEC,POLICY))['prediction']),encoded(malformed))

    def set_numeric_reference(self, literal, archived_literal=None):
        ref=exact_json('{"sample":[{"id":"R1","name":"treated","time":'+literal+'}]}')
        (self.root/'reference.json').write_bytes(encoded(ref))
        self.m['files']['reference.json']=hashlib.sha256((self.root/'reference.json').read_bytes()).hexdigest()
        for c in self.inv['cells']:
            if c['field']=='time':c['value_json']=archived_literal if c['side']=='reference' and archived_literal is not None else literal
        self.replace_judgment()

    def test_replay_reads_reference_numbers_without_losing_precision(self):
        self.set_numeric_reference('1.00')
        result=replay(self.root/'manifest.json')
        self.assertEqual(result['scores'][0]['field_f1'],1)
        self.assertEqual(result['consistency_signature_version'],'lossless-decimal-1')

    def test_replay_rejects_precision_only_reference_mismatch(self):
        for reference,archived in [('1.00','1.0'),('0.123456789012345678901','0.123456789012345678902')]:
            with self.subTest(reference=reference,archived=archived):
                self.set_numeric_reference(reference,archived)
                with self.assertRaisesRegex(ValueError,'inventory'):replay(self.root/'manifest.json')

    def test_precision_dependent_archived_verdicts_do_not_conflict(self):
        self.set_numeric_reference('1.04')
        for c in self.inv['cells']:
            if c['side']=='prediction' and c['field']=='time':c['value_json']='1.0'
        self.replace_judgment()
        other=copy.deepcopy({'inventory':self.inv,'marking':self.marks})
        for c in other['inventory']['cells']:
            if c['side']=='prediction' and c['field']=='time':
                c['value_json']='1.00';cell=c['id']
        next(m for m in other['marking']['cells'] if m['prediction_cell']==cell)['verdict']='incorrect'
        (self.root/'j2.json').write_text(json.dumps(other))
        self.m['files']['j2.json']=hashlib.sha256((self.root/'j2.json').read_bytes()).hexdigest()
        self.m['models'].append('second')
        self.m['positions'].append({**self.m['positions'][0],'model':'second','judgment':'j2.json'})
        self.save();result=replay(self.root/'manifest.json')
        self.assertEqual(result['consistency_conflicts'],[])
        self.assertNotEqual(result['scores'][0]['field_f1'],result['scores'][1]['field_f1'])

    def test_metadata_reading_keeps_ordinary_metric_types(self):
        path=self.root/'metadata.json';path.write_text('{"expected":0.25}')
        self.assertIs(type(read(path)['expected']),float)

if __name__=='__main__':unittest.main()
