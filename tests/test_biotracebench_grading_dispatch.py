"""Prove unsent failures can resume without hiding potentially billed requests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_biotracebench_task_grading as fixtures
from biotracebench_scoring import task_grading as grading
from model_api import ApiFailure, Backend, dispatch
from model_conversation.archive import digest, read, write, verify


class DispatchTests(unittest.TestCase):
    fixture = fixtures.WorkflowTests.fixture
    backend = fixtures.WorkflowTests.backend

    def single(self, root):
        self.fixture(root, budget={**fixtures.BUDGET, 'max_requests':1,
                                  'total_cny':'0.073738'})
        packet = read(root/'plan/plan.json')['packets'][0]
        return packet, root/'run/attempts'/packet['id']

    def test_missing_or_invalid_credential_creates_no_reservation_and_can_resume(self):
        for credential in (None, 'synthetic\ninvalid', 'synthetic-无效'):
            with self.subTest(credential_present=credential is not None), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                _, folder = self.single(root)
                calls = []
                backend = self.backend(calls)
                environment = {} if credential is None else {'DASHSCOPE_API_KEY':credential}
                with patch.dict('os.environ', environment, clear=True):
                    for _ in range(2):
                        with self.assertRaises(ApiFailure):
                            grading.execute(root/'plan', root/'run', backend=backend)
                state = read(root/'run/status.json')
                self.assertEqual(state['outputs'][0]['status'], 'paused_before_send')
                self.assertEqual(state['outputs'][0]['dispatch_state'], 'not_sent')
                self.assertFalse(folder.exists())
                ledger = read(root/'run/network-recovery.json')
                self.assertEqual(ledger['reserved_requests'], 0)
                self.assertEqual(ledger['budget_committed_upper_cny'], '0')
                self.assertFalse(ledger['unknown_requests'])
                self.assertFalse(calls)
                if credential:
                    self.assertTrue(all(credential.encode() not in p.read_bytes()
                        for p in (root/'run').rglob('*') if p.is_file()))
                with patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
                    state = grading.execute(root/'plan', root/'run', backend=backend)
                self.assertEqual(state['graded_outputs'], 1)
                self.assertEqual(state['outputs'][0]['dispatch_state'], 'response_saved')
                self.assertNotIn('reason', state['outputs'][0])
                self.assertEqual(len(calls), 1)
                self.assertEqual(read(root/'run/completion-audit.json')['generated_requests'], 1)
                self.assertEqual(len(read(root/'run/costs.json')['requests']), 1)
                verify(root/'run')

    def test_credential_disappearing_after_reservation_releases_count_and_money(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root = Path(temp)
            _, folder = self.single(root)
            calls = []
            backend = self.backend(calls)
            invoke = backend.invoke

            def missing_after_reservation(*args):
                with patch.dict('os.environ', {}, clear=True):
                    return invoke(*args)

            with patch.object(backend, 'invoke', side_effect=missing_after_reservation), self.assertRaises(ApiFailure):
                grading.execute(root/'plan', root/'run', backend=backend)
            self.assertTrue((folder/'reservation.json').exists())
            self.assertFalse((folder/'api-request.json').exists())
            self.assertEqual(dispatch.state(folder), 'not_sent')
            ledger = read(root/'run/network-recovery.json')
            self.assertEqual(ledger['reserved_requests'], 0)
            self.assertEqual(ledger['local_reservations'], 1)
            self.assertEqual(ledger['not_sent_requests'][0]['upper_cny'], '0')
            self.assertEqual(ledger['budget_committed_upper_cny'], '0')
            self.assertFalse(ledger['unknown_requests'])
            before = (folder/'reservation.json').read_bytes()
            self.assertEqual(grading.execute(root/'plan', root/'run', backend=backend)['graded_outputs'], 1)
            self.assertEqual((folder/'reservation.json').read_bytes(), before)
            self.assertEqual(len(calls), 1)
            self.assertFalse((folder/'network-retries').exists())

    def test_credential_disappearing_before_preparation_leaves_no_orphan_directory(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp)
            _,folder=self.single(root)
            calls=[]
            backend=self.backend(calls)
            prepare=backend.prepare_send

            def missing_before_preparation(*args):
                with patch.dict('os.environ',{},clear=True):
                    return prepare(*args)

            with patch.object(backend,'prepare_send',side_effect=missing_before_preparation), self.assertRaises(ApiFailure):
                grading.execute(root/'plan',root/'run',backend=backend)
            self.assertFalse(folder.exists())
            self.assertFalse(calls)
            self.assertEqual(read(root/'run/status.json')['outputs'][0]['dispatch_state'],'not_sent')
            self.assertEqual(grading.execute(root/'plan',root/'run',backend=backend)['graded_outputs'],1)
            self.assertEqual(len(calls),1)

    def test_crash_before_api_invoke_and_after_request_snapshot_can_resume(self):
        for phase in ('reservation', 'request_snapshot', 'preparation'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temp, \
                    patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
                root = Path(temp)
                packet, folder = self.single(root)
                calls = []
                backend = self.backend(calls)
                original = grading.event

                def crash_event(out, kind, **details):
                    if kind == 'request_reserved':
                        raise OSError('Synthetic crash before API invoke')
                    return original(out, kind, **details)

                if phase == 'reservation':
                    with patch('biotracebench_scoring.grading_attempts.event', side_effect=crash_event), self.assertRaises(OSError):
                        grading.execute(root/'plan', root/'run', backend=backend)
                elif phase == 'request_snapshot':
                    with patch('model_api.backend.dispatch.start', side_effect=OSError('Synthetic pre-dispatch crash')), self.assertRaises(OSError):
                        grading.execute(root/'plan', root/'run', backend=backend)
                else:
                    # A crash after durable preparation but before local reservation.
                    backend.prepare_send(packet['request'], folder)
                self.assertFalse(calls)
                self.assertEqual(dispatch.state(folder), 'not_sent')
                snapshot = (folder/'api-request.json').read_bytes() if (folder/'api-request.json').exists() else None
                self.assertEqual(grading.execute(root/'plan', root/'run', backend=backend)['graded_outputs'], 1)
                if snapshot is not None:
                    self.assertEqual((folder/'api-request.json').read_bytes(), snapshot)
                self.assertEqual(len(calls), 1)
                self.assertEqual(read(root/'run/completion-audit.json')['generated_requests'], 1)

    def test_dispatch_marker_without_a_reply_stays_unknown_and_is_not_resent(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root = Path(temp)
            _, folder = self.single(root)
            calls = []
            backend = self.backend(calls)
            start = dispatch.start

            def crash_after_marker(*args):
                start(*args)
                raise OSError('Synthetic crash at the send boundary')

            with patch('model_api.backend.dispatch.start', side_effect=crash_after_marker), self.assertRaises(OSError):
                grading.execute(root/'plan', root/'run', backend=backend)
            self.assertFalse(calls)
            self.assertEqual(dispatch.state(folder), 'may_have_been_sent')
            ledger = read(root/'run/network-recovery.json')
            self.assertEqual(ledger['reserved_requests'], 1)
            self.assertEqual(ledger['unknown_reserved_upper_cny'], '0.073738')
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, 'execution/cost unknown'):
                    grading.execute(root/'plan', root/'run', backend=backend)
            self.assertFalse(calls)

    def test_legacy_ambiguous_reservation_does_not_gain_unsent_proof(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root = Path(temp)
            packet, folder = self.single(root)
            plan = read(root/'plan/plan.json')
            write(folder/'reservation.json', {'packet_identity':digest(packet),
                'reserve_upper_cny':'0.073738', 'output_control':plan['output_control']})
            calls = []
            with self.assertRaisesRegex(RuntimeError, 'execution/cost unknown'):
                grading.execute(root/'plan', root/'run', backend=self.backend(calls))
            self.assertFalse(calls)
            self.assertFalse((folder/dispatch.PREPARED).exists())
            ledger = read(root/'run/network-recovery.json')
            self.assertEqual(ledger['unknown_requests'][0]['reason'], 'legacy_submission_unknown')
            self.assertEqual(ledger['budget_committed_upper_cny'], '0.073738')

    def test_remote_authentication_rejection_is_not_a_local_unsent_failure(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root = Path(temp)
            _, folder = self.single(root)
            calls = []

            def rejected(*args):
                calls.append(1)
                return 401, {}, b'{"error":{"code":"invalid_api_key"}}'

            backend = Backend(fixtures.PROFILE, sender=rejected)
            for _ in range(2):
                with self.assertRaises(ApiFailure):
                    grading.execute(root/'plan', root/'run', backend=backend)
            self.assertEqual(len(calls), 1)
            self.assertEqual(dispatch.state(folder), 'may_have_been_sent')
            ledger = read(root/'run/network-recovery.json')
            self.assertFalse(ledger['not_sent_requests'])
            self.assertEqual(ledger['reserved_requests'], 1)

    def test_offline_unsent_recovery_never_sends_or_requires_a_credential(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            packet, folder = self.single(root)
            calls = []
            backend = self.backend(calls)
            with patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
                backend.prepare_send(packet['request'], folder)
            with patch.dict('os.environ', {}, clear=True), self.assertRaisesRegex(RuntimeError, 'Offline recovery cannot submit'):
                grading.execute(root/'plan', root/'run', offline=True, backend=backend)
            self.assertFalse(calls)
            self.assertEqual(dispatch.state(folder), 'not_sent')

    def test_changed_preparation_cannot_reuse_an_unsent_request(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root = Path(temp)
            packet, folder = self.single(root)
            calls = []
            backend = self.backend(calls)
            backend.prepare_send(packet['request'], folder)
            stamp = read(folder/dispatch.PREPARED)
            stamp['request_hash'] = '0'*64
            write(folder/dispatch.PREPARED, stamp)
            with self.assertRaisesRegex(ValueError, 'preparation identity changed'):
                backend.invoke(packet['request'], folder)
            self.assertFalse(calls)
            self.assertFalse((folder/dispatch.STARTED).exists())

    def test_later_unsent_failure_preserves_completed_reports_and_costs(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root = Path(temp)
            self.fixture(root, ('i0','gsr','ssr'), budget={**fixtures.BUDGET,'max_requests':3})
            calls = []
            backend = self.backend(calls)
            invoke = backend.invoke

            def fail_second(*args):
                if len(calls)==1:
                    with patch.dict('os.environ', {}, clear=True):
                        return invoke(*args)
                return invoke(*args)

            with patch.object(backend,'invoke',side_effect=fail_second), self.assertRaises(ApiFailure):
                grading.execute(root/'plan',root/'run',backend=backend)
            output = read(root/'plan/plan.json')['packets'][0]['id']
            report = root/'run/tasks'/output
            before = {p.name:p.read_bytes() for p in report.iterdir()}
            cost = read(root/'run/costs.json')['requests'][0]
            result = grading.execute(root/'plan',root/'run',backend=backend)
            self.assertEqual(result['graded_outputs'],3)
            self.assertEqual(before,{p.name:p.read_bytes() for p in report.iterdir()})
            self.assertEqual(cost,read(root/'run/costs.json')['requests'][0])
            self.assertEqual(len(calls),3)
            self.assertEqual(read(root/'run/completion-audit.json')['generated_requests'],3)


if __name__ == '__main__':
    unittest.main()
