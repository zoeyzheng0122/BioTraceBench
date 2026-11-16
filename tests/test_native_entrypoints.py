import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from biotracebench_scoring.__main__ import main


class NativeEntrypointTests(unittest.TestCase):
    def test_prepare_uses_direct_native_interface_without_cli_transport(self):
        with patch('biotracebench_scoring.native_codex.prepare_native', return_value={'positions': 36}) as prepare:
            with patch('biotracebench_scoring.codex_grading.execute', side_effect=AssertionError('CLI transport invoked')):
                with contextlib.redirect_stdout(io.StringIO()):
                    result = main(['native-prepare', '--manifest', '/external/manifest.json',
                                   '--contexts', '/external/contexts.json', '--task-policies', '/external/policies.json',
                                   '--out', '/external/native', '--condition', 'i0'])
        self.assertEqual(result, 0)
        prepare.assert_called_once_with('/external/manifest.json', '/external/contexts.json',
                                        '/external/native', conditions=['i0'], task_policies='/external/policies.json')

    def test_import_preserves_actor_mapping_and_source_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'actor.json'
            actor = {'kind': 'native_codex', 'agent_id': 'synthetic-agent', 'declaration': 'Direct native judgment.'}
            path.write_text(json.dumps(actor))
            with patch('biotracebench_scoring.native_codex.ingest_native', return_value={'status': 'accepted'}) as ingest:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(['native-import', '--plan', '/external/native', '--job', 'n-1',
                        '--reply', '/external/judgment.json', '--actor', str(path), '--phase', 'review',
                        '--scope', 'fields', '--mapping-identity', 'mapping', '--evidence', '/external/evidence.json']), 0)
            ingest.assert_called_once_with('/external/native', 'n-1', '/external/judgment.json', actor,
                phase='review', scope='fields', mapping_identity='mapping', evidence='/external/evidence.json')

    def test_replay_exposes_incomplete_status(self):
        with patch('biotracebench_scoring.native_codex.replay_native', return_value={'status': 'incomplete'}) as replay:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['native-replay', '--plan', '/external/native', '--out', '/external/replayed']), 1)
        replay.assert_called_once_with('/external/native', '/external/replayed')

    def test_export_keeps_reference_and_history_separate(self):
        with patch('biotracebench_scoring.native_codex.export_native', return_value={'validation_status': 'exact_replay_passed'}) as export:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['native-export', '--plan', '/external/native', '--out', '/external/export',
                    '--historical', '/external/old.json', '--audit', '/external/reference.json',
                    '--audit-provenance', '/external/provenance.json', '--require-complete']), 0)
        export.assert_called_once_with('/external/native', '/external/export', historical='/external/old.json',
            audit='/external/reference.json', audit_provenance='/external/provenance.json', require_complete=True)


if __name__ == '__main__':
    unittest.main()
