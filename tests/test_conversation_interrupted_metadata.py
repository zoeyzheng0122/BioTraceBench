"""Keep observed HTTP evidence without promoting an incomplete stream to success."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from model_conversation import Conversation, Stop
from model_conversation.archive import read, verify
from model_conversation.streaming import Interrupted
from test_deepseek_conversation import config


class InterruptedMetadataTests(unittest.TestCase):
    def test_observed_http_and_partial_stream_are_safely_archived_without_retry(self):
        calls=[]
        def sender(*args):
            calls.append(args)
            raise Interrupted(b'data: synthetic-key\n\n',200,
                {'Content-Type':'text/event-stream','X-Request-ID':'synthetic-key-id','Authorization':'not-for-archive'})
        messages=[{'role':'user','content':'Return JSON'}]
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{'DEEPSEEK_API_KEY':'synthetic-key'}):
            folder=Path(temp)/'call';client=Conversation(config(),sender=sender)
            with self.assertRaises(Stop) as caught:client.invoke(messages,[],folder)
            self.assertEqual(caught.exception.status,'paused_unknown')
            verify(folder)
            metadata=read(folder/'http.json')
            self.assertEqual(metadata['status'],200)
            self.assertFalse(metadata['response_complete'])
            self.assertTrue(metadata['credential_echo_redacted'])
            self.assertNotIn('authorization',metadata['headers'])
            self.assertNotIn('synthetic-key',(folder/'http.json').read_text())
            self.assertNotIn(b'synthetic-key',(folder/'partial-stream.bin').read_bytes())
            self.assertEqual(read(folder/'failure.json')['consumption'],'unknown')
            with patch.dict(os.environ,{},clear=True), self.assertRaises(Stop):client.recover(messages,[],folder)
            self.assertEqual(len(calls),1)

    def test_no_http_status_is_invented_before_response_headers(self):
        def sender(*args):raise Interrupted(b'',None,{})
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{'DEEPSEEK_API_KEY':'synthetic-key'}):
            folder=Path(temp)/'call'
            with self.assertRaises(Stop):Conversation(config(),sender=sender).invoke([{'role':'user','content':'JSON'}],[],folder)
            verify(folder)
            self.assertFalse((folder/'http.json').exists())
            self.assertEqual(read(folder/'failure.json')['execution'],'unknown')


if __name__=='__main__':unittest.main()
