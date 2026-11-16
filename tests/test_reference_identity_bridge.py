import copy
import unittest

from model_conversation.archive import digest
from biotracebench_scoring.reference_identity_bridge import FORMAT, validate_reference_bridge
from biotracebench_scoring.task_grading_contract import inventory
from test_native_codex import DICT, POLICY


class ReferenceIdentityBridgeTests(unittest.TestCase):
    def fixture(self):
        before = inventory({}, {'sample': [{'id':'S1','label':'Arm A','value':5,'optional':None},
                                           {'id':'S2','label':'Arm B','value':3,'optional':None}]}, DICT, POLICY)
        after = inventory({}, {'sample': [{'id':'S1','label':'Arm A','value':6,'optional':None}]}, DICT, POLICY)
        oldrow=next(x for x in before['rows'] if x['row_index']==0)
        newrow=next(x for x in after['rows'] if x['row_index']==0)
        def stripped(inv, row, field):
            cell=next(x for x in inv['cells'] if x['row']==row['id'] and x['field']==field)
            return {k:v for k,v in cell.items() if k not in ('id','row','row_index')}
        evidence={'source_id':'s','quote':'Arm A has value 6.','reason':'Synthetic source decision.'}
        bridge={'format':FORMAT,'before_identity':digest(before),'after_identity':digest(after),
                'author':{'kind':'native_codex','agent_id':'/root/test','session_id':'synthetic'},
                'pairs':[{'before':oldrow['id'],'after':newrow['id'],'anchors':['label'],**evidence,
                          'changes':[{'field':'value','before':stripped(before,oldrow,'value'),
                                      'after':stripped(after,newrow,'value'),**evidence}]}],
                'removed':[{'row':before['rows'][1]['id'],**evidence}],'added':[]}
        return before,after,[{'id':'s','text':'Arm A has value 6. Arm B is out of scope.'}],bridge

    def test_explicit_source_evidence_and_exact_changes(self):
        a,b,s,m=self.fixture();result=validate_reference_bridge(a,b,s,m)
        self.assertEqual((result['pairs'],result['removed'],result['added']),(1,1,0))

    def test_undeclared_change_and_unaccounted_record_fail(self):
        a,b,s,m=self.fixture();m['pairs'][0]['changes']=[]
        with self.assertRaisesRegex(ValueError,'declared exactly'):validate_reference_bridge(a,b,s,m)
        a,b,s,m=self.fixture();m['removed']=[]
        with self.assertRaisesRegex(ValueError,'every reference row'):validate_reference_bridge(a,b,s,m)

    def test_no_id_only_match_or_fabricated_source_quote(self):
        a,b,s,m=self.fixture();m['pairs'][0]['anchors']=['id']
        with self.assertRaisesRegex(ValueError,'scientific fields'):validate_reference_bridge(a,b,s,m)
        a,b,s,m=self.fixture();m['pairs'][0]['quote']='not in the source'
        with self.assertRaisesRegex(ValueError,'source quote'):validate_reference_bridge(a,b,s,m)

    def test_identity_and_one_to_one_are_enforced(self):
        a,b,s,m=self.fixture();m['before_identity']='altered'
        with self.assertRaisesRegex(ValueError,'identity mismatch'):validate_reference_bridge(a,b,s,m)
        a,b,s,m=self.fixture();m['pairs'].append(copy.deepcopy(m['pairs'][0]))
        with self.assertRaisesRegex(ValueError,'one-to-one'):validate_reference_bridge(a,b,s,m)

    def test_changed_lexeme_is_not_silently_accepted(self):
        a,b,s,m=self.fixture();m['pairs'][0]['changes'][0]['after']['value_json']='6.0'
        with self.assertRaisesRegex(ValueError,'do not match'):validate_reference_bridge(a,b,s,m)

    def test_submission_and_author_must_remain_verifiable(self):
        a,b,s,m=self.fixture();m['author']['agent_id']=''
        with self.assertRaisesRegex(ValueError,'attributable'):validate_reference_bridge(a,b,s,m)
        a,b,s,m=self.fixture();b['diagnostics'].append({'error':'new'});m['after_identity']=digest(b)
        with self.assertRaisesRegex(ValueError,'diagnostics'):validate_reference_bridge(a,b,s,m)

    def test_added_reference_row_requires_its_own_evidence(self):
        a,b,s,m=self.fixture()
        # Reversing the inventories makes the original removal an addition.
        pair=m['pairs'][0];pair['before'],pair['after']=pair['after'],pair['before']
        for change in pair['changes']:
            change['before'],change['after']=change['after'],change['before']
        m['before_identity'],m['after_identity']=digest(b),digest(a)
        m['added'],m['removed']=m['removed'],[]
        self.assertEqual(validate_reference_bridge(b,a,s,m)['added'],1)
        m['added'][0]['quote']='Unsupported addition'
        with self.assertRaisesRegex(ValueError,'source quote'):validate_reference_bridge(b,a,s,m)
