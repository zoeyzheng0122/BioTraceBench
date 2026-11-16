"""DeepSeek delivery, upload, token and provisional-scoring boundaries offline."""
import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PIL import Image
from model_conversation import Conversation, Stop
from model_conversation.archive import encoded, read, sha
from model_conversation.files import upload
from model_conversation.token_count import count


def config():
    return {'provider': 'deepseek', 'protocol': 'chat_completions', 'key_env': 'DEEPSEEK_API_KEY',
            'endpoint': 'https://api.deepseek.com/chat/completions', 'model': 'deepseek-flash',
            'accepted_response_models': ['deepseek-flash'], 'timeout': 900, 'retries': 0,
            'context_tokens': 1048576, 'max_output_tokens': 32768, 'max_request_bytes': 50331648,
            'generation': {'reasoning_effort': 'high'}, 'output_token_field': 'max_tokens',
            'capabilities': {'vision': True, 'tools': False, 'json_object': True},
            'estimator': {'kind': 'fixed_upper_bound', 'input_tokens': 10000, 'basis': 'Synthetic test'},
            'file_expiries': {'file-api-test': 4102444800}}


class DeepSeekTests(unittest.TestCase):
    def test_native_files_and_history_survive_offline_recovery(self):
        calls = []
        def send(endpoint, body, headers, timeout):
            calls.append(json.loads(body))
            return 200, {}, encoded({'model': 'deepseek-flash', 'choices': [{'message': {
                'role': 'assistant', 'content': '{"ok":true}', 'reasoning_content': 'native reasoning'}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'prompt_cache_hit_tokens': 0}})
        messages = [{'role': 'user', 'content': [{'type': 'text', 'text': 'Return JSON'}, {'type': 'file', 'file_id': 'file-api-test'}]}]
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'synthetic-key'}):
            client = Conversation(config(), sender=send)
            result = client.invoke(messages, [], Path(temp) / 'call')
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(client.recover(messages, [], Path(temp) / 'call'), result)
            self.assertEqual(result['message']['reasoning_content'], 'native reasoning')
            self.assertEqual(len(calls), 1)
            self.assertNotIn('tools', calls[0])
            bad = config(); bad['file_expiries']['file-api-test'] = 1
            with self.assertRaises(Stop):
                Conversation(bad, sender=lambda *a: self.fail('Expired files must not invoke')).invoke(messages, [], Path(temp) / 'expired')

    def test_other_providers_and_undeclared_file_ids_are_rejected(self):
        messages = [{'role': 'user', 'content': [{'type': 'file', 'file_id': 'file-api-test'}]}]
        bad = config(); bad['file_expiries'] = {}
        with self.assertRaises(ValueError):Conversation(bad).preflight(messages, [])
        bad = config(); bad.update(provider='qwen', key_env='DASHSCOPE_API_KEY'); bad.pop('file_expiries')
        with self.assertRaises(ValueError):Conversation(bad).preflight(messages, [])

    def test_projected_image_identity_is_verified_and_source_is_preserved(self):
        from types import SimpleNamespace
        from biotracebench.inputs import image_part
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'copy.png'; Image.new('RGB', (100, 50), 'red').save(path)
            original = {'sha256': 'original-source', 'width': 200, 'height': 100, 'path': 'original.png'}
            reader = SimpleNamespace(entries={'m1': {'images': [original]}})
            mapping = {'images': {'original-source': {'path': str(path), 'sha256': sha(path), 'width': 100,
                                                      'height': 50, 'file_id': 'file-api-test'}}}
            meta, part = image_part(reader, 'm1', 0, mapping)
            self.assertEqual(part, {'type': 'file', 'file_id': 'file-api-test'})
            self.assertEqual(meta['width'], 200)
            self.assertEqual(meta['delivery']['width'], 100)
            self.assertNotIn('delivery', original)
            self.assertNotIn('path', meta['delivery'])
            path.write_bytes(b'changed')
            with self.assertRaises(Stop):image_part(reader, 'm1', 0, mapping)

    def test_upload_is_cached_expires_and_does_not_retry(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'synthetic-key'}):
            root = Path(temp); image = root / 'image.png'; Image.new('RGB', (10, 10), 'red').save(image)
            calls = []
            def sender(endpoint, body, headers, timeout):
                calls.append(body)
                self.assertIn(b'name="expires_after[seconds]"\r\n\r\n86400', body)
                self.assertIn(b'name="purpose"\r\n\r\nuser_data', body)
                return 200, {}, encoded({'id': 'file-api-test', 'bytes': image.stat().st_size, 'purpose': 'user_data',
                                        'created_at': int(time.time()), 'expires_at': int(time.time()) + 86400})
            first = upload(image, root / 'upload', sender=sender)
            self.assertEqual(upload(image, root / 'upload', sender=lambda *a: self.fail('No duplicate upload')), first)
            self.assertEqual(len(calls), 1)
            with patch('model_conversation.files.time.time', return_value=4102444800), self.assertRaises(Stop):
                upload(image, root / 'upload', sender=sender)
            def broken(*args):raise TimeoutError()
            with self.assertRaises(Stop):upload(image, root / 'failed', sender=broken)
            with self.assertRaises(Stop):upload(image, root / 'failed', sender=lambda *a: self.fail('No retry'))

    def test_local_count_includes_native_reasoning_and_images_without_base64_tokens(self):
        from tokenizers import Tokenizer, models, pre_tokenizers
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'tokenizer.json'
            tokenizer = Tokenizer(models.WordLevel({'[UNK]': 0, 'hello': 1, 'reason': 2}, unk_token='[UNK]'))
            tokenizer.pre_tokenizer = pre_tokenizers.Whitespace(); tokenizer.save(str(path))
            policy = {'kind': 'local_tokenizer', 'path': str(path), 'sha256': sha(path), 'image_token_upper': 1024,
                      'reserve_tokens': 4096, 'basis': 'Synthetic tokenizer'}
            body = {'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': 'hello'}, {'type': 'file', 'file_id': 'file-api-test'}]},
                                 {'role': 'assistant', 'content': 'hello', 'reasoning_content': 'reason'}]}
            result = count(body, policy)
            self.assertEqual(result['text_tokens'], 3)
            self.assertEqual(result['reserved_input_tokens'], 3 + 1024 + 4096)
            c = config(); c['estimator'] = policy
            client = Conversation(c)
            messages = body['messages']
            first = client.estimate(messages, [], Path(temp) / 'estimate')
            with patch('model_conversation.token_count.count', side_effect=AssertionError('Offline replay must use receipt')):
                self.assertEqual(client.estimate(messages, [], Path(temp) / 'estimate', offline=True), first)
            path.write_text('{}')
            with self.assertRaises(Stop):count(body, policy)

    def test_draft_scoring_is_explicit_and_cannot_be_reported_as_frozen(self):
        from biotracebench_scoring.evaluation import score
        from test_biotracebench_scoring_items import POLICY, DICT, GOLD
        policy = copy.deepcopy(POLICY); policy['frozen'] = False
        with self.assertRaises(ValueError):score(GOLD, GOLD, DICT, policy)
        result = score(GOLD, GOLD, DICT, policy, allow_unfrozen=True)
        original = score(GOLD, GOLD, DICT, POLICY)
        self.assertEqual(result['field'], original['field'])
        self.assertEqual(result['record'], original['record'])
        self.assertEqual(result['status'], 'provisional')
        self.assertFalse(result['policy_frozen'])
        self.assertFalse(policy['frozen'])


if __name__ == '__main__':unittest.main()
