"""Local response reuse and bounded network replacement; no real network calls."""
import copy
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import test_biotracebench_task_grading as fixtures
from biotracebench_scoring import task_grading as grading
from model_api import Backend
from model_conversation.archive import read, write, verify, sha


class NetworkRecoveryTests(unittest.TestCase):
    fixture = fixtures.WorkflowTests.fixture
    backend = fixtures.WorkflowTests.backend

    def setup_run(self, root, *, budget=None, stages=('i0',), fail_at=(1,), mode='valid'):
        self.fixture(root, stages, budget=budget or {**fixtures.BUDGET, 'max_network_retries_per_output':1})
        calls, sent = [], []
        good = self.backend(calls, mode)

        def sender(*args):
            sent.append(args[1])
            if len(sent) in fail_at:
                raise TimeoutError('Synthetic connection loss')
            return good.sender(*args)

        return Backend(fixtures.PROFILE, sender=sender), sent

    def test_resume_reuses_complete_initial_and_replaces_only_interrupted_output(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root = Path(temp)
            backend, sent = self.setup_run(root, stages=('i0','gsr'), fail_at=(2,))
            with self.assertRaises(Exception):grading.execute(root/'plan', root/'run', backend=backend)
            self.assertEqual(len(sent), 2)  # No immediate automatic retry.
            ids = [p['id'] for p in read(root/'plan/plan.json')['packets']]
            first = (root/'run/tasks'/ids[0]/'marking.json').read_bytes()
            result = grading.execute(root/'plan', root/'run', backend=backend)
            self.assertEqual(result['graded_outputs'], 2)
            self.assertEqual(len(sent), 3)
            self.assertEqual(sent[1], sent[2])
            self.assertEqual((root/'run/tasks'/ids[0]/'marking.json').read_bytes(), first)
            old = root/'run/attempts'/ids[1]
            self.assertTrue((old/'api-request.json').exists())
            self.assertTrue((old/'network-interruption.json').exists())
            self.assertFalse((old/'api-response.bin').exists())
            self.assertTrue((old/'network-retries/0001/api-response.bin').exists())
            ledger = read(root/'run/network-recovery.json')
            self.assertEqual(len(ledger['unknown_requests']), 1)
            self.assertEqual(Decimal(ledger['known_usage_upper_cny']), Decimal('0.00024'))
            self.assertEqual(Decimal(ledger['unknown_reserved_upper_cny']), Decimal('0.073738'))
            self.assertEqual(Decimal(ledger['budget_committed_upper_cny']), Decimal('0.073978'))
            self.assertIsNone(ledger['exact_cny'])
            self.assertEqual(read(root/'run/completion-audit.json')['generated_requests'], 3)
            costs = read(root/'run/costs.json')['requests']
            self.assertEqual(len(costs), 2)
            self.assertTrue(costs[1]['attempt'].endswith('/network-retries/0001'))
            verify(root/'run')
            before = {str(p.relative_to(root/'run')):sha(p) for p in (root/'run').rglob('*') if p.is_file()}
            with patch.dict('os.environ', {}, clear=True):
                grading.execute(root/'plan', root/'run', offline=True, backend=backend)
            self.assertEqual(before, {str(p.relative_to(root/'run')):sha(p) for p in (root/'run').rglob('*') if p.is_file()})
            self.assertEqual(len(sent), 3)

    def test_offline_recovery_never_creates_a_replacement_request(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);backend,sent=self.setup_run(root)
            with self.assertRaises(Exception):grading.execute(root/'plan',root/'run',backend=backend)
            with patch.dict('os.environ',{},clear=True), self.assertRaisesRegex(RuntimeError,'offline recovery cannot resend'):
                grading.execute(root/'plan',root/'run',offline=True,backend=backend)
            self.assertEqual(len(sent),1)
            self.assertFalse(list((root/'run').glob('attempts/*/network-retries/*')))

    def test_one_replacement_limit_survives_repeated_restarts(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);backend,sent=self.setup_run(root,fail_at=(1,2))
            for _ in range(2):
                with self.assertRaises(Exception):grading.execute(root/'plan',root/'run',backend=backend)
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError,'retry limit reached'):
                    grading.execute(root/'plan',root/'run',backend=backend)
            self.assertEqual(len(sent),2)
            ledger=read(root/'run/network-recovery.json')
            self.assertEqual(len(ledger['unknown_requests']),2)
            self.assertEqual(Decimal(ledger['unknown_reserved_upper_cny']),Decimal('0.147476'))

    def test_count_or_money_limit_includes_the_original_unknown_request(self):
        for override in ({'max_requests':1}, {'total_cny':'0.147475'}):
            with self.subTest(override=override),tempfile.TemporaryDirectory() as temp,patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
                root=Path(temp);backend,sent=self.setup_run(root,budget={**fixtures.BUDGET,'max_network_retries_per_output':1,**override})
                with self.assertRaises(Exception):grading.execute(root/'plan',root/'run',backend=backend)
                with self.assertRaisesRegex(RuntimeError,'budget reached'):
                    grading.execute(root/'plan',root/'run',backend=backend)
                self.assertEqual(len(sent),1)
                self.assertFalse(list((root/'run').glob('attempts/*/network-retries/*/reservation.json')))

    def test_equal_budget_boundary_allows_one_replacement_without_releasing_unknown(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);backend,sent=self.setup_run(root,budget={**fixtures.BUDGET,'max_network_retries_per_output':1,'total_cny':'0.147476'})
            with self.assertRaises(Exception):grading.execute(root/'plan',root/'run',backend=backend)
            self.assertEqual(grading.execute(root/'plan',root/'run',backend=backend)['graded_outputs'],1)
            self.assertEqual(len(sent),2)
            self.assertEqual(len(read(root/'run/network-recovery.json')['unknown_requests']),1)

    def test_existing_complete_response_is_reused_before_any_replacement(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);backend,sent=self.setup_run(root,fail_at=())
            original=grading.task_report
            def crash(folder,entry,result=None):
                if result:raise OSError('Synthetic report interruption')
                return original(folder,entry,result)
            with patch.object(grading,'task_report',side_effect=crash),self.assertRaises(OSError):
                grading.execute(root/'plan',root/'run',backend=backend)
            with patch.dict('os.environ',{},clear=True):
                result=grading.execute(root/'plan',root/'run',offline=True,backend=backend)
            self.assertEqual(result['graded_outputs'],1)
            self.assertEqual(len(sent),1)
            self.assertFalse(list((root/'run').glob('attempts/*/network-retries/*')))

    def test_invalid_or_truncated_scoring_response_is_not_a_network_retry(self):
        for mode in ('bad_json','truncated','missing_usage'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp,patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
                root=Path(temp);backend,sent=self.setup_run(root,fail_at=(),mode=mode)
                try:grading.execute(root/'plan',root/'run',backend=backend)
                except ValueError:pass
                try:grading.execute(root/'plan',root/'run',backend=backend)
                except ValueError:pass
                self.assertEqual(len(sent),1)
                self.assertFalse(list((root/'run').glob('attempts/*/network-retries/*')))

    def test_archive_validation_failure_does_not_trigger_network_retry(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);backend,sent=self.setup_run(root)
            with self.assertRaises(Exception):grading.execute(root/'plan',root/'run',backend=backend)
            with patch.object(backend,'recover',side_effect=ValueError('Synthetic archive mismatch')),self.assertRaises(ValueError):
                grading.execute(root/'plan',root/'run',backend=backend)
            self.assertEqual(len(sent),1)
            self.assertFalse(list((root/'run').glob('attempts/*/network-retries/*')))

    def test_absent_or_invalid_retry_setting_never_authorizes_extra_requests(self):
        for value in (None, True, -1, '1'):
            with self.subTest(value=value),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);backend,sent=self.setup_run(root,budget={**fixtures.BUDGET,'max_network_retries_per_output':value})
                with self.assertRaisesRegex(ValueError,'nonnegative integer'):
                    grading.execute(root/'plan',root/'run',backend=backend)
                self.assertFalse(sent)
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root=Path(temp);backend,sent=self.setup_run(root,budget=copy.deepcopy(fixtures.BUDGET))
            with self.assertRaises(Exception):grading.execute(root/'plan',root/'run',backend=backend)
            with self.assertRaisesRegex(RuntimeError,'retry limit reached'):
                grading.execute(root/'plan',root/'run',backend=backend)
            self.assertEqual(len(sent),1)


if __name__=='__main__':unittest.main()
