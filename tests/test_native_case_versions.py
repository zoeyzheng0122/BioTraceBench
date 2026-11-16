"""Whole-case version composition uses explicit scientific applicability only."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from model_conversation.archive import digest, read, sha, write
from biotracebench_scoring import native_codex as native
from biotracebench_scoring import native_case_versions as versions
import test_native_codex as fixtures


class NativeCaseVersionTests(unittest.TestCase):
    def fixture(self, root, *, finish=True, partial=False, change_value=False, change_domain=False,
                change_requirement=False):
        helper = fixtures.NativeCodexTests()
        task='Report Arm A. Value 5 is archival context, outside the required output.'
        inv, template, _ = helper.fixture(root,task_definition=task)
        helper.finish(root, inv, template)
        amended = copy.deepcopy(template)
        field = next(f for f in amended['fields'] if f['id']=='sample:0:value')
        field.update(applicable=False,required_assertions=[],applicability={
            'basis':'Synthetic scope review excludes reference-only background.',
            'reason':'This fixture quantity is not a required logical target.', 'source_ids':['source-a']})
        if change_requirement:
            label=next(f for f in amended['fields'] if f['id']=='sample:0:label')
            label['required_assertions'][0]['text']='A different scientific requirement.'
        contexts=read(root/'contexts.json');contexts['SYNTHETIC']['task_policy']=amended
        write(root/'amended-contexts.json',contexts)
        # The original scientific inventory is reused; only the task policy changes.
        manifest=read(root/'archive/manifest.json')
        if partial:manifest['positions']=manifest['positions'][:1]
        if change_domain:
            for p in manifest['positions']:p['domain']='clinical'
        if change_value:
            import gzip
            packet=root/'archive/changed.json.gz'
            altered=copy.deepcopy(inv)
            c=next(c for c in altered['cells'] if c['side']=='prediction' and c['field']=='value')
            c['value_json']='6'
            packet.write_bytes(gzip.compress(json.dumps({'inventory':altered}).encode()))
            manifest['files']['changed.json.gz']=sha(packet)
            for p in manifest['positions']:p['judgment']='changed.json.gz'
        write(root/'archive/amended-manifest.json',manifest)
        native.prepare_native(root/'archive/amended-manifest.json',root/'amended-contexts.json',root/'amended')
        new=read(root/'amended/plan.json');old=read(root/'plan/plan.json')
        patch={'format':versions.FORMAT,'case':'SYNTHETIC','base_plan_identity':old['identity'],
               'amendment_plan_identity':new['identity'],'excluded_fields':['sample:0:value'],
               'basis':'Synthetic field-scope correction.','task_quote':'Value 5 is archival context, outside the required output.'}
        write(root/'amendment.json',patch)
        if finish and not change_value:
            reply=fixtures.fixture_reply(inv,template)
            value=next(f for f in reply['fields'] if f['field_id']=='sample:0:value')
            cell=next(c for c in inv['cells'] if c['side']=='prediction' and c['field']=='value')
            value.update(prediction_evidence=[],assertions=[],verdict='not_scored')
            reply['unscored']=[{'cell':cell['id'],'field_id':'sample:0:value','category':'out_of_scope',
                               'basis':'Synthetic source-only exclusion.','reason':'Correct background, not a requested field.'}]
            for phase in ('first','review'):
                result=native.ingest_native(root/'amended','n-00001',reply,fixtures.ACTOR,phase=phase)
                self.assertEqual(result['status'],'accepted',result)
        return patch

    def amendment(self,root):
        return {'plan':str(root/'amended'),'manifest':str(root/'amendment.json')}

    def test_full_case_override_replays_and_preserves_original_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            before={p:p.read_bytes() for p in (root/'plan').rglob('*.json')}
            result=versions.compose_native(root/'plan',[self.amendment(root)],root/'composed',require_complete=True)
            data=read(result['path'])
            self.assertEqual((result['coverage'],result['positions'],result['amended_cases']),('complete',2,['SYNTHETIC']))
            self.assertTrue(all(p['score']['field']['gold']==1 for p in data['positions']))
            self.assertTrue(all(p['superseded_version']['score']['field']['gold']==2 for p in data['positions']))
            self.assertTrue(all(sha(path)==value for path,value in data['source_sha256'].items()))
            self.assertEqual(before,{p:p.read_bytes() for p in before})

    def test_pending_new_version_never_falls_back_to_old_complete_judgment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root,finish=False)
            result=versions.compose_native(root/'plan',[self.amendment(root)],root/'composed')
            self.assertEqual(result['coverage'],'incomplete')
            self.assertTrue(all(p['status']=='awaiting_first_pass' and p['score'] is None
                                for p in read(result['path'])['positions']))
            with self.assertRaisesRegex(ValueError,'incomplete'):
                versions.compose_native(root/'plan',[self.amendment(root)],root/'other',require_complete=True)

    def test_partial_case_stage_override_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root,partial=True)
            with self.assertRaisesRegex(ValueError,'every case'):
                versions.verify_amendment(root/'plan',root/'amended',root/'amendment.json')

    def test_original_input_and_domain_cannot_change(self):
        for change in ('change_value','change_domain'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.fixture(root,**{change:True})
                with self.assertRaisesRegex(ValueError,'changed'):
                    versions.verify_amendment(root/'plan',root/'amended',root/'amendment.json')

    def test_manifest_requires_actual_task_quote_and_exact_declared_field_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);patch=self.fixture(root)
            patch['task_quote']='An invented task instruction';write(root/'bad.json',patch)
            with self.assertRaisesRegex(ValueError,'literal frozen task'):
                versions.verify_amendment(root/'plan',root/'amended',root/'bad.json')
            patch=read(root/'amendment.json');patch['excluded_fields']=['sample:0:label'];write(root/'bad.json',patch)
            with self.assertRaises(ValueError):versions.verify_amendment(root/'plan',root/'amended',root/'bad.json')

    def test_duplicate_case_versions_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            with self.assertRaisesRegex(ValueError,'Duplicate'):
                versions.compose_native(root/'plan',[self.amendment(root)]*2,root/'bad')

    def test_exclusion_cannot_silently_change_another_scientific_requirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root,change_requirement=True)
            with self.assertRaisesRegex(ValueError,'undeclared scientific requirements'):
                versions.verify_amendment(root/'plan',root/'amended',root/'amendment.json')
