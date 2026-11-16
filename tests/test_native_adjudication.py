"""Synthetic provenance and exact replay tests for later source adjudications."""
import copy
import tempfile
import unittest
from pathlib import Path

from model_conversation.archive import read, sha, write, digest
from biotracebench_scoring import native_codex as native
from biotracebench_scoring import native_adjudication as adjudication
import test_native_codex as fixtures
import test_native_consistency as consistency_fixtures
from biotracebench_scoring import native_consistency as consistency

ACTOR = fixtures.ACTOR


class NativeAdjudicationTests(unittest.TestCase):
    def fixture(self, root):
        helper = fixtures.NativeCodexTests()
        inv, policy, prepared = helper.fixture(root)
        reply = helper.finish(root, inv, policy)
        return inv, policy, reply

    def changed(self, reply):
        value = copy.deepcopy(reply)
        item = next(f for f in value['fields'] if f['field_id'].endswith(':value'))
        item['assertions'][0].update(verdict='incorrect', reason='Synthetic source adjudicator rejects this expression.')
        item.update(verdict='incorrect', reason='Synthetic complete-field correction.')
        return value

    def append(self, root, reply, **kwargs):
        request = adjudication.adjudication_request(root/'plan', 'n-00001', root/'corrections')
        return adjudication.adjudicate_native(root/'plan', 'n-00001', reply, ACTOR,
            root/'corrections', reason='Synthetic evidence-based correction.',
            evidence=[{'source_id': 'source-a', 'quote': 'Arm A has value 5.'}],
            supersedes=request['supersedes'], **kwargs)

    def test_correction_replays_and_preserves_accepted_phases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, _, reply = self.fixture(root)
            before = {p: p.read_bytes() for p in (root/'plan/imports').rglob('*.json')}
            result = self.append(root, self.changed(reply))
            self.assertEqual(result['score']['field']['tp'], 1)
            self.assertEqual(result['score']['record']['tp'], 0)
            request = adjudication.adjudication_request(root/'plan', 'n-00001', root/'corrections')
            self.assertEqual(request['supersedes'], result['identity'])
            self.assertEqual(before, {p: p.read_bytes() for p in before})
            self.assertEqual(native.replay_native(root/'plan', root/'base')['completed_positions'], 2)

    def test_export_separates_first_review_and_adjudicated_views(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, _, reply = self.fixture(root)
            self.append(root, self.changed(reply))
            first = read(adjudication.export_view(root/'plan', root/'first', phase='first')['path'])
            final = read(adjudication.export_view(root/'plan', root/'final', adjudications=root/'corrections')['path'])
            self.assertEqual(first['judgment_view'], 'first')
            self.assertEqual(first['positions'][0]['score']['field']['tp'], 2)
            self.assertEqual(final['judgment_view'], 'source_adjudicated')
            self.assertEqual(final['positions'][0]['score']['field']['tp'], 1)
            self.assertEqual(final['positions'][0]['base_score']['field']['tp'], 2)
            self.assertTrue(all(sha(p) == h for p, h in final['source_sha256'].items()))
            with self.assertRaisesRegex(ValueError, 'cannot apply'):
                adjudication.export_view(root/'plan', root/'bad', phase='first', adjudications=root/'corrections')

    def test_stale_concurrent_update_rejected_and_retry_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, _, reply = self.fixture(root)
            base = adjudication.adjudication_request(root/'plan', 'n-00001', root/'corrections')
            arguments = dict(reason='Synthetic update.', evidence=[{'source_id':'source-a','quote':'value 5'}],
                             supersedes=base['supersedes'])
            a = adjudication.adjudicate_native(root/'plan', 'n-00001', self.changed(reply), ACTOR,
                                              root/'corrections', **arguments)
            b = adjudication.adjudicate_native(root/'plan', 'n-00001', self.changed(reply), ACTOR,
                                              root/'corrections', **arguments)
            self.assertEqual(a['identity'], b['identity'])
            with self.assertRaisesRegex(ValueError, 'stale'):
                adjudication.adjudicate_native(root/'plan', 'n-00001', reply, ACTOR,
                                              root/'corrections', **arguments)
            c = self.append(root, reply)
            self.assertNotEqual(c['identity'], a['identity'])
            self.assertEqual(len(list((root/'corrections/adjudications/n-00001').glob('*.json'))), 2)

    def test_source_proof_and_full_coverage_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, _, reply = self.fixture(root)
            request = adjudication.adjudication_request(root/'plan', 'n-00001', root/'corrections')
            for evidence in ([], [{'source_id':'source-a','quote':'Invented quote'}],
                             [{'source_id':'unknown','quote':'value 5'}],
                             [{'artifact_path':'/tmp/unfrozen','location':'panel A',
                               'observation':'Unbound observation without an asset hash'}],
                             [{'artifact_path':'/tmp/unfrozen','artifact_sha256':'0'*64,
                               'location':'panel A','observation':'Invented observation'}]):
                with self.assertRaises(ValueError):
                    adjudication.adjudicate_native(root/'plan','n-00001',reply,ACTOR,root/'corrections',
                        reason='Synthetic test.',evidence=evidence,supersedes=request['supersedes'])
            incomplete = copy.deepcopy(reply); incomplete['fields'].pop()
            with self.assertRaises(ValueError):self.append(root, incomplete)

    def test_receipt_tamper_rejected_even_with_recomputed_outer_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, _, reply = self.fixture(root)
            path = Path(self.append(root, reply)['path']); value = read(path)
            value['previous_reply_identity'] = '0'*64
            value.pop('identity'); value['identity'] = digest(value); write(path, value)
            with self.assertRaisesRegex(ValueError, 'preceding judgment'):
                adjudication.adjudication_request(root/'plan','n-00001',root/'corrections')

    def test_adjudication_requires_completed_review_and_separate_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); inv, policy, _ = fixtures.NativeCodexTests().fixture(root)
            with self.assertRaisesRegex(ValueError, 'accepted complete'):
                adjudication.adjudication_request(root/'plan','n-00001',root/'corrections')
            reply = fixtures.fixture_reply(inv, policy)
            with self.assertRaisesRegex(ValueError, 'outside'):
                adjudication.adjudicate_native(root/'plan','n-00001',reply,ACTOR,root/'plan/corrections',
                    reason='Synthetic.',evidence=[],supersedes='none')

    def test_first_pass_export_does_not_require_completed_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); inv, policy, _ = fixtures.NativeCodexTests().fixture(root)
            reply = fixtures.fixture_reply(inv, policy)
            native.ingest_native(root/'plan','n-00001',reply,ACTOR)
            first = read(adjudication.export_view(root/'plan',root/'first',phase='first',require_complete=True)['path'])
            self.assertTrue(all(r['status']=='complete' for r in first['positions']))
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                adjudication.export_view(root/'plan',root/'review',require_complete=True)

    def test_final_consistency_uses_adjudicated_and_unmodified_jobs_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template, inputs, jobs = consistency_fixtures.campaign(
                root, [consistency_fixtures.prediction(), consistency_fixtures.prediction(True, True)],
                final_bad={1:'sample:0:method'})
            self.assertGreater(consistency.inspect(root/'plan')['conflict_groups'], 0)
            request = adjudication.adjudication_request(root/'plan', jobs[1], root/'corrections')
            inv, mapping = inputs[1]
            correct = consistency_fixtures.native_reply(inv, template, mapping)
            result = adjudication.adjudicate_native(root/'plan',jobs[1],correct,ACTOR,root/'corrections',
                reason='Synthetic source resolves a native contradiction.',
                evidence=[{'source_id':'synthetic-source','quote':'Synthetic arm definitions'}],
                supersedes=request['supersedes'])
            receipt = read(result['path'])
            self.assertEqual(receipt['changes']['fields'][0]['key'], 'sample:0:method')
            report = consistency.inspect(root/'plan',adjudications=root/'corrections')
            self.assertEqual(report['conflict_groups'], 0)
            self.assertGreater(report['repeated_context_groups'], 0)
            self.assertEqual(report['origins'][jobs[1]]['phase'], 'source_adjudication')
            self.assertGreater(consistency.inspect(root/'plan')['conflict_groups'], 0)

    def test_partial_consistency_subset_is_explicit_and_never_reads_pending_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template, inputs, jobs = consistency_fixtures.campaign(
                root,[consistency_fixtures.prediction(),consistency_fixtures.prediction(True,True)],finish=False)
            inv, mapping = inputs[0]
            answer = consistency_fixtures.native_reply(inv,template,mapping)
            for phase in ('first','review'):
                native.ingest_native(root/'plan',jobs[0],answer,ACTOR,phase=phase)
            report = consistency.inspect(root/'plan',jobs=[jobs[0]])
            self.assertEqual(report['coverage'],'explicit_subset')
            self.assertEqual((report['selected_jobs'],report['total_plan_jobs']),(1,2))
            with self.assertRaises(ValueError):consistency.inspect(root/'plan',jobs=['unknown'])
            with self.assertRaises(ValueError):consistency.inspect(root/'plan',jobs=[jobs[0],jobs[0]])
