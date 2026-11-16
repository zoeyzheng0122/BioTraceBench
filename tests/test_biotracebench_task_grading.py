"""Whole-task machine marking and external manual inspection; synthetic providers only."""
import copy
import json
import tempfile
import unittest
from itertools import zip_longest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from model_conversation.archive import read, write, seal, verify, verify_events
from model_api import Backend
from biotracebench_scoring import task_grading as grading
from biotracebench_scoring.task_grading_contract import PROMPT, inventory, mark_all

ROOT=Path(__file__).resolve().parents[1]
PROFILE=ROOT/'configs/models/profiles/qwen3.8-max-judge.json'
DICT={'sample':{'identifier':'id','fields':[{'key':k} for k in ('id','label','value','optional')]}}
GOLD={'sample':[{'id':'S1','label':'A','value':60,'optional':None}]}
POLICY={'version':'biotracebench-score-2','reference_contract':'biotracebench-fixed-reference-1',
        'compound_fields':[],'identity_task_rules':{},'field_roles':{},'frozen':False}
BUDGET={'max_requests':10,'per_request_cny':1,'total_cny':10,'max_input_cny_per_million':1,
        'max_output_cny_per_million':1,'price_source':'synthetic tariff, not live','price_verified_at':'2026-10-29'}


def reply_for(inv, pairs=None, overrides=None):
    """Invent a Qwen reply from explicit fixture pairing, not scorer decisions."""
    sides={s:[r for r in inv['rows'] if r['side']==s] for s in ('prediction','reference')}
    pairs=pairs if pairs is not None else list(zip_longest(sides['prediction'],sides['reference']))
    result={'records':[],'cells':[],'reference_issues':[]}
    for p,g in pairs:
        result['records'].append({'prediction_row':p['id'] if p else None,'reference_row':g['id'] if g else None,
            'verdict':'matched' if p and g else 'extra' if p else 'missing','reason':'Synthetic object identity.'})
        pc={c['field']:c for c in inv['cells'] if p and c['row']==p['id']}
        gc={c['field']:c for c in inv['cells'] if g and c['row']==g['id']}
        for key in sorted(set(pc)|set(gc)):
            a,b=pc.get(key),gc.get(key);role=(b or a)['role']
            category=role if role!='unclassified' else 'scientific'
            ap=bool(a and a['nonempty']);bp=bool(b and b['nonempty'])
            verdict=('not_scored' if category!='scientific' or not ap and not bp else
                     'missing' if not ap else 'extra' if not bp else
                     'correct' if a['value_json']==b['value_json'] else 'incorrect')
            verdict=(overrides or {}).get(key,verdict)
            result['cells'].append({'prediction_cell':a['id'] if a else None,'reference_cell':b['id'] if b else None,
                'category':category,'verdict':verdict,'reason':'Synthetic whole-cell judgment.'})
    return result


class ContractTests(unittest.TestCase):
    def inv(self,pred=GOLD,gold=GOLD):return inventory(pred,gold,DICT,POLICY)

    def test_complete_marking_has_no_human_gate_or_partial_field_credit(self):
        inv=self.inv();result=mark_all(inv,reply_for(inv))
        self.assertEqual(result['field'],{'tp':2,'predicted':2,'gold':2,'precision':1,'recall':1,'f1':1})
        self.assertEqual(result['mark_counts']['not_scored'],2)
        self.assertEqual(result['status'],'automatic_scoring_completed')
        self.assertFalse(result['human_review']['required_for_automatic_completion'])
        self.assertEqual(len(result['cells']),4)

    def test_prompt_distinguishes_inventory_ids_from_values_and_null_content(self):
        self.assertIn('must copy the id of an existing inventory.cells entry', PROMPT)
        self.assertIn('an existing cell still requires its c-prefixed inventory ID', PROMPT)
        self.assertIn('never an ID range or comma-separated IDs', PROMPT)

    def test_cell_values_cannot_replace_inventory_ids(self):
        inv=self.inv();reply=reply_for(inv)
        cell=next(c for c in inv['cells'] if c['field']=='id' and c['side']=='prediction')
        item=next(c for c in reply['cells'] if c['prediction_cell']==cell['id'])
        item['prediction_cell']=json.loads(cell['value_json'])
        with self.assertRaisesRegex(ValueError,'Unknown, duplicate or incorrectly paired'):
            mark_all(inv,reply)

    def test_null_valued_existing_cell_keeps_its_inventory_pointer(self):
        inv=self.inv();reply=reply_for(inv)
        cell=next(c for c in inv['cells'] if c['field']=='optional' and c['side']=='reference')
        item=next(c for c in reply['cells'] if c['reference_cell']==cell['id'])
        self.assertEqual(item['verdict'],'not_scored')
        self.assertEqual(mark_all(inv,reply)['field']['f1'],1)
        item['reference_cell']=None
        with self.assertRaisesRegex(ValueError,'Unknown, duplicate or incorrectly paired'):
            mark_all(inv,reply)

    def test_reference_issues_require_one_reference_inventory_id_per_item(self):
        inv=self.inv();reply=reply_for(inv)
        refs=[c['id'] for c in inv['cells'] if c['side']=='reference']
        for invalid in [refs[0]+'-'+refs[-1], ','.join(refs[:2]), 'S1']:
            reply['reference_issues']=[{'reference_cell':invalid,'reason':'Synthetic defect.'}]
            with self.assertRaisesRegex(ValueError,'existing gold cell'):
                mark_all(inv,reply)
        reply['reference_issues']=[{'reference_cell':c,'reason':'Synthetic defect.'} for c in refs[:2]]
        self.assertEqual(len(mark_all(inv,reply)['reference_issues']),2)

    def test_prompt_keeps_suspected_reference_defects_under_declared_roles(self):
        self.assertIn('Copy every declared inventory role', PROMPT)
        self.assertIn('only a role explicitly marked unclassified may be classified', PROMPT)
        self.assertIn('separately report suspected reference defects in reference_issues', PROMPT)

    def test_reference_only_scientific_cell_cannot_be_excluded_for_suspected_scope(self):
        inv=self.inv(None);reply=reply_for(inv)
        item=next(c for c in reply['cells'] if c['category']=='scientific' and c['verdict']=='missing')
        item.update(category='out_of_scope',verdict='not_scored')
        with self.assertRaisesRegex(ValueError,'cannot reclassify'):
            mark_all(inv,reply)
        item.update(category='scientific',verdict='missing')
        reply['reference_issues']=[{'reference_cell':item['reference_cell'],'reason':'Synthetic suspected reference defect.'}]
        result=mark_all(inv,reply)
        self.assertEqual(result['field']['gold'],2)
        self.assertEqual(result['field']['tp'],0)
        self.assertEqual(len(result['reference_issues']),1)

    def test_declared_identifier_role_is_not_reclassified_as_scientific(self):
        inv=self.inv();reply=reply_for(inv)
        item=next(c for c in reply['cells'] if c['category']=='identifier')
        item.update(category='scientific',verdict='correct')
        with self.assertRaisesRegex(ValueError,'cannot reclassify'):
            mark_all(inv,reply)

    def test_prompt_requires_complete_large_inventory_without_summaries(self):
        self.assertIn('Complete coverage is mandatory for this large inventory', PROMPT)
        self.assertIn('including identifier/provenance cells and null-valued cells', PROMPT)
        self.assertIn('do not stop after a subset of rows', PROMPT)

    def test_omitted_repeated_row_cells_are_rejected(self):
        gold=copy.deepcopy(GOLD);gold['sample'].append(copy.deepcopy(gold['sample'][0]))
        inv=self.inv(gold,gold);reply=reply_for(inv)
        reply['cells']=reply['cells'][:4]
        with self.assertRaisesRegex(ValueError,'omitted cells'):
            mark_all(inv,reply)

    def test_prompt_explicitly_defines_pair_verdict_direction(self):
        self.assertIn('a null prediction_row with an existing reference_row is missing', PROMPT)
        self.assertIn('an existing prediction_row with a null reference_row is extra', PROMPT)
        self.assertIn('matched requires both row IDs', PROMPT)

    def test_reference_only_extra_and_prediction_only_missing_are_rejected(self):
        for prediction,reference,wrong in [(None,GOLD,'extra'),(GOLD,{},'missing')]:
            inv=inventory(prediction,reference,DICT,POLICY);reply=reply_for(inv)
            reply['records'][0]['verdict']=wrong
            with self.assertRaisesRegex(ValueError,'Record verdict contradicts its pair'):
                mark_all(inv,reply)

    def test_valid_one_sided_directions_preserve_existing_denominators(self):
        for prediction,reference,key in [(None,GOLD,'gold'),(GOLD,{},'predicted')]:
            inv=inventory(prediction,reference,DICT,POLICY);result=mark_all(inv,reply_for(inv))
            self.assertEqual(result['record'][key],1)
            self.assertEqual(result['field'][key],2)
            self.assertEqual(result['record']['tp'],0)

    def test_prompt_requires_per_record_walk_and_cell_id_conservation(self):
        self.assertIn('finish the complete sorted union of field names for one record pair', PROMPT)
        self.assertIn('Never skip an entire table', PROMPT)
        self.assertIn('every prediction-side inventory.cells id occurs exactly once', PROMPT)
        self.assertIn('every reference-side inventory.cells id occurs exactly once', PROMPT)

    def test_omitting_a_fully_matched_table_still_fails_coverage(self):
        dictionary={name:copy.deepcopy(DICT['sample']) for name in ['condition','sample']}
        database={name:copy.deepcopy(GOLD['sample']) for name in dictionary}
        inv=inventory(database,database,dictionary,POLICY);reply=reply_for(inv)
        omitted={c['id'] for c in inv['cells'] if c['table']=='condition'}
        reply['cells']=[c for c in reply['cells'] if c['prediction_cell'] not in omitted and c['reference_cell'] not in omitted]
        with self.assertRaisesRegex(ValueError,'omitted cells'):
            mark_all(inv,reply)

    def test_prompt_requires_exact_row_field_lookup_and_opaque_ids(self):
        self.assertIn('row=prediction_row, field=field_name', PROMPT)
        self.assertIn('row=reference_row, field=the same field_name', PROMPT)
        self.assertIn('Never calculate c-prefixed IDs by arithmetic', PROMPT)

    def test_cross_field_cell_pair_is_rejected_despite_complete_id_coverage(self):
        inv=self.inv();reply=reply_for(inv)
        reply['cells'][0]['reference_cell'],reply['cells'][1]['reference_cell']=reply['cells'][1]['reference_cell'],reply['cells'][0]['reference_cell']
        with self.assertRaisesRegex(ValueError,'incorrectly paired cell marking'):
            mark_all(inv,reply)

    def test_cell_pair_must_follow_declared_record_mapping(self):
        database=copy.deepcopy(GOLD)
        database['sample'].append({'id':'S2','label':'B','value':70,'optional':None})
        inv=inventory(database,database,DICT,POLICY)
        pr=[r for r in inv['rows'] if r['side']=='prediction']
        gr=[r for r in inv['rows'] if r['side']=='reference']
        declared=reply_for(inv,[(pr[0],gr[1]),(pr[1],gr[0])])
        inconsistent=reply_for(inv,[(pr[0],gr[0]),(pr[1],gr[1])])
        declared['cells']=inconsistent['cells']
        with self.assertRaisesRegex(ValueError,'incorrectly paired cell marking'):
            mark_all(inv,declared)

    def test_prompt_binds_roles_to_each_cell_and_table(self):
        self.assertIn('Role binding is per inventory cell and its table', PROMPT)
        self.assertIn('same field name can have different declared roles', PROMPT)
        self.assertIn('sample.sample_id cell declared identifier remains', PROMPT)

    def cross_table_role_inventory(self):
        dictionary={'sample':{'identifier':'sample_id','fields':[{'key':'sample_id'},{'key':'label'}]},
                    'condition':{'identifier':'condition_id','fields':[{'key':'condition_id'},{'key':'sample_id'}]}}
        database={'sample':[{'sample_id':'S1','label':'A'}],
                  'condition':[{'condition_id':'C1','sample_id':'S1'}]}
        return inventory(database,database,dictionary,POLICY)

    def test_same_named_identifier_and_relationship_keep_distinct_roles(self):
        inv=self.cross_table_role_inventory();reply=reply_for(inv);result=mark_all(inv,reply)
        sample=[x for x in result['cells'] if x['prediction']['table']=='sample' and x['prediction']['field']=='sample_id'][0]
        relationship=[x for x in result['cells'] if x['prediction']['table']=='condition' and x['prediction']['field']=='sample_id'][0]
        self.assertEqual((sample['category'],sample['verdict']),('identifier','not_scored'))
        self.assertEqual((relationship['category'],relationship['verdict']),('scientific','correct'))

    def test_correct_alignment_does_not_allow_identifier_reclassification(self):
        inv=self.cross_table_role_inventory();reply=reply_for(inv)
        ids={c['id'] for c in inv['cells'] if c['table']=='sample' and c['field']=='sample_id'}
        item=next(x for x in reply['cells'] if x['prediction_cell'] in ids)
        item.update(category='scientific',verdict='correct',reason='Synthetic matching IDs align correctly.')
        with self.assertRaisesRegex(ValueError,'cannot reclassify'):mark_all(inv,reply)

    def test_incorrect_is_one_event_and_reference_denominator_is_unchanged(self):
        p=copy.deepcopy(GOLD);p['sample'][0]['value']=61
        inv=self.inv(p);result=mark_all(inv,reply_for(inv))
        self.assertEqual(result['mark_counts']['incorrect'],1)
        self.assertEqual(result['mark_counts']['missing'],0)
        self.assertEqual(result['field']['recall'],.5)
        self.assertEqual(result['field']['f1'],.5)
        self.assertEqual(result['record']['tp'],0)

    def test_missing_extra_and_zero_explicit_state_are_retained(self):
        g=copy.deepcopy(GOLD);g['sample'].append({'id':'S2','label':'B','value':0,'optional':'NR'})
        p=copy.deepcopy(g);p['sample'].reverse()
        p['sample'][0]['value']=None
        p['sample'][1].update(value=61,optional='additional science')
        p['sample'].append({'id':'S3','label':'C','value':15,'optional':None})
        inv=self.inv(p,g);pr=[r for r in inv['rows'] if r['side']=='prediction'];gr=[r for r in inv['rows'] if r['side']=='reference']
        result=mark_all(inv,reply_for(inv,[(pr[0],gr[1]),(pr[1],gr[0]),(pr[2],None)]))
        self.assertEqual(result['known_field_counts'],{'tp':3,'predicted':7,'gold':5})
        self.assertEqual(result['mark_counts']['incorrect'],1)
        self.assertEqual(result['mark_counts']['missing'],1)
        self.assertEqual(result['mark_counts']['extra'],3)
        self.assertEqual(result['field']['f1'],.5)

    def test_missing_whole_record_is_visible_cell_by_cell(self):
        inv=self.inv(None);ref=inv['rows'][0]
        result=mark_all(inv,reply_for(inv,[(None,ref)]))
        self.assertEqual(result['mark_counts']['missing'],2)
        self.assertEqual(result['field']['f1'],0)
        self.assertEqual(result['record']['gold'],1)

    def test_renamed_ids_are_not_scientific_targets(self):
        p=copy.deepcopy(GOLD);p['sample'][0]['id']='different'
        inv=self.inv(p);result=mark_all(inv,reply_for(inv))
        self.assertEqual(result['field']['f1'],1)

    def test_qwen_judgment_is_preserved_without_a_hidden_deterministic_override(self):
        p=copy.deepcopy(GOLD);p['sample'][0]['label']='Different complete wording'
        inv=self.inv(p);result=mark_all(inv,reply_for(inv,overrides={'label':'correct'}))
        self.assertEqual(result['field']['tp'],2)
        self.assertEqual(next(i for i in result['cells'] if (i['prediction'] or i['reference'])['field']=='label')['verdict'],'correct')

    def test_uncertain_is_exported_and_machine_workflow_still_finishes(self):
        inv=self.inv();reply=reply_for(inv,overrides={'label':'uncertain'})
        result=mark_all(inv,reply)
        self.assertEqual(result['score_basis'],'lower_bound_unresolved')
        self.assertEqual(result['field']['f1'],.5)
        self.assertEqual(result['unresolved_items'],1)
        self.assertEqual(result['status'],'automatic_scoring_completed')

    def test_omitted_duplicate_and_invalid_cell_pairs_are_rejected(self):
        inv=self.inv()
        for change in ('omit','duplicate','unknown','cross_field','extra_score'):
            reply=reply_for(inv)
            if change=='omit':reply['cells'].pop()
            elif change=='duplicate':reply['cells'].append(copy.deepcopy(reply['cells'][0]))
            elif change=='unknown':reply['cells'][0]['prediction_cell']='unknown'
            elif change=='cross_field':reply['cells'][0]['reference_cell']=reply['cells'][1]['reference_cell']
            else:reply['score']=100
            with self.subTest(change=change),self.assertRaises(ValueError):mark_all(inv,reply)

    def test_gold_blank_and_declared_scientific_roles_cannot_be_overridden(self):
        inv=self.inv()
        for key,change in [('optional',{'category':'scientific','verdict':'correct'}),
                           ('value',{'category':'provenance','verdict':'not_scored'})]:
            reply=reply_for(inv)
            ids={c['id'] for c in inv['cells'] if c['field']==key}
            next(c for c in reply['cells'] if c['prediction_cell'] in ids).update(change)
            with self.assertRaises(ValueError):mark_all(inv,reply)

    def test_record_coverage_and_one_to_one_identity_are_required(self):
        inv=self.inv()
        for change in ('omit','duplicate','empty'):
            reply=reply_for(inv)
            if change=='omit':reply['records']=[]
            elif change=='duplicate':reply['records']*=2
            else:reply['records'][0].update(prediction_row=None,reference_row=None)
            with self.assertRaises(ValueError):mark_all(inv,reply)

    def test_all_decimal_digits_and_original_inputs_are_preserved(self):
        g=copy.deepcopy(GOLD);g['sample'][0]['value']=Decimal('0.123456789012345678901234567890')
        original=copy.deepcopy(g);inv=self.inv(g,g)
        self.assertTrue(any(c['value_json']=='0.123456789012345678901234567890' for c in inv['cells']))
        mark_all(inv,reply_for(inv));self.assertEqual(g,original)

    def test_no_reference_repair_or_missing_reference_key_silently_becomes_blank(self):
        g=copy.deepcopy(GOLD);del g['sample'][0]['optional']
        with self.assertRaisesRegex(ValueError,'missing a declared field'):self.inv(GOLD,g)
        inv=self.inv();reply=reply_for(inv);reply['reference_issues']=[{'reference_cell':'not-real','reason':'Invented'}]
        with self.assertRaises(ValueError):mark_all(inv,reply)

    def test_out_of_scope_extra_table_is_visible_without_scientific_credit_or_penalty(self):
        p=copy.deepcopy(GOLD);p['notes']=[{'text':'An out-of-scope note.'}]
        inv=self.inv(p);pr=[r for r in inv['rows'] if r['side']=='prediction'];gr=[r for r in inv['rows'] if r['side']=='reference']
        reply=reply_for(inv,[(pr[1],gr[0]),(pr[0],None)])
        for item in reply['cells']:
            if item['reference_cell'] is None:item.update(category='out_of_scope',verdict='not_scored')
        result=mark_all(inv,reply)
        self.assertEqual(result['field']['f1'],1)
        self.assertEqual(result['record']['predicted'],1)
        self.assertEqual(len(result['cells']),5)

    def test_unknown_scientific_classification_does_not_invent_a_complete_score(self):
        p=copy.deepcopy(GOLD);p['sample'][0]['unclassified']='Possible scientific addition'
        inv=self.inv(p);reply=reply_for(inv)
        extra=next(c for c in reply['cells'] if c['reference_cell'] is None)
        extra.update(category='uncertain',verdict='uncertain')
        result=mark_all(inv,reply)
        self.assertIsNone(result['field'])
        self.assertEqual(result['score_basis'],'undefined_classification')
        self.assertEqual(result['status'],'automatic_scoring_completed')

    def test_uncertain_record_pairing_cannot_award_correct_cells(self):
        inv=self.inv();reply=reply_for(inv);reply['records'][0]['verdict']='uncertain'
        with self.assertRaises(ValueError):mark_all(inv,reply)
        for item in reply['cells']:
            if item['verdict']=='correct':item['verdict']='uncertain'
        result=mark_all(inv,reply)
        self.assertEqual(result['field']['tp'],0)
        self.assertEqual(result['score_basis'],'lower_bound_unresolved')


class WorkflowTests(unittest.TestCase):
    def fixture(self,root,stages=('i0',),prediction=GOLD,budget=None,profile=PROFILE,terminal=False):
        prepared=root/'prepared';run=root/'submission'
        write(prepared/'dictionary.json',DICT)
        write(prepared/'materials.json',{'domain':'basic','study_id':'synthetic-study'})
        (prepared/'instruction.md').write_text('Extract the synthetic preparation. Do not invent values.')
        identity=seal(prepared)
        write(run/'manifest.json',{'stages':list(stages),'tasks':[{'case_id':'SYN','prepared':str(prepared),'material_identity':identity}]})
        for stage in stages:
            if not terminal:
                write(run/'SYN'/stage/'final/database.json',prediction);seal(run/'SYN'/stage/'final')
        if terminal:write(run/'status.json',{'tasks':{'SYN':{s:'failed' for s in stages}}})
        write(root/'gold/basic/SYN/SYN.json',GOLD);write(root/'policy.json',POLICY)
        write(root/'budget.json',budget or BUDGET)
        return grading.prepare(run,root/'gold',root/'policy.json',profile,root/'budget.json',root/'plan',provisional=True)

    def backend(self,calls,mode='valid'):
        def sender(endpoint,body,headers,timeout):
            calls.append(json.loads(body))
            if mode=='timeout':raise TimeoutError()
            payload=json.loads(calls[-1]['messages'][1]['content'][0]['text'])['payload']
            reply=reply_for(payload['inventory'])
            if mode=='omit':reply['cells'].pop()
            if mode=='html':reply['cells'][0]['reason']='<script>alert(1)</script>'
            content=json.dumps(reply)
            if mode=='bad_json':content='not JSON'
            response={'model':'qwen3.8-max-0902','id':'synthetic-request',
                'choices':[{'finish_reason':'length' if mode=='truncated' else 'stop','message':{'content':content}}]}
            if mode!='missing_usage':response['usage']={'prompt_tokens':100,'completion_tokens':20}
            return 200,{},json.dumps(response).encode()
        return Backend(PROFILE,sender=sender)

    def test_complete_task_grading_finishes_without_human_files_and_recovers_offline(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);self.fixture(root,('i0','gsr','ssr'));calls=[]
            result=grading.execute(root/'plan',root/'run',backend=self.backend(calls))
            self.assertEqual(result['status'],'automatic_scoring_completed')
            self.assertEqual(result['graded_outputs'],3);self.assertEqual(len(calls),3)
            self.assertFalse((root/'run/review-template.json').exists())
            self.assertFalse(read(root/'run/completion-audit.json')['human_review_required'])
            entries=read(root/'run/status.json')['outputs']
            for entry in entries:
                report=root/'run/tasks'/entry['id']
                self.assertTrue((report/'review.html').exists());self.assertTrue((report/'cells.csv').exists())
                self.assertEqual(len(read(report/'marking.json')['result']['cells']),4)
                self.assertTrue((report/'raw-grading.txt').exists())
            self.assertNotIn('gsr',json.dumps(calls));self.assertNotIn('ssr',json.dumps(calls))
            verify(root/'run');verify_events(root/'run')
            with patch.dict('os.environ',{},clear=True),patch('socket.socket',side_effect=AssertionError('No network')):
                recovered=grading.execute(root/'plan',root/'run',offline=True,backend=self.backend(calls))
            self.assertEqual(result,recovered);self.assertEqual(len(calls),3)
            self.assertIsNone(read(root/'run/costs.json')['exact_cny'])
            for path in (root/'run').rglob('*'):
                if path.is_file():self.assertNotIn(b'synthetic-secret',path.read_bytes())

    def test_current_rules_reach_the_wire_without_superseded_rules_or_examples(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);self.fixture(root)
            policy=read(ROOT/'configs/tasks/biotracebench-scoring-v2.json')
            original=copy.deepcopy(policy)
            policy['legacy_examples']={'text':'Superseded example must never reach Qwen'}
            write(root/'current-policy.json',policy)
            prepared=grading.prepare(root/'submission',root/'gold',root/'current-policy.json',PROFILE,
                root/'budget.json',root/'current-plan',provisional=True)
            self.assertEqual(prepared['prepared_outputs'],1)
            calls=[]
            result=grading.execute(root/'current-plan',root/'run',backend=self.backend(calls))
            self.assertEqual(result['graded_outputs'],1)
            wire=calls[0];payload=json.loads(wire['messages'][1]['content'][0]['text'])['payload']
            effective=json.loads(payload['scoring_policy_json'])
            self.assertEqual(effective['field_rules']['condition.factor_value'],{'numeric':True})
            self.assertEqual(effective['field_rules']['result.result_value'],{'numeric':True})
            self.assertEqual(set(effective['unit_catalog']['families']),
                {'mass','volume','fixed_duration','pressure_pa','molar_concentration',
                 'mass_concentration','daily_exposure_duration','event_rate_spelling'})
            self.assertIn('Qwen judges complete scientific meaning',effective['text_policy'])
            self.assertIn('genuinely unresolved identities remain uncertain',effective['identity_policy'])
            for key in ('legacy_examples','judge_contract','boundary_revision','scoring_workflow',
                        'scoring_standard','identity_task_rules','bootstrap_seed','frozen'):
                self.assertNotIn(key,effective)
            for key in ('formal_freeze_requirements','status','approved','activated','frozen',
                        'case_specific_existing_permission'):
                self.assertNotIn(key,effective['unit_catalog'])
            sent=json.dumps(wire)
            for old in ('exact unless frozen aliases','Conflicts require source-grounded human adjudication',
                        'Superseded example must never reach Qwen',
                        'Include identifier/provenance/blank cells as not_scored'):
                self.assertNotIn(old,sent)
            self.assertEqual(wire['messages'][0]['content'],PROMPT)
            self.assertIn('BOTH sides lack scientific content',PROMPT)
            self.assertNotIn('judge_contract',original)
            self.assertNotIn('boundary_revision',original)
            self.assertFalse(original['frozen'])
            self.assertEqual(read(root/'current-policy.json'),policy)

    def test_superseded_unit_examples_are_rejected_instead_of_silently_forwarded(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.fixture(root)
            policy=copy.deepcopy(POLICY)
            policy['field_rules']={'sample.value':{'numeric':True,'unit_field':'optional',
                'canonical_unit':'mg','unit_scales':{'mg':'1','μg':'0.001'}}}
            write(root/'old-policy.json',policy)
            result=grading.prepare(root/'submission',root/'gold',root/'old-policy.json',PROFILE,
                root/'budget.json',root/'blocked-plan',provisional=True)
            self.assertEqual(result['prepared_outputs'],0)
            entry=read(root/'blocked-plan/plan.json')['entries'][0]
            self.assertEqual(entry['status'],'blocked_input_or_capacity')
            self.assertIn('Remove superseded field-level unit rules',entry['reason'])
            self.assertEqual(result['model_calls'],0)

    def test_current_unit_rules_are_validated_before_selecting_request_criteria(self):
        policy=read(ROOT/'configs/tasks/biotracebench-scoring-v2.json')
        policy['unit_catalog']['case_specific_existing_permission']={'B905':'Synthetic task permits an explicitly anchored exact conversion.'}
        original=copy.deepcopy(policy)
        other=grading._grading_policy(policy,'SYN',DICT)
        self.assertNotIn('case_specific_existing_permission',other['unit_catalog'])
        scoped=grading._grading_policy(policy,'B905',DICT)
        self.assertEqual(set(scoped['unit_catalog']['case_specific_existing_permission']),{'B905'})
        self.assertEqual(policy,original)
        policy['unit_catalog']['activated']=False
        with self.assertRaisesRegex(ValueError,'activated'):
            grading._grading_policy(policy,'SYN',DICT)

    def test_invalid_or_truncated_marking_is_archived_without_zero_scores_or_retry(self):
        for mode in ('omit','bad_json','truncated'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
                root=Path(temp);self.fixture(root);calls=[]
                result=grading.execute(root/'plan',root/'run',backend=self.backend(calls,mode))
                self.assertEqual(result['status'],'automatic_scoring_completed_with_errors')
                self.assertEqual(result['failed_outputs'],1);self.assertEqual(len(calls),1)
                self.assertEqual(read(root/'run/study-scores.json')[0]['conditions'],{})
                self.assertTrue(list((root/'run/attempts').glob('*/api-response.bin')))
                self.assertTrue(list((root/'run/tasks').glob('*/raw-grading.txt')))

    def test_timeout_and_missing_usage_pause_without_resending(self):
        for mode in ('timeout','missing_usage'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
                root=Path(temp);self.fixture(root);calls=[]
                with self.assertRaises(Exception):grading.execute(root/'plan',root/'run',backend=self.backend(calls,mode))
                self.assertEqual(read(root/'run/status.json')['status'],'paused')
                with self.assertRaises(Exception):grading.execute(root/'plan',root/'run',offline=True,backend=self.backend(calls))
                self.assertEqual(len(calls),1)

    def test_budget_and_request_caps_stop_before_an_extra_physical_request(self):
        for limited in ({**BUDGET,'per_request_cny':.0001},{**BUDGET,'max_requests':1}):
            with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
                root=Path(temp);self.fixture(root,('i0','gsr'),budget=limited);calls=[]
                with self.assertRaises(Exception):grading.execute(root/'plan',root/'run',backend=self.backend(calls))
                self.assertEqual(len(calls),0 if limited['per_request_cny']==.0001 else 1)

    def test_html_is_escaped_and_reports_need_no_citation_gate(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);self.fixture(root);calls=[]
            result=grading.execute(root/'plan',root/'run',backend=self.backend(calls,'html'))
            text=next((root/'run/tasks').glob('*/review.html')).read_text()
            self.assertIn('&lt;script&gt;',text);self.assertNotIn('<script>',text)
            self.assertEqual(result['graded_outputs'],1)

    def test_plan_and_run_tampering_are_rejected_offline(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);self.fixture(root);calls=[]
            grading.execute(root/'plan',root/'run',backend=self.backend(calls))
            (root/'run/review.html').write_text('tampered')
            with self.assertRaises(Exception):grading.execute(root/'plan',root/'run',offline=True,backend=self.backend(calls))
            self.assertEqual(len(calls),1)

    def test_incomplete_budget_does_not_allow_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.fixture(root,budget={'max_requests':None});calls=[]
            with self.assertRaises(ValueError):grading.execute(root/'plan',root/'run',backend=self.backend(calls))
            self.assertFalse(calls)

    def test_provisional_flag_is_explicit_and_does_not_freeze_rules(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.fixture(root)
            with self.assertRaisesRegex(ValueError,'unfrozen'):
                grading.prepare(root/'submission',root/'gold',root/'policy.json',PROFILE,root/'budget.json',root/'other')
            self.assertFalse(read(root/'policy.json')['frozen'])

    def test_crash_after_response_is_recovered_without_new_generation(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);self.fixture(root);calls=[]
            original=grading.task_report
            def crash(folder,entry,result=None):
                if result:raise RuntimeError('Synthetic crash after complete response')
                return original(folder,entry,result)
            with patch.object(grading,'task_report',side_effect=crash),self.assertRaises(RuntimeError):
                grading.execute(root/'plan',root/'run',backend=self.backend(calls))
            with patch.dict('os.environ',{},clear=True):
                result=grading.execute(root/'plan',root/'run',offline=True,backend=self.backend(calls))
            self.assertEqual(result['graded_outputs'],1);self.assertEqual(len(calls),1)

    def test_capacity_block_is_retained_without_truncation_or_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            from model_api import load_profile
            profile=load_profile(PROFILE).describe();profile['max_input_bytes']=100
            write(root/'small-profile.json',profile)
            result=self.fixture(root,profile=root/'small-profile.json')
            self.assertEqual(result['prepared_outputs'],0)
            self.assertEqual(result['blocked_or_waiting'],1)
            self.assertIn('no truncation',read(root/'plan/plan.json')['entries'][0]['reason'])

    def test_nonterminal_missing_output_is_pending_not_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.fixture(root)
            manifest=read(root/'submission/manifest.json');manifest['stages'].append('not_started')
            write(root/'submission/manifest.json',manifest)
            grading.prepare(root/'submission',root/'gold',root/'policy.json',PROFILE,root/'budget.json',root/'plan2',provisional=True)
            entries=read(root/'plan2/plan.json')['entries']
            self.assertEqual(entries[1]['status'],'waiting_for_input')

    def test_terminal_no_output_is_graded_as_missing_without_human_unlock(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);self.fixture(root,terminal=True);calls=[]
            result=grading.execute(root/'plan',root/'run',backend=self.backend(calls))
            self.assertEqual(result['status'],'automatic_scoring_completed')
            mark=next((root/'run/tasks').glob('*/marking.json'))
            scored=read(mark)['result']
            self.assertEqual(scored['mark_counts']['missing'],2)
            for level in ('field','record'):
                for metric in ('precision','recall','f1'):self.assertEqual(scored[level][metric],0)

    def test_unreadable_submission_remains_a_failed_input_not_a_manufactured_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);result=self.fixture(root,prediction=None)
            self.assertEqual(result['prepared_outputs'],0)
            self.assertIn('Unreadable submission',read(root/'plan/plan.json')['entries'][0]['reason'])

    def test_used_prepared_metadata_tampering_is_blocked_without_reading_materials(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.fixture(root)
            (root/'prepared/instruction.md').write_text('changed')
            result=grading.prepare(root/'submission',root/'gold',root/'policy.json',PROFILE,root/'budget.json',root/'plan2',provisional=True)
            self.assertEqual(result['prepared_outputs'],0)
            self.assertIn('identity changed',read(root/'plan2/plan.json')['entries'][0]['reason'])

    def test_source_and_input_directories_cannot_be_used_for_private_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.fixture(root)
            for out in (ROOT/'private-grading',root/'prepared/invalid',root/'submission/invalid'):
                with self.assertRaises(ValueError):
                    grading.prepare(root/'submission',root/'gold',root/'policy.json',PROFILE,root/'budget.json',out,provisional=True)

    def test_cli_exposes_prepare_run_recover_without_human_finalize(self):
        import contextlib,io
        from biotracebench_scoring.__main__ import main
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.fixture(root)
            with contextlib.redirect_stdout(io.StringIO()):
                code=main(['grade-prepare','--run',str(root/'submission'),'--gold-root',str(root/'gold'),
                     '--policy',str(root/'policy.json'),'--profile',str(PROFILE),'--budget',str(root/'budget.json'),
                     '--out',str(root/'cli-plan'),'--provisional'])
            self.assertEqual(code,0);verify(root/'cli-plan')


if __name__=='__main__':unittest.main()
