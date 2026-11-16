"""Archive provenance must not become scientific regrading or a paid retry."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_biotracebench_task_grading as fixtures
from biotracebench_scoring import task_grading as grading
from model_api.archive_integrity import ArchiveConflict, FILES
from model_conversation.archive import read, write, sha, verify


class ArchiveTests(unittest.TestCase):
    fixture = fixtures.WorkflowTests.fixture
    backend = fixtures.WorkflowTests.backend

    def changed_transport(self, calls, mutate):
        backend = self.backend(calls)
        invoke = backend.invoke

        def changed(request, folder):
            response = invoke(request, folder)
            mutate(Path(folder), request, backend)
            return response

        backend.invoke = changed
        return backend

    def test_verified_missing_and_incomplete_receipts_have_identical_scores(self):
        metrics = []
        for mode in ('verified', 'missing', 'files', 'identity', 'malformed'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp, \
                    patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
                root = Path(temp)
                self.fixture(root)
                calls = []

                def mutate(folder, request, backend):
                    path = folder/'transport-receipt.json'
                    if mode == 'missing':
                        path.unlink()
                    elif mode in ('files', 'identity'):
                        value = read(path)
                        if mode == 'files':
                            value['files'].pop('api-response.bin')
                        else:
                            value.pop('profile_hash')
                        write(path, value)
                    elif mode == 'malformed':
                        path.write_text('{')

                backend = self.changed_transport(calls, mutate)
                state = grading.execute(root/'plan', root/'run', backend=backend)
                entry = state['outputs'][0]
                marking = read(root/'run/tasks'/entry['id']/'marking.json')
                expected = 'verified' if mode == 'verified' else 'unverified'
                self.assertEqual(entry['archive_integrity']['status'], expected)
                self.assertEqual(marking['result']['archive_integrity']['status'], expected)
                metrics.append((marking['result']['field'], marking['result']['record']))
                self.assertIn(expected, (root/'run/tasks'/entry['id']/'review.html').read_text())
                self.assertIn(expected, (root/'run/review.html').read_text())
                self.assertEqual(state['graded_outputs'], 1)
                before = {str(p.relative_to(root/'run')):sha(p) for p in (root/'run').rglob('*') if p.is_file()}
                with patch.dict('os.environ', {}, clear=True):
                    again = grading.execute(root/'plan', root/'run', offline=True, backend=backend)
                self.assertEqual(state, again)
                self.assertEqual(before, {str(p.relative_to(root/'run')):sha(p) for p in (root/'run').rglob('*') if p.is_file()})
                self.assertEqual(len(calls), 1)
                verify(root/'run')
        self.assertTrue(all(m == metrics[0] for m in metrics))

    def test_later_receipt_or_run_seal_does_not_upgrade_original_provenance(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root = Path(temp)
            self.fixture(root)
            calls = []
            backend = self.changed_transport(calls, lambda folder, *_:(folder/'transport-receipt.json').unlink())
            original = grading.task_report

            def crash(folder, entry, result=None):
                if result:
                    raise OSError('Synthetic report interruption')
                return original(folder, entry, result)

            with patch.object(grading, 'task_report', side_effect=crash), self.assertRaises(OSError):
                grading.execute(root/'plan', root/'run', backend=backend)
            packet = read(root/'plan/plan.json')['packets'][0]
            folder = root/'run/attempts'/packet['id']
            # Emulate someone generating a new checksum later; it cannot prove original provenance.
            write(folder/'transport-receipt.json', {'provider':'api',
                'profile_hash':backend.inspect_archive(packet['request'], folder)['profile_hash'],
                'request_hash':backend.inspect_archive(packet['request'], folder)['request_hash'],
                'files':{name:sha(folder/name) for name in FILES}})
            with patch.dict('os.environ', {}, clear=True):
                state = grading.execute(root/'plan', root/'run', offline=True, backend=backend)
            assessment = state['outputs'][0]['archive_integrity']
            self.assertEqual(assessment['status'], 'unverified')
            self.assertEqual(assessment['observed_status'], 'verified')
            self.assertEqual(state['graded_outputs'], 1)
            self.assertEqual(len(calls), 1)

    def test_conflicting_archive_is_not_retried_or_scored_and_other_outputs_continue(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root = Path(temp)
            budget = {**fixtures.BUDGET, 'max_network_retries_per_output':1}
            self.fixture(root, ('i0', 'gsr', 'ssr'), budget=budget)
            calls = []

            def mutate(folder, *_):
                if len(calls) == 1:
                    path = folder/'api-response.bin'
                    path.write_bytes(path.read_bytes()+b' ')

            state = grading.execute(root/'plan', root/'run', backend=self.changed_transport(calls, mutate))
            self.assertEqual(state['graded_outputs'], 2)
            self.assertEqual(state['archive_conflicts'], 1)
            self.assertEqual(state['status'], 'automatic_scoring_completed_with_errors')
            entry = state['outputs'][0]
            self.assertEqual(entry['status'], 'blocked_archive_conflict')
            marking = read(root/'run/tasks'/entry['id']/'marking.json')
            self.assertIsNone(marking['result'])
            self.assertTrue((root/'run/attempts'/entry['id']/'api-response.bin').read_bytes().endswith(b' '))
            self.assertEqual(len(read(root/'run/costs.json')['requests']), 2)
            unknown = read(root/'run/network-recovery.json')['unknown_requests']
            self.assertEqual(len(unknown), 1)
            self.assertEqual(unknown[0]['reason'], 'archive_conflict')
            audit = read(root/'run/completion-audit.json')
            self.assertEqual(audit['unknown_network_reserved_upper_cny'], '0')
            self.assertEqual(audit['unknown_archive_reserved_upper_cny'], unknown[0]['reserve_upper_cny'])
            self.assertEqual(len(calls), 3)
            self.assertFalse(list((root/'run/attempts').glob('*/network-retries')))

    def test_conflict_preserves_published_reports_and_known_costs(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root = Path(temp)
            self.fixture(root, ('i0', 'gsr', 'ssr'))
            calls = []
            backend = self.backend(calls)
            sender = backend.sender
            count = []

            def interrupted(*args):
                count.append(1)
                if len(count) == 3:
                    raise TimeoutError('Synthetic interruption')
                return sender(*args)

            backend.sender = interrupted
            with self.assertRaises(Exception):
                grading.execute(root/'plan', root/'run', backend=backend)
            packet = read(root/'plan/plan.json')['packets'][0]
            folder = root/'run/attempts'/packet['id']
            report = root/'run/tasks'/packet['id']
            before = {p.name:p.read_bytes() for p in report.iterdir()}
            costs = (root/'run/costs.json').read_bytes()
            path = folder/'api-response.bin'
            path.write_bytes(path.read_bytes()+b' ')
            with self.assertRaisesRegex(RuntimeError, 'execution/cost unknown'):
                grading.execute(root/'plan', root/'run', offline=True, backend=backend)
            self.assertEqual(before, {p.name:p.read_bytes() for p in report.iterdir()})
            self.assertEqual(costs, (root/'run/costs.json').read_bytes())
            self.assertEqual(read(root/'run/status.json')['archive_conflicts'], 1)
            self.assertEqual(len(count), 3)

    def test_api_inspection_and_recovery_are_read_only_without_a_receipt(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root = Path(temp)
            self.fixture(root)
            packet = read(root/'plan/plan.json')['packets'][0]
            calls = []
            backend = self.backend(calls)
            folder = root/'archive'
            response = backend.invoke(packet['request'], folder)
            (folder/'transport-receipt.json').unlink()
            before = {p.name:p.read_bytes() for p in folder.iterdir()}
            with patch.dict('os.environ', {}, clear=True):
                self.assertEqual(backend.inspect_archive(packet['request'], folder)['status'], 'unverified')
                self.assertEqual(backend.recover(packet['request'], folder), response)
            self.assertEqual(before, {p.name:p.read_bytes() for p in folder.iterdir()})
            bad = copy.deepcopy(packet['request'])
            bad['stage'] = 'different'
            with self.assertRaises(ArchiveConflict):
                backend.recover(bad, folder)
            self.assertEqual(len(calls), 1)

    def test_receipt_identity_and_partial_checksum_conflicts_are_detected(self):
        for mode in ('request', 'profile', 'partial', 'frozen'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp, \
                    patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
                root = Path(temp)
                self.fixture(root)
                packet = read(root/'plan/plan.json')['packets'][0]
                backend = self.backend([])
                folder = root/'archive'
                backend.invoke(packet['request'], folder)
                path = folder/'transport-receipt.json'
                stamp = read(path)
                if mode in ('request', 'profile'):
                    stamp[mode+'_hash'] = '0'*64
                elif mode == 'partial':
                    stamp['files'] = {'api-response.bin':'0'*64}
                else:
                    (folder/'transport-receipt.json').unlink()
                    frozen = read(folder/'api-request.json')
                    frozen['profile']['model'] = 'different'
                    write(folder/'api-request.json', frozen)
                if mode != 'frozen':
                    write(path, stamp)
                with self.assertRaises(ArchiveConflict):
                    backend.recover(packet['request'], folder)

    def test_conflict_observation_cannot_be_cleared_by_regenerating_a_receipt(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            from biotracebench_scoring.grading_archives import assess
            root = Path(temp)
            self.fixture(root)
            packet = read(root/'plan/plan.json')['packets'][0]
            backend = self.backend([])
            folder = root/'run/attempts'/packet['id']
            backend.invoke(packet['request'], folder)
            path = folder/'transport-receipt.json'
            stamp = read(path)
            stamp['files']['api-response.bin'] = '0'*64
            write(path, stamp)
            with self.assertRaises(ArchiveConflict):
                assess(root/'run', backend, packet, folder)
            stamp['files']['api-response.bin'] = sha(folder/'api-response.bin')
            write(path, stamp)
            self.assertEqual(backend.inspect_archive(packet['request'], folder)['status'], 'verified')
            with self.assertRaises(ArchiveConflict) as caught:
                assess(root/'run', backend, packet, folder)
            self.assertEqual(caught.exception.assessment['status'], 'conflict')
            self.assertEqual(caught.exception.assessment['observed_status'], 'verified')


if __name__ == '__main__':
    unittest.main()
