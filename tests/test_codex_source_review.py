"""Scoped source revisions, evidence exhaustion and immutable first-pass archives."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from model_conversation.archive import digest
from biotracebench_scoring import codex_source_review as review
from biotracebench_scoring import codex_consistency as consistency
from biotracebench_scoring import codex_audit_export as exporter
from test_codex_consistency import job, write
from test_biotracebench_task_grading import reply_for


class SourceReviewTests(unittest.TestCase):
    def fixture(self, root, sources=None):
        route = job(root, 1, verdict='uncertain')
        write(root / 'index.json', {'plan_identity': 'plan', 'positions': [route]})
        write(root / 'base-plan/plan.json', {'profile': {'model': 'synthetic-codex', 'reasoning_effort': 'high', 'disabled_features': []}})
        if sources is None:
            sources = [{'id': 'decisive', 'source': 'synthetic.txt', 'locator': 'Materials', 'text': 'The source defines the selected material as liver protein.'}]
        write(root / 'catalog/synthetic.json', sources)
        review.prepare_review(root / 'index.json', root / 'base-plan', root / 'catalog', root / 'review')
        return route

    def executor(self, calls, decisive='decisive'):
        def run(request, attempt, profile, images):
            calls.append(request)
            payload = request['payload']; inv = payload['inventory']
            resolved = any(s['id'] == decisive for s in payload['sources'])
            reply = reply_for(inv, overrides={'sample_material': 'correct' if resolved else 'uncertain', 'sample_id': 'correct'})
            if 'batch_scope' in payload:
                wanted = {(p['prediction_cell'], p['reference_cell']) for p in payload['batch_scope']['expected_cell_pairs']}
                reply = {'cells': [c for c in reply['cells'] if (c['prediction_cell'], c['reference_cell']) in wanted], 'reference_issues': []}
            write(attempt / 'response.txt', reply)
            write(attempt / 'transport.json', {'tool_events': 0, 'actual_model_metadata': [{'model': 'synthetic-codex'}],
                                              'response_sha256': review.sha(attempt / 'response.txt')})
            return reply
        return run

    def test_scoped_source_closure_preserves_first_pass_and_unreviewed_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); route = self.fixture(root)
            before = {str(p): review.sha(p) for p in (root / 'job-1').rglob('*.json')}
            original = review.read(route['result']); calls = []
            result = review.execute_review(root / 'review', executor=self.executor(calls))
            final = review.read(root / 'review/jobs/job-1/result.json')
            self.assertEqual(final['score']['unresolved_items'], 0)
            self.assertEqual(result['resolved'], 1)
            self.assertEqual(len(calls), 1)
            self.assertEqual(final['marking']['records'], original['marking']['records'])
            scope = calls[0]['payload']['batch_scope']
            changed = {(c['prediction_cell'], c['reference_cell']) for c in scope['expected_cell_pairs']}
            old_cells = {(c['prediction_cell'], c['reference_cell']): c for c in original['marking']['cells']}
            self.assertTrue(all(c == old_cells[c['prediction_cell'], c['reference_cell']]
                                for c in final['marking']['cells'] if (c['prediction_cell'], c['reference_cell']) not in changed))
            self.assertTrue(all(review.sha(p) == expected for p, expected in before.items()))
            native, _ = review.validate_review_native(root / 'review/jobs/job-1/result.json', final)
            self.assertEqual(native['actual_model'], 'synthetic-codex')
            # The final overlay keeps an explicit per-position origin plan.
            index = review.read(result['final_index'])
            self.assertEqual(index['positions'][0]['plan_identity'], final['plan_identity'])
            consistency.inspect(result['final_index'], root / 'consistency.json')
            packet = review.read(route['packet'])
            audit_marking = reply_for(packet['payload']['inventory'])
            write(root / 'audit/adjudicated/Q001.json', {'identity': {'case': route['case'], 'model': route['model'],
                    'stage': 'i0', 'domain': 'basic'}, 'inventory': packet['payload']['inventory'], 'marking': audit_marking})
            exporter.export(result['final_index'], root / 'audit', root / 'verified.json')
            verified = review.read(root / 'verified.json')
            self.assertEqual(next(iter(verified['jobs'].values()))['origin_plan_identity'], final['plan_identity'])
            self.assertIn(str(Path(route['result']).resolve()), verified['source_sha256'])

    def test_more_unseen_evidence_is_used_until_source_supported_closure(self):
        sources = [{'id': 'a', 'source': 'source.txt', 'locator': 'Introduction', 'text': 'Background about the selected assay.'},
                   {'id': 'z', 'source': 'source.txt', 'locator': 'Materials', 'text': 'The definitive material record identifies liver protein.'}]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            route = job(root, 1, verdict='uncertain')
            write(root / 'index.json', {'plan_identity': 'plan', 'positions': [route]})
            write(root / 'base-plan/plan.json', {'profile': {'model': 'synthetic-codex', 'reasoning_effort': 'high', 'disabled_features': []}})
            write(root / 'catalog/synthetic.json', sources)
            review.prepare_review(root / 'index.json', root / 'base-plan', root / 'catalog', root / 'review', source_character_budget=40)
            calls = []; review.execute_review(root / 'review', executor=self.executor(calls, decisive='z'))
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0]['payload']['source_review_coverage']['remaining_catalog_chunks'], 1)
            self.assertEqual(calls[1]['payload']['source_review_coverage']['remaining_catalog_chunks'], 0)
            self.assertEqual(review.read(root / 'review/jobs/job-1/result.json')['score']['unresolved_items'], 0)

    def test_exhausted_evidence_retains_genuine_uncertainty_in_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            review.execute_review(root / 'review', executor=self.executor([], decisive='absent'))
            state = review.read(root / 'review/jobs/job-1/status.json')
            self.assertEqual(state['status'], 'source_review_queue')
            self.assertGreater(state['unresolved_items'], 0)

    def test_changed_first_pass_or_native_reply_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); route = self.fixture(root)
            Path(route['result']).write_text(Path(route['result']).read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'First-pass'):
                review.execute_review(root / 'review', executor=self.executor([]))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            review.execute_review(root / 'review', executor=self.executor([]))
            result_path = root / 'review/jobs/job-1/result.json'; result = review.read(result_path)
            part = result['source_review']['parts'][0]
            Path(part['reply']).write_text('{}')
            with self.assertRaisesRegex(ValueError, 'native phase'):
                review.validate_review_native(result_path, result)

    def test_offline_recovery_sends_no_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            with self.assertRaisesRegex(RuntimeError, 'offline recovery sent no request'):
                review.execute_review(root / 'review', offline=True, executor=lambda *_: self.fail('No process may run'))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            review.execute_review(root / 'review', executor=self.executor([]))
            folder = root / 'review/jobs/job-1'
            (folder / 'result.json').unlink()
            (folder / 'round-001/part-001/accepted.json').unlink()
            (folder / 'round-001/part-001/attempt-001/reply.json').unlink()
            result = review.execute_review(root / 'review', offline=True, executor=lambda *_: self.fail('Recovery may not send'))
            self.assertEqual(result['resolved'], 1)

    def test_original_image_bytes_are_attached_and_bound_without_a_paid_test_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); attempt = root / 'attempt'; attempt.mkdir()
            image_path = root / 'figure.png'; image_path.write_bytes(b'synthetic original figure bytes')
            image = {'id': 'figure', 'source': 'figures/figure.png', 'path': str(image_path), 'sha256': review.sha(image_path)}
            profile = {'model': 'synthetic-codex', 'reasoning_effort': 'high', 'disabled_features': []}
            request = {'instruction': 'Inspect the attached original figure.', 'payload': {}, 'response_schema': {'type': 'object'}}
            commands = []
            def invoke(command, **kwargs):
                commands.append(command)
                output = Path(command[command.index('-o') + 1]); write(output, {'cells': [], 'reference_issues': []})
                kwargs['stdout'].write(b'{"type":"thread.started","thread_id":"synthetic"}\n')
                return SimpleNamespace(returncode=0)
            with patch.object(review.subprocess, 'run', side_effect=invoke), patch.object(review.native, '_session_model_metadata', return_value=[{'model': 'synthetic-codex'}]):
                review._image_invoke(request, attempt, profile, [image])
            self.assertIn('--image', commands[0])
            attachment = Path(commands[0][commands[0].index('--image') + 1])
            self.assertEqual(attachment.read_bytes(), image_path.read_bytes())
            metadata = review.read(attempt / 'transport.json')
            self.assertEqual(metadata['image_attachments'][0]['sha256'], image['sha256'])


if __name__ == '__main__': unittest.main()
