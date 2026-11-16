"""Received-but-defective I0 vs incomplete transport; synthetic and network-free."""
import copy
import json
import unittest
from pathlib import Path

import test_biotracebench_conditions as fixtures
from test_biotracebench import ANSWER
from biotracebench.common import encoded, read, write, sha, digest
from biotracebench.materials import prepare
from biotracebench.runner import INITIAL_REVIEW_POLICY, freeze
from biotracebench.export import run_report


class ReviewStartTests(unittest.TestCase):
    setUp = fixtures.ConditionTests.setUp
    tearDown = fixtures.ConditionTests.tearDown
    manifest = fixtures.ConditionTests.manifest
    execute = fixtures.ConditionTests.execute
    response = fixtures.ConditionTests.response
    send = fixtures.ConditionTests.send

    def first_response(self, text, finish='stop'):
        def send(*args):
            if 'estimate' in args[0]:
                return self.provider(*args)
            if self.provider.completions == 0:
                self.wire.append(json.loads(args[1]))
                return self.response(text, finish=finish)
            return self.send(*args)
        return send

    def partial(self):
        value = copy.deepcopy(ANSWER)
        value.pop('condition')
        return value

    def raw(self, database):
        return json.dumps({'database': database, 'annotations': []}, ensure_ascii=False)

    def assert_same_unrepaired_origin(self, raw):
        initial = self.out/'B001/i0/final'
        self.assertEqual((initial/'raw-answer.txt').read_text(), raw)
        g = read(self.out/'B001/gsr/branch.json')
        s = read(self.out/'B001/ssr/branch.json')
        self.assertEqual(g['i0_history_sha256'], s['i0_history_sha256'])
        self.assertEqual(g['parent_final_identity'], s['parent_final_identity'])
        self.assertEqual(g['initial_submission_status'], 'invalid_output')
        self.assertFalse(g['initial_database_schema_valid'])
        self.assertEqual(self.wire[1]['messages'][:-1], self.wire[2]['messages'][:-1])
        initial_message = self.wire[1]['messages'][-2]
        self.assertEqual(initial_message['content'], raw)
        archived = read(self.out/'B001/i0/calls/00000/completion/response.bin')['choices'][0]['message']
        self.assertEqual(initial_message, archived)
        self.assertIn('reasoning_content', initial_message)
        checkpoint = read(initial.parent/'initial-review-start.json')
        self.assertTrue(checkpoint['eligible_for_review'])
        self.assertFalse(checkpoint['host_repaired'])
        self.assertEqual(checkpoint['extra_model_calls'], 0)
        self.assertEqual(checkpoint['raw_answer_sha256'], sha(initial/'raw-answer.txt'))
        self.assertEqual(checkpoint['initial_history_sha256'], g['i0_history_sha256'])
        return initial

    def test_missing_table_is_retained_and_both_independent_reviews_run(self):
        manifest = self.manifest()
        self.assertEqual(manifest['initial_review_policy'], INITIAL_REVIEW_POLICY)
        raw = self.raw(self.partial())
        result = self.execute(self.first_response(raw))
        self.assertIsNone(result['failure'])
        self.assertEqual(result['tasks']['B001'], {'i0':'invalid_output','gsr':'completed','ssr':'completed'})
        self.assertEqual(self.provider.completions, 3)
        initial = self.assert_same_unrepaired_origin(raw)
        self.assertEqual(read(initial/'database.json'), self.partial())
        self.assertNotIn('condition', read(initial/'database.json'))
        self.assertEqual(read(initial/'output-assessment.json')['scientific_correctness'], 'not_evaluated')
        self.assertTrue(read(initial/'diagnostics.json'))
        self.assertEqual(read(self.out/'management/overview.json')['forks']['B001']['common_start'], 'verified')
        self.assertEqual(len(read(self.out/'costs.json')['calls']), 3)

    def test_missing_field_under_strict_schema_is_not_filled_by_host(self):
        self.manifest(strict=True)
        partial = copy.deepcopy(ANSWER); partial['sample'][0].pop('species')
        raw = self.raw(partial)
        result = self.execute(self.first_response(raw))
        self.assertIsNone(result['failure'])
        initial = self.assert_same_unrepaired_origin(raw)
        self.assertNotIn('species', read(initial/'database.json')['sample'][0])
        self.assertFalse(read(initial/'output-assessment.json')['native_output_schema_valid'])
        self.assertEqual(self.provider.completions, 3)

    def test_malformed_json_with_normal_finish_is_preserved_in_native_history(self):
        self.manifest()
        raw = '{"database":{"sample":['
        result = self.execute(self.first_response(raw))
        self.assertIsNone(result['failure'])
        initial = self.assert_same_unrepaired_origin(raw)
        self.assertIsNone(read(initial/'database.json'))
        self.assertFalse(read(initial/'output-assessment.json')['json_parseable'])
        self.assertEqual(self.provider.completions, 3)

    def test_all_three_defective_submissions_stay_invalid_without_repair_calls(self):
        self.manifest()
        def send(*args):
            if 'estimate' in args[0]: return self.provider(*args)
            self.wire.append(json.loads(args[1]))
            return self.response('{}')
        result = self.execute(send)
        self.assertIsNone(result['failure'])
        self.assertEqual(set(result['tasks']['B001'].values()), {'invalid_output'})
        self.assertEqual(result['queue_status'] if 'queue_status' in result else 'finished', 'finished')
        self.assertEqual(self.provider.completions, 3)
        self.assert_same_unrepaired_origin('{}')
        for stage in ('i0','gsr','ssr'):
            self.assertEqual(read(self.out/'B001'/stage/'final/database.json'), {})

    def test_partial_i0_does_not_stop_the_next_task(self):
        root = self.root/'dataset'
        task = root/'tasks/basic/B002'; task.mkdir()
        write(task/'task.json', {'case_id':'B002','domain':'basic','doi':'10.synthetic/2'})
        (task/'complete-prompt.md').write_text('Synthetic B002 task. Return the declared tables.')
        source = root/'materials/basic/B001'; target = root/'materials/basic/B002'; target.mkdir()
        m = read(source/'materials.json'); m['case']['case_id'] = 'B002'
        for name in ('article.xml','notes.txt'):
            (target/name).write_bytes((source/name).read_bytes())
        write(target/'materials.json', m)
        prepare(root,'B002',self.root/'prepared-b002')
        self.manifest(); self.frozen.unlink()
        draft=read(self.root/'draft.json')
        draft['tasks'].append({'case_id':'B002','prepared':str(self.root/'prepared-b002'),'required_reads':[]})
        write(self.root/'draft.json',draft); freeze(self.root/'draft.json',self.frozen)
        result=self.execute(self.first_response(self.raw(self.partial())))
        self.assertIsNone(result['failure'])
        self.assertEqual(result['tasks']['B001']['i0'],'invalid_output')
        self.assertEqual(set(result['tasks']['B002'].values()),{'completed'})
        self.assertEqual(self.provider.completions,6)

    def test_offline_recovery_keeps_originals_and_does_not_resubmit(self):
        self.manifest(); self.execute(self.first_response(self.raw(self.partial())))
        originals={str(p.relative_to(self.out)):sha(p) for p in self.out.glob('B001/*/final/*') if p.is_file()}
        checkpoint=self.out/'B001/i0/initial-review-start.json'; identity=sha(checkpoint)
        self.assertIsNone(self.execute(offline=True)['failure'])
        self.assertEqual(self.provider.completions,3)
        self.assertEqual(identity,sha(checkpoint))
        self.assertEqual(originals,{str(p.relative_to(self.out)):sha(p) for p in self.out.glob('B001/*/final/*') if p.is_file()})
        self.assertEqual([r['new_requests_this_session'] for r in read(self.out/'management/overview.json')['rows']],[0,0,0])

    def test_timeout_keeps_unknown_consumption_and_never_creates_review_start(self):
        self.manifest()
        def send(*args):
            if 'estimate' in args[0]: return self.provider(*args)
            self.provider.completions += 1
            raise TimeoutError('Synthetic transport timeout')
        result=self.execute(send)
        self.assertEqual(result['failure']['status'],'paused_unknown')
        self.assertEqual(result['tasks']['B001'],{'i0':'paused_unknown','gsr':'not_started','ssr':'not_started'})
        self.assertEqual(self.provider.completions,1)
        self.assertFalse((self.out/'B001/i0/final').exists())
        self.assertFalse((self.out/'B001/i0/initial-review-start.json').exists())
        self.assertTrue((self.out/'B001/i0/calls/00000/completion/failure.json').exists())
        self.assertEqual(read(self.out/'costs.json')['unknown_budget_calls'],1)
        self.assertEqual(self.execute(send)['failure']['status'],'paused_unknown')
        self.assertEqual(self.provider.completions,1)

    def test_output_truncation_still_pauses_before_reviews(self):
        self.manifest()
        result=self.execute(self.first_response(self.raw(self.partial()),finish='length'))
        self.assertEqual(result['failure']['status'],'paused_truncated')
        self.assertEqual(self.provider.completions,1)
        self.assertEqual(result['tasks']['B001']['gsr'],'not_started')
        self.assertEqual(result['tasks']['B001']['ssr'],'not_started')
        self.assertFalse((self.out/'B001/i0/initial-review-start.json').exists())

    def test_empty_api_message_is_not_a_received_submission(self):
        self.manifest()
        result=self.execute(self.first_response(''))
        self.assertEqual(result['failure']['status'],'failed_response')
        self.assertEqual(self.provider.completions,1)
        self.assertFalse((self.out/'B001/i0/initial-review-start.json').exists())
        self.assertEqual(result['tasks']['B001']['gsr'],'not_started')

    def test_budget_still_stops_before_first_review_without_changing_limits(self):
        self.manifest(); self.frozen.unlink()
        draft=read(self.root/'draft.json'); draft['max_total_cost']='0.0023'
        write(self.root/'draft.json',draft); frozen=freeze(self.root/'draft.json',self.frozen)
        result=self.execute(self.first_response(self.raw(self.partial())))
        self.assertEqual(result['failure']['status'],'paused_budget')
        self.assertEqual(result['tasks']['B001']['i0'],'invalid_output')
        self.assertEqual(result['tasks']['B001']['gsr'],'paused_budget')
        self.assertEqual(result['tasks']['B001']['ssr'],'not_started')
        self.assertEqual(self.provider.completions,1)
        self.assertTrue((self.out/'B001/i0/initial-review-start.json').exists())
        self.assertEqual(read(self.out/'manifest.json')['budgets'],frozen['budgets'])
        self.assertFalse((self.out/'limit-extensions').exists())

    def test_checkpoint_tampering_stops_recovery_and_export_includes_decision(self):
        self.manifest(); self.execute(self.first_response(self.raw(self.partial())))
        run_report(self.out,self.root/'export')
        checkpoint=self.out/'B001/i0/initial-review-start.json'
        self.assertEqual(read(checkpoint),read(self.root/'export/B001/i0/initial-review-start.json'))
        modified=read(checkpoint); modified['initial_history_sha256']='changed'; write(checkpoint,modified)
        self.assertEqual(self.execute(offline=True)['failure']['status'],'tampered')
        self.assertEqual(self.provider.completions,3)



if __name__ == '__main__':
    unittest.main()
