import copy
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from model_conversation.archive import read,sha,write
from biotracebench_scoring import native_codex as native
from biotracebench_scoring import native_i0_export
from test_native_codex import NativeCodexTests,ACTOR,fixture_reply
import test_native_adjudication as source_fixture


class InitialOutputExportTests(unittest.TestCase):
    def test_only_i0_jobs_replayed_and_other_stage_remains_untouched(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);inv,policy,_=NativeCodexTests().fixture(root)
            changed=copy.deepcopy(inv)
            cell=next(c for c in changed['cells'] if c['side']=='prediction' and c['field']=='value')
            cell['value_json']='6'
            packet=root/'archive/gsr.json.gz';packet.write_bytes(gzip.compress(json.dumps({'inventory':changed}).encode()))
            manifest=read(root/'archive/manifest.json');manifest['positions'][1]['judgment']='gsr.json.gz';manifest['files']['gsr.json.gz']=sha(packet);write(root/'archive/i0test.json',manifest)
            native.prepare_native(root/'archive/i0test.json',root/'contexts.json',root/'new-plan')
            routes=read(root/'new-plan/private/routes.json');initial=next(r['job_id'] for r in routes if r['condition']=='i0');other=next(r['job_id'] for r in routes if r['condition']=='gsr');self.assertNotEqual(initial,other)
            reply=fixture_reply(inv,policy)
            for phase in ('first','review'):
                self.assertEqual(native.ingest_native(root/'new-plan',initial,reply,ACTOR,phase=phase)['status'],'accepted')
            with patch.object(native,'_recheck_attempts',wraps=native._recheck_attempts) as check:
                out=native_i0_export.export_i0(root/'new-plan',root/'scoped')
            self.assertEqual({call.args[1] for call in check.call_args_list},{initial})
            data=read(out['path']);self.assertEqual(len(data['positions']),1)
            self.assertEqual((data['positions'][0]['identity']['condition'],data['positions'][0]['status']),('i0','complete'))
            self.assertTrue(all(sha(path)==value for path,value in data['source_sha256'].items()))
            self.assertFalse((root/'new-plan/imports'/other).exists())

    def test_changed_routes_are_rejected_even_for_unselected_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);NativeCodexTests().fixture(root)
            path=root/'plan/private/routes.json';routes=read(path);routes[1]['model']='tampered';write(path,routes)
            with self.assertRaisesRegex(ValueError,'route coverage or identity'):
                native_i0_export.export_i0(root/'plan',root/'out')

    def test_i0_export_replays_source_adjudication_and_preserves_base_score(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);helper=source_fixture.NativeAdjudicationTests()
            _,_,reply=helper.fixture(root);helper.append(root,helper.changed(reply))
            data=read(native_i0_export.export_i0(root/'plan',root/'out',adjudications=root/'corrections')['path'])
            self.assertEqual(len(data['positions']),1)
            row=data['positions'][0]
            self.assertEqual(row['score']['field']['tp'],1)
            self.assertEqual(row['base_score']['field']['tp'],2)
            self.assertEqual(row['selected_judgment']['phase'],'source_adjudication')
            self.assertTrue(all(sha(path)==value for path,value in data['source_sha256'].items()))
