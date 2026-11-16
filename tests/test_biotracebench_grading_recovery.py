"""Preserve saved marking and incurred costs when replay stops partway through."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_biotracebench_task_grading as fixtures
from biotracebench_scoring import task_grading as grading
from biotracebench_scoring.task_grading_report import task_report, _atomic_text
from model_api import Backend
from model_conversation.archive import read, sha, verify


class RecoveryTests(unittest.TestCase):
    fixture = fixtures.WorkflowTests.fixture
    backend = fixtures.WorkflowTests.backend

    def interrupted_run(self, root):
        self.fixture(root, ('i0', 'gsr', 'ssr'))
        calls = []
        good = self.backend(calls)
        attempts = []

        def sender(*args):
            attempts.append(True)
            if len(attempts) == 3:
                raise TimeoutError('Synthetic third request interruption')
            return good.sender(*args)

        transport = Backend(fixtures.PROFILE, sender=sender)
        with self.assertRaises(Exception):
            grading.execute(root/'plan', root/'run', backend=transport)
        ids = [p['id'] for p in read(root/'plan/plan.json')['packets']]
        return transport, attempts, ids

    def report_bytes(self, root, ids):
        return {str(p.relative_to(root)):p.read_bytes()
                for output in ids for p in (root/'tasks'/output).iterdir()
                if p.name in {'marking.json', 'cells.csv', 'review.html', 'raw-grading.txt'}}

    def test_first_or_later_recovery_error_preserves_all_reports_and_costs(self):
        for fail_at in (1, 2):
            with self.subTest(fail_at=fail_at), tempfile.TemporaryDirectory() as temp, \
                    patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
                root = Path(temp)
                transport, attempts, ids = self.interrupted_run(root)
                reports = self.report_bytes(root/'run', ids[:2])
                costs = (root/'run/costs.json').read_bytes()
                scores = (root/'run/study-scores.json').read_bytes()
                recover = transport.recover
                replayed = []

                def broken_recover(*args):
                    replayed.append(True)
                    if len(replayed) == fail_at:
                        raise ValueError('Synthetic archive validation failure')
                    return recover(*args)

                with patch.object(transport, 'recover', side_effect=broken_recover), \
                        self.assertRaisesRegex(ValueError, 'Synthetic archive'):
                    grading.execute(root/'plan', root/'run', offline=True, backend=transport)
                self.assertEqual(self.report_bytes(root/'run', ids[:2]), reports)
                self.assertEqual((root/'run/costs.json').read_bytes(), costs)
                self.assertEqual((root/'run/study-scores.json').read_bytes(), scores)
                self.assertEqual(read(root/'run/status.json')['status'], 'paused')
                self.assertEqual(len(attempts), 3)

    def test_repeated_recovery_of_unknown_request_preserves_costs_without_resend(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root = Path(temp)
            transport, attempts, ids = self.interrupted_run(root)
            reports = self.report_bytes(root/'run', ids[:2])
            costs = read(root/'run/costs.json')
            with patch.dict('os.environ', {}, clear=True):
                for _ in range(2):
                    with self.assertRaisesRegex(RuntimeError, 'execution/cost unknown'):
                        grading.execute(root/'plan', root/'run', offline=True, backend=transport)
                    self.assertEqual(self.report_bytes(root/'run', ids[:2]), reports)
                    self.assertEqual(read(root/'run/costs.json'), costs)
                    self.assertEqual(len(read(root/'run/costs.json')['requests']), 2)
            self.assertEqual(len(attempts), 3)

    def test_crash_after_last_response_replays_without_duplicate_cost_or_generation(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root = Path(temp)
            self.fixture(root, ('i0', 'gsr', 'ssr'))
            calls = []
            original = grading.task_report
            completed = []

            def crash(folder, entry, result=None):
                if result:
                    completed.append(entry['id'])
                    if len(completed) == 3:
                        raise OSError('Synthetic report creation interruption')
                return original(folder, entry, result)

            with patch.object(grading, 'task_report', side_effect=crash), \
                    self.assertRaisesRegex(OSError, 'Synthetic report'):
                grading.execute(root/'plan', root/'run', backend=self.backend(calls))
            prior_costs = read(root/'run/costs.json')
            prior_reports = self.report_bytes(root/'run', completed[:2])
            with patch.dict('os.environ', {}, clear=True):
                state = grading.execute(root/'plan', root/'run', offline=True, backend=self.backend(calls))
                self.assertEqual(state['graded_outputs'], 3)
                self.assertEqual(self.report_bytes(root/'run', completed[:2]), prior_reports)
                self.assertEqual(read(root/'run/costs.json'), prior_costs)
                before = {str(p.relative_to(root/'run')):sha(p) for p in (root/'run').rglob('*') if p.is_file()}
                again = grading.execute(root/'plan', root/'run', offline=True, backend=self.backend(calls))
                self.assertEqual(again, state)
                self.assertEqual(before, {str(p.relative_to(root/'run')):sha(p) for p in (root/'run').rglob('*') if p.is_file()})
            verify(root/'run')
            self.assertEqual(len(calls), 3)

    def test_recovery_adds_an_unpublished_cost_once_and_keeps_prior_report(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root = Path(temp)
            self.fixture(root, ('i0', 'gsr', 'ssr'))
            calls = []
            original = grading.write

            def fail_second_ledger(path, value):
                if Path(path).name == 'costs.json' and len(value['requests']) == 2:
                    raise OSError('Synthetic ledger publication interruption')
                return original(path, value)

            with patch.object(grading, 'write', side_effect=fail_second_ledger), \
                    self.assertRaisesRegex(OSError, 'Synthetic ledger'):
                grading.execute(root/'plan', root/'run', backend=self.backend(calls))
            ids = [p['id'] for p in read(root/'plan/plan.json')['packets']]
            before = self.report_bytes(root/'run', ids[:1])
            self.assertEqual(len(read(root/'run/costs.json')['requests']), 1)
            with patch.dict('os.environ', {}, clear=True):
                for _ in range(2):
                    with self.assertRaisesRegex(RuntimeError, 'cannot submit unexecuted'):
                        grading.execute(root/'plan', root/'run', offline=True, backend=self.backend(calls))
                    self.assertEqual(len(read(root/'run/costs.json')['requests']), 2)
                    self.assertEqual(self.report_bytes(root/'run', ids[:1]), before)
            self.assertEqual(len(calls), 2)

    def test_recovery_error_preserves_a_previously_published_invalid_marking(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.dict('os.environ', {'DASHSCOPE_API_KEY':'synthetic-secret'}):
            root = Path(temp)
            self.fixture(root, ('i0', 'gsr'))
            calls = []
            malformed = self.backend(calls, 'bad_json')
            attempts = []

            def sender(*args):
                attempts.append(True)
                if len(attempts) == 2:
                    raise TimeoutError('Synthetic second request interruption')
                return malformed.sender(*args)

            transport = Backend(fixtures.PROFILE, sender=sender)
            with self.assertRaises(Exception):
                grading.execute(root/'plan', root/'run', backend=transport)
            output = read(root/'plan/plan.json')['packets'][0]['id']
            before = self.report_bytes(root/'run', [output])
            with patch.object(transport, 'recover', side_effect=ValueError('Synthetic archive failure')), \
                    self.assertRaisesRegex(ValueError, 'Synthetic archive'):
                grading.execute(root/'plan', root/'run', offline=True, backend=transport)
            self.assertEqual(self.report_bytes(root/'run', [output]), before)
            self.assertEqual(read(root/'run/status.json')['outputs'][0]['status'], 'failed_grading_response')
            self.assertEqual(len(attempts), 2)

    def test_report_render_failure_does_not_replace_existing_files(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)/'report'
            inv = fixtures.inventory(fixtures.GOLD, fixtures.GOLD, fixtures.DICT, fixtures.POLICY)
            result = fixtures.mark_all(inv, fixtures.reply_for(inv))
            entry = {'id':'synthetic', 'case_id':'SYN', 'condition':'i0', 'status':'automatic_scoring_completed'}
            task_report(folder, entry, result)
            before = {p.name:p.read_bytes() for p in folder.iterdir()}
            changed = copy.deepcopy(result)
            changed['cells'][0]['reason'] = 'Synthetic new report content'
            with patch('biotracebench_scoring.task_grading_report.csv.DictWriter.writerows',
                       side_effect=OSError('Synthetic render failure')), \
                    self.assertRaisesRegex(OSError, 'Synthetic render'):
                task_report(folder, entry, changed)
            self.assertEqual(before, {p.name:p.read_bytes() for p in folder.iterdir()})

    def test_text_publication_interruption_keeps_the_previous_complete_file(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)/'cells.csv'
            target.write_text('previous complete report\n')
            before = target.read_bytes()
            with patch('biotracebench_scoring.task_grading_report.os.fsync',
                       side_effect=OSError('Synthetic flush failure')), \
                    self.assertRaisesRegex(OSError, 'Synthetic flush'):
                _atomic_text(target, 'new complete report\n')
            self.assertEqual(target.read_bytes(), before)
            _atomic_text(target, 'new complete report\n')
            self.assertEqual(target.read_text(), 'new complete report\n')
            self.assertFalse(target.with_name('cells.csv.tmp').exists())


if __name__ == '__main__':
    unittest.main()
