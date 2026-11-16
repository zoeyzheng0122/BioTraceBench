import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from model_conversation.archive import write, read, sha
from biotracebench_scoring import native_reference_versions as versions
from biotracebench_scoring.task_grading_contract import inventory
from test_reference_identity_bridge import ReferenceIdentityBridgeTests
from test_native_codex import DICT, POLICY


class ReferencePlanTests(unittest.TestCase):
    def test_replace_reference_preserves_submitted_values_and_diagnostics(self):
        prediction={'sample':[{'id':'P1','label':'Arm A','value':5,'optional':None}]}
        old={'sample':[{'id':'S1','label':'Arm A','value':5,'optional':None}]}
        revised={'sample':[{'id':'S1','label':'Arm A','value':6,'optional':None},
                           {'id':'S2','label':'Arm B','value':3,'optional':None}]}
        original=inventory(prediction,old,DICT,POLICY)
        original['diagnostics'].append({'error':'synthetic-original'})
        value=next(c for c in original['cells'] if c['side']=='prediction' and c['field']=='value')
        value['value_json']='5.00'
        ref_only=inventory(None,revised,DICT,POLICY)
        actual=versions.replace_reference_inventory(original,ref_only)
        self.assertEqual([x for x in actual['cells'] if x['side']=='prediction'],
                         [x for x in original['cells'] if x['side']=='prediction'])
        self.assertEqual(actual['diagnostics'],original['diagnostics'])
        self.assertEqual([r['id'] for r in actual['rows']],['p0','r1','r2'])
        ref_only['diagnostics'].append({'error':'invalid'})
        with self.assertRaisesRegex(ValueError,'must not contain'):
            versions.replace_reference_inventory(original,ref_only)

    def fixture(self, root):
        old_inv,new_inv,sources,bridge=ReferenceIdentityBridgeTests().fixture()
        def route(job,sha):
            return {'case':'SYNTHETIC','model':'model','condition':'i0','domain':'basic',
                    'zero_cause':None,'job_id':job,'original_packet_sha256':sha}
        old_route,new_route=route('old','old-sha'),route('new','new-sha')
        old_plan,new_plan={'identity':'old-plan'},{'identity':'new-plan'}
        old_fields=[{'id':'field','required_assertions':['old']}]
        new_fields=[{'id':'field','required_assertions':['new']}]
        old_context={'sources':sources,'task_definition':'unchanged','task_policy':{'fields':old_fields}}
        new_context={'sources':sources,'task_definition':'unchanged','task_policy':{'fields':new_fields}}
        manifest={'format':versions.FORMAT,'case':'SYNTHETIC','base_plan_identity':'old-plan',
                  'revised_plan_identity':'new-plan','bridges':[{'old_job':'old','new_job':'new',
                    'old_packet_sha256':'old-sha','new_packet_sha256':'new-sha','bridge':bridge}],
                  'policy_changes':[{'path':'/fields','before':old_fields,'after':new_fields,
                    'source_id':'s','quote':'Arm A has value 6.','reason':'Source correction.'}]}
        path=root/'manifest.json';write(path,manifest)
        def routes(plan,case):
            return (old_plan,[old_route],[old_route]) if plan=='base' else (new_plan,[new_route],[new_route])
        def inputs(plan,job,frozen):
            return ({'inventory':old_inv,'local_terminal':False},old_context) if plan=='base' else (
                    {'inventory':new_inv,'local_terminal':False},new_context)
        return path,manifest,routes,inputs

    def test_full_i0_reference_plan_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            path,m,r,i=self.fixture(Path(temp))
            with patch.object(versions,'_case_routes',side_effect=r),patch.object(versions.native,'_inputs',side_effect=i):
                result=versions.verify_reference_version('base','revised',path)
            self.assertEqual((result['condition'],result['positions'],result['policy_changes']),('i0',1,1))

    def test_undeclared_policy_and_missing_bridge_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path,m,r,i=self.fixture(Path(temp));m['policy_changes']=[];write(path,m)
            with patch.object(versions,'_case_routes',side_effect=r),patch.object(versions.native,'_inputs',side_effect=i):
                with self.assertRaisesRegex(ValueError,'declared exactly'):
                    versions.verify_reference_version('base','revised',path)
                m['bridges']=[];write(path,m)
                with self.assertRaisesRegex(ValueError,'Missing source-authored'):
                    versions.verify_reference_version('base','revised',path)

    def test_newly_blank_fields_require_an_explicit_optional_context_decision(self):
        before={'fields':[{'id':'x','required_assertions':[{'id':'required'}]}]}
        after={'fields':[{'id':'x','required_assertions':[]}]}
        with self.assertRaisesRegex(ValueError,'optional-context decision'):
            versions._validate_blank_transitions(before,after)
        after['fields'][0]['optional_context_allowed']=True
        versions._validate_blank_transitions(before,after)
    def test_modified_source_and_wrong_packet_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path,m,r,i=self.fixture(Path(temp));m['bridges'][0]['new_packet_sha256']='wrong';write(path,m)
            with patch.object(versions,'_case_routes',side_effect=r),patch.object(versions.native,'_inputs',side_effect=i):
                with self.assertRaisesRegex(ValueError,'packet provenance'):
                    versions.verify_reference_version('base','revised',path)
            path,m,r,i=self.fixture(Path(temp))
            def changed(plan,job,frozen):
                packet,ctx=i(plan,job,frozen);ctx=copy.deepcopy(ctx)
                if plan=='revised':ctx['task_definition']='changed'
                return packet,ctx
            with patch.object(versions,'_case_routes',side_effect=r),patch.object(versions.native,'_inputs',side_effect=changed):
                with self.assertRaisesRegex(ValueError,'frozen sources'):
                    versions.verify_reference_version('base','revised',path)

    def test_other_stage_or_missing_i0_position_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path,m,r,i=self.fixture(Path(temp))
            def wrong_stage(plan,case):
                frozen,selected,all_routes=r(plan,case)
                if plan=='revised':
                    selected=copy.deepcopy(selected);selected[0]['condition']='gsr';all_routes=selected
                return frozen,selected,all_routes
            with patch.object(versions,'_case_routes',side_effect=wrong_stage):
                with self.assertRaisesRegex(ValueError,'only.*I0'):
                    versions.verify_reference_version('base','revised',path)
            def missing(plan,case):
                frozen,selected,all_routes=r(plan,case)
                if plan=='base':
                    extra=copy.deepcopy(selected[0]);extra['model']='other';selected=selected+[extra]
                return frozen,selected,all_routes
            with patch.object(versions,'_case_routes',side_effect=missing):
                with self.assertRaisesRegex(ValueError,'every I0'):
                    versions.verify_reference_version('base','revised',path)
            def duplicate(plan,case):
                frozen,selected,all_routes=r(plan,case)
                if plan=='revised':selected=selected+copy.deepcopy(selected);all_routes=selected
                return frozen,selected,all_routes
            with patch.object(versions,'_case_routes',side_effect=duplicate):
                with self.assertRaisesRegex(ValueError,'every I0'):
                    versions.verify_reference_version('base','revised',path)

    def test_pending_revised_reference_never_falls_back_to_old_score(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);manifest=root/'manifest.json';write(manifest,{'synthetic':True})
            identity={'case':'SYNTHETIC','model':'m','condition':'i0','domain':'basic'}
            old={'identity':identity,'status':'complete','score':{'field':1},'input_identity':'old'}
            other={'identity':{**identity,'condition':'gsr'},'status':'complete','score':{'field':1}}
            new={'identity':identity,'status':'awaiting_first_pass','score':None,'input_identity':'new'}
            base=root/'base.json';child=root/'child.json'
            for path,positions in ((base,[old,other]),(child,[new])):
                write(path,{'positions':positions,'source_sha256':{},'validation_status':'exact_replay_passed'})
            def export(plan,out,**kwargs):
                path=base if plan=='base' else child
                return {'path':str(path),'sha256':sha(path)}
            proof={'case':'SYNTHETIC','condition':'i0','positions':1}
            revision={'plan':'revised','manifest':str(manifest)}
            with patch.object(versions,'verify_reference_version',return_value=proof),patch.object(versions,'export_view',side_effect=export),patch.object(versions,'export_i0',side_effect=export):
                result=versions.compose_reference_i0('base',[revision],root/'out',required_revised_cases=['SYNTHETIC'])
                rows=read(result['path'])['positions']
                self.assertEqual(len(rows),1)
                self.assertIsNone(rows[0]['score'])
                self.assertEqual(rows[0]['superseded_version']['score'],{'field':1})
                with self.assertRaisesRegex(ValueError,'incomplete'):
                    versions.compose_reference_i0('base',[revision],root/'complete',required_revised_cases=['SYNTHETIC'],require_complete=True)
                with self.assertRaisesRegex(ValueError,'Every expected revised case'):
                    versions.compose_reference_i0('base',[revision],root/'missing',required_revised_cases=['SYNTHETIC','OTHER'])
