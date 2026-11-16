"""Total-output reservations on synthetic provider responses; no live API calls."""
import copy
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from model_api import Backend, load_profile
from model_conversation.archive import read, write, seal, verify
from biotracebench_scoring import task_grading as grading
from biotracebench_scoring.task_grading_budget import output_control, usage_breakdown, TOKEN_MARGIN
import test_biotracebench_task_grading as fixtures


class GradingBudgetTests(unittest.TestCase):
    def fixture(self,root,**options):
        return fixtures.WorkflowTests().fixture(root,**options)

    def backend(self,calls,usage=None,finish='stop',empty=False):
        def sender(endpoint,body,headers,timeout):
            wire=json.loads(body);calls.append(wire)
            packet=json.loads(wire['messages'][1]['content'][0]['text'])['payload']
            text='' if empty else json.dumps(fixtures.reply_for(packet['inventory']))
            response={'id':'synthetic-budget-response','model':'qwen3.8-max-0902',
                'usage':usage if usage is not None else {'prompt_tokens':100,'completion_tokens':20},
                'choices':[{'finish_reason':finish,'message':{'content':text}}]}
            return 200,{},json.dumps(response).encode()
        return Backend(fixtures.PROFILE,sender=sender)

    def test_wire_uses_total_cap_without_changing_the_vendor_template(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);self.fixture(root);calls=[]
            grading.execute(root/'plan',root/'run',backend=self.backend(calls))
            self.assertNotIn('max_tokens',calls[0])
            self.assertEqual(calls[0]['max_completion_tokens'],8192)
            self.assertTrue(calls[0]['enable_thinking'])
            control=read(root/'plan/plan.json')['output_control']
            self.assertEqual(control['reserved_output_tokens'],8202)
            self.assertEqual(control['output_scope'],'reasoning_plus_final')
            self.assertEqual(read(fixtures.ROOT/'configs/models/vendors/qwen.json')['output_token_field'],'max_tokens')

    def test_old_answer_only_profile_is_rejected_before_a_plan_or_request(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);profile=load_profile(fixtures.PROFILE).describe()
            profile['output_token_field']='max_tokens';write(root/'old-profile.json',profile)
            with self.assertRaisesRegex(ValueError,'requires max_completion_tokens'):
                self.fixture(root,profile=root/'old-profile.json')
            self.assertFalse((root/'plan').exists())

    def test_context_margin_is_checked_even_when_the_base_api_profile_fits(self):
        p=load_profile(fixtures.PROFILE).describe()
        p['max_input_bytes']=p['context_tokens']-p['max_output_tokens']
        load_profile(p)  # Base API does not know this provider-specific margin.
        with self.assertRaisesRegex(ValueError,'provider token margin exceeds context'):
            output_control(p)
        p['max_input_bytes']-=TOKEN_MARGIN
        self.assertEqual(output_control(p)['context_input_bound_bytes']+8202,p['context_tokens'])

    def test_reservation_uses_the_same_total_cap_plus_margin_at_both_rates(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);budget={**fixtures.BUDGET,'max_input_cny_per_million':'2',
                                  'max_output_cny_per_million':'5'}
            self.fixture(root,budget=budget);plan=read(root/'plan/plan.json')
            expected=(Decimal(65536)*2+Decimal(8192+10)*5)/1000000
            self.assertEqual(grading._budget(plan)[-1],expected)
            self.assertFalse((root/'run').exists())

    def test_single_budget_including_all_but_half_the_margin_stops_before_send(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);self.fixture(root,budget={**fixtures.BUDGET,'per_request_cny':'0.073733'});calls=[]
            with self.assertRaisesRegex(RuntimeError,'budget reached'):
                grading.execute(root/'plan',root/'run',backend=self.backend(calls))
            self.assertEqual(calls,[])
            self.assertFalse((root/'run/attempts').exists())

    def test_total_budget_retains_first_cost_and_stops_before_next_request(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);self.fixture(root,stages=('i0','gsr'),
                budget={**fixtures.BUDGET,'total_cny':'0.073853'});calls=[]
            with self.assertRaisesRegex(RuntimeError,'budget reached'):
                grading.execute(root/'plan',root/'run',backend=self.backend(calls))
            self.assertEqual(len(calls),1)
            self.assertEqual(Decimal(read(root/'run/costs.json')['total_upper_cny']),Decimal('0.00012'))
            self.assertEqual(read(root/'run/status.json')['status'],'paused')

    def test_exact_single_and_total_reservation_boundary_is_allowed(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);self.fixture(root,budget={**fixtures.BUDGET,
                'per_request_cny':'0.073738','total_cny':'0.073738'});calls=[]
            result=grading.execute(root/'plan',root/'run',backend=self.backend(calls))
            self.assertEqual(result['graded_outputs'],1);self.assertEqual(len(calls),1)

    def test_reasoning_is_logged_as_a_subset_and_never_charged_twice(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);self.fixture(root);calls=[]
            usage={'prompt_tokens':100,'completion_tokens':100,
                   'completion_tokens_details':{'reasoning_tokens':70,'text_tokens':100}}
            grading.execute(root/'plan',root/'run',backend=self.backend(calls,usage))
            cost=read(root/'run/costs.json')['requests'][0]
            self.assertEqual(Decimal(cost['upper_cny']),Decimal('0.0002'))
            self.assertEqual(cost['usage_breakdown']['reasoning_tokens'],70)
            self.assertEqual(cost['usage_breakdown']['final_text_tokens'],30)
            self.assertEqual(cost['usage_breakdown']['output_tokens_total'],100)
            self.assertEqual(cost['raw_usage'],usage)
            self.assertIsNone(cost['exact_cny']);self.assertIsNone(cost['billed_actual'])
            self.assertEqual(read(next((root/'run/attempts').glob('*/usage-breakdown.json'))),cost['usage_breakdown'])

    def test_missing_optional_details_do_not_invent_zero_or_block_known_total_costs(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);self.fixture(root,stages=('i0','gsr'));calls=[]
            result=grading.execute(root/'plan',root/'run',backend=self.backend(calls))
            self.assertEqual(result['graded_outputs'],2)
            for item in read(root/'run/costs.json')['requests']:
                self.assertIsNone(item['usage_breakdown']['reasoning_tokens'])
                self.assertIsNone(item['usage_breakdown']['final_text_tokens'])
                self.assertEqual(item['usage_breakdown']['detail_status'],'not_reported')

    def test_invalid_optional_details_are_preserved_without_changing_billable_totals(self):
        usage={'input_tokens':10,'output_tokens':20}
        raw={'completion_tokens':20,'completion_tokens_details':{'reasoning_tokens':30,'text_tokens':False}}
        original=copy.deepcopy(raw);details=usage_breakdown(usage,raw)
        self.assertEqual(raw,original)
        self.assertEqual(details['output_tokens_total'],20)
        self.assertIsNone(details['reasoning_tokens']);self.assertIsNone(details['final_text_tokens'])
        self.assertEqual(details['detail_status'],'invalid_preserved')
        details=usage_breakdown(usage,{'completion_tokens_details':[]})
        self.assertEqual(details['output_tokens_total'],20)
        self.assertEqual(details['detail_status'],'invalid_preserved')

    def test_missing_total_usage_keeps_raw_response_and_reservation_unknown(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);self.fixture(root);calls=[]
            usage={'prompt_tokens':100,'completion_tokens_details':{'reasoning_tokens':15}}
            with self.assertRaisesRegex(ValueError,'usage missing'):
                grading.execute(root/'plan',root/'run',backend=self.backend(calls,usage))
            unknown=read(root/'run/unknown-cost.json')
            self.assertIsNone(unknown['exact_cny']);self.assertEqual(unknown['consumption'],'unknown')
            self.assertEqual(unknown['output_control']['reserved_output_tokens'],8202)
            self.assertTrue(list((root/'run/attempts').glob('*/api-response.bin')))
            with self.assertRaises(ValueError):
                grading.execute(root/'plan',root/'run',offline=True,backend=self.backend(calls))
            self.assertEqual(len(calls),1)

    def test_output_margin_boundary_is_enforced_independently_of_cost_headroom(self):
        for output,accepted in ((8202,True),(8203,False)):
            with self.subTest(output=output),tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
                root=Path(temp);self.fixture(root);calls=[]
                usage={'prompt_tokens':100,'completion_tokens':output}
                if accepted:
                    self.assertEqual(grading.execute(root/'plan',root/'run',backend=self.backend(calls,usage))['graded_outputs'],1)
                else:
                    with self.assertRaisesRegex(ValueError,'token bounds'):
                        grading.execute(root/'plan',root/'run',backend=self.backend(calls,usage))
                    self.assertEqual(read(root/'run/status.json')['outputs'][0]['status'],'paused_usage_exceeded_token_bounds')
                    with self.assertRaisesRegex(ValueError,'token bounds'):
                        grading.execute(root/'plan',root/'run',offline=True,backend=self.backend(calls))
                self.assertEqual(len(calls),1)
                self.assertEqual(read(root/'run/costs.json')['requests'][0]['usage']['output_tokens'],output)

    def test_input_token_bound_is_checked_without_relying_on_total_fee_overrun(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);self.fixture(root);calls=[]
            with self.assertRaisesRegex(ValueError,'token bounds'):
                grading.execute(root/'plan',root/'run',backend=self.backend(calls,{'prompt_tokens':65537,'completion_tokens':0}))
            self.assertEqual(len(calls),1)
            self.assertTrue((root/'run/costs.json').exists())

    def test_truncated_reasoning_only_response_retains_cost_without_a_score_or_retry(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);self.fixture(root);calls=[]
            usage={'prompt_tokens':100,'completion_tokens':8192,
                   'completion_tokens_details':{'reasoning_tokens':8192,'text_tokens':8192}}
            result=grading.execute(root/'plan',root/'run',backend=self.backend(calls,usage,finish='length',empty=True))
            self.assertEqual(result['status'],'automatic_scoring_completed_with_errors')
            self.assertEqual(read(root/'run/study-scores.json')[0]['conditions'],{})
            self.assertEqual(read(root/'run/costs.json')['requests'][0]['usage_breakdown']['final_text_tokens'],0)
            self.assertTrue(list((root/'run/tasks').glob('*/raw-grading.txt')))
            self.assertEqual(len(calls),1)

    def test_crash_recovery_reuses_original_total_usage_and_cost_without_credentials(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);self.fixture(root);calls=[]
            usage={'prompt_tokens':100,'completion_tokens':100,'completion_tokens_details':{'reasoning_tokens':70}}
            original=grading.task_report
            def crash(folder,entry,result=None):
                if result:raise RuntimeError('Synthetic crash after complete marking')
                return original(folder,entry,result)
            with patch.object(grading,'task_report',side_effect=crash),self.assertRaises(RuntimeError):
                grading.execute(root/'plan',root/'run',backend=self.backend(calls,usage))
            costs=read(root/'run/costs.json')
            with patch.dict('os.environ',{},clear=True):
                result=grading.execute(root/'plan',root/'run',offline=True,backend=self.backend(calls))
            self.assertEqual(result['graded_outputs'],1);self.assertEqual(len(calls),1)
            self.assertEqual(read(root/'run/costs.json'),costs);verify(root/'run')

    def test_output_control_mismatch_cannot_be_reinterpreted_as_a_new_paid_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.fixture(root);calls=[]
            plan=read(root/'plan/plan.json');plan['output_control']['provider_margin_tokens']=0
            write(root/'plan/plan.json',plan);seal(root/'plan')
            with self.assertRaisesRegex(ValueError,'output-control identity changed'):
                grading.execute(root/'plan',root/'run',backend=self.backend(calls))
            self.assertEqual(calls,[]);self.assertFalse((root/'run').exists())


if __name__=='__main__':unittest.main()
