"""Offline two-round completion gates with synthetic submissions only."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from argparse import Namespace
from model_conversation.archive import read, write, seal, digest
from biotracebench_scoring.workflow import score_run
from biotracebench_scoring import completion, scoring_judge as judge
from test_biotracebench_scoring_items import GOLD, DICT, POLICY
import test_biotracebench_scoring_judge as fixtures


class CompletionTests(unittest.TestCase):
    def build(self, root, semantic=False, states=None, corrupt=False, unreadable=False):
        stages=['i0','gsr','ssr']
        gold=copy.deepcopy(GOLD)
        prediction=copy.deepcopy(gold)
        if semantic:
            gold['result'][0]['result_value']='not estimable'
            prediction['result'][0]['result_value']='NE'
        prepared=root/'prepared'
        write(prepared/'dictionary.json', DICT)
        write(prepared/'materials.json', {'domain':'clinical','study_id':'synthetic-study'})
        material=seal(prepared)
        run=root/'run'
        write(run/'manifest.json', {'protocol':'biotracebench-run-2','stages':stages,
              'tasks':[{'case_id':'SYN','prepared':str(prepared),'material_identity':material}]})
        for stage in stages:
            if not states or stage not in states:
                write(run/'SYN'/stage/'final/database.json', None if unreadable and stage=='i0' else prediction)
                seal(run/'SYN'/stage/'final')
        if states:write(run/'status.json',{'tasks':{'SYN':states}})
        if corrupt:write(run/'SYN/i0/final/database.json',{})
        write(root/'gold/clinical/SYN/SYN.json',gold)
        write(root/'policy.json',POLICY)
        score_run(Namespace(run=str(run),gold_root=str(root/'gold'),policy=str(root/'policy.json'),
                            out=str(root/'scores'),adjudications=None,with_analysis=False))
        return root/'scores'

    def reviews(self, root, approve=True):
        reviews=read(root/'check/review-template.json')
        for item in reviews:
            item.update(approve=approve,reviewer='synthetic-human',reviewed_at='2026-10-28',basis='Checked all evaluable fields and diagnostics.')
        write(root/'reviews.json',reviews)
        return reviews

    def test_correct_scores_require_human_round_then_complete_offline(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.build(root)
            self.assertEqual(read(root/'scores/scoring-overview.json')['status'],'awaiting_human_review')
            completion.prepare(root/'scores',root/'check')
            packets=read(root/'check/review-packets.json')
            self.assertNotIn('"condition"',str(packets))
            self.reviews(root)
            with patch('socket.socket',side_effect=AssertionError('No network')):
                result=completion.finalize(root/'check',root/'reviews.json',root/'completed')
            self.assertEqual(result['status'],'completed')
            self.assertEqual(result['counts']['completed'],3)
            self.assertTrue(all(r['field']['f1']==1 for r in read(root/'completed/study-scores.json')[0]['conditions'].values()))
            self.assertEqual(read(root/'completed/completion-audit.json')['model_calls'],0)

    def test_terminal_failure_counts_zero_but_running_task_remains_pending(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.build(root,states={'i0':'failed','gsr':'running'})
            completion.prepare(root/'scores',root/'check');self.reviews(root)
            result=completion.finalize(root/'check',root/'reviews.json',root/'done')
            self.assertEqual(result['counts']['pending'],1)
            self.assertEqual(result['completed_zero_output'],1)
            self.assertNotEqual(result['status'],'completed')
            initial=read(root/'done/study-scores.json')[0]['conditions']['i0']
            for level in ('field','record'):
                for metric in ('precision','recall','f1'):self.assertEqual(initial[level][metric],0)

    def test_corrupted_archive_is_blocked_not_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.build(root,corrupt=True)
            completion.prepare(root/'scores',root/'check');self.reviews(root)
            result=completion.finalize(root/'check',root/'reviews.json',root/'done')
            self.assertEqual(result['status'],'blocked')
            self.assertEqual(result['counts']['blocked'],1)
            self.assertNotIn('i0',read(root/'done/study-scores.json')[0]['conditions'])

    def test_unreadable_output_requires_explicit_no_usable_content_confirmation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.build(root,unreadable=True)
            completion.prepare(root/'scores',root/'check');reviews=self.reviews(root)
            result=completion.finalize(root/'check',root/'reviews.json',root/'pending')
            self.assertEqual(result['counts']['awaiting_human_review'],1)
            routes=read(root/'check/private-routes.json')
            for review in reviews:
                if routes[review['id']]['condition']=='i0':review['no_usable_output']=True
            write(root/'reviews.json',reviews)
            result=completion.finalize(root/'check',root/'reviews.json',root/'done')
            self.assertEqual(result['status'],'completed')
            self.assertEqual(result['completed_zero_output'],1)

    def test_qwen_batch_first_then_one_human_round(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);self.build(root,semantic=True)
            with self.assertRaisesRegex(ValueError,'Qwen proposals'):
                completion.prepare(root/'scores',root/'early')
            contexts={}
            for score in read(root/'scores/study-scores.json')[0]['conditions'].values():
                for q in score['adjudication_queue']:
                    if q['kind']=='text_equivalence':
                        contexts[score['context_id']+':'+q['id']]={'task_definition':'Synthetic endpoint',
                            'field_rule':'NE means not estimable.',
                            'sources':[{'id':'e1','source':'synthetic.txt','locator':'line 1','text':'NE: not estimable.'}]}
            write(root/'evidence.json',contexts)
            write(root/'budget.json',{'max_requests':3,'per_request_cny':1,'total_cny':3,
              'max_input_cny_per_million':1,'max_output_cny_per_million':1,'price_source':'synthetic','price_verified_at':'2026-10-28'})
            judge.prepare(root/'scores/study-scores.json',root/'evidence.json',fixtures.PROFILE,root/'budget.json',root/'judge-plan')
            calls=[]
            judge.execute(root/'judge-plan',root/'judge-run',backend=fixtures.JudgeTests().transport(calls))
            self.assertEqual(len(calls),1)  # Same context shares one proposal.
            completion.prepare(root/'scores',root/'check',root/'judge-plan',root/'judge-run')
            reviews=self.reviews(root)
            # Blanket approval cannot replace unresolved semantic decisions.
            pending=completion.finalize(root/'check',root/'reviews.json',root/'pending')
            self.assertNotEqual(pending['status'],'completed')
            for review in reviews:
                for item in review['semantic_reviews']:item.update(equal=True,basis='Human checked the definition.')
            write(root/'reviews.json',reviews)
            result=completion.finalize(root/'check',root/'reviews.json',root/'done')
            self.assertEqual(result['status'],'completed')
            self.assertEqual(len(calls),1)

    def test_tampering_and_missing_reviews_cannot_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.build(root)
            completion.prepare(root/'scores',root/'check')
            write(root/'reviews.json',[])
            result=completion.finalize(root/'check',root/'reviews.json',root/'pending')
            self.assertEqual(result['counts']['awaiting_human_review'],3)
            self.reviews(root)
            write(root/'scores/study-scores.json',[])
            with self.assertRaises(RuntimeError):
                completion.finalize(root/'check',root/'reviews.json',root/'tampered')


if __name__=='__main__':unittest.main()
