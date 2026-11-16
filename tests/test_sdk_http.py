import unittest
from unittest.mock import patch

from model_api.http import send


class HttpTests(unittest.TestCase):
    def test_http_boundary_does_not_follow_redirects_or_retry_and_uses_remaining_deadline(self):
        calls=[];timeouts=[]
        class Socket:
            def settimeout(self,value):timeouts.append(value)
        class Response:
            status=307
            def getheaders(self):return [('Location','https://another.invalid')]
            def read1(self,n):return b''
        class Connection:
            def __init__(self,host,port=None,timeout=None):self.sock=Socket();calls.append(('connect',host,port,timeout))
            def connect(self):pass
            def request(self,method,path,body=None,headers=None):calls.append((method,path,body,headers))
            def getresponse(self):return Response()
            def close(self):calls.append(('close',))
        with patch('model_api.http.http.client.HTTPSConnection',Connection),patch('model_api.http.time.monotonic',side_effect=[0,1,2,3]):
            status,headers,body=send('https://example.invalid/v1/responses',b'{}',{'Authorization':'Bearer test'},10)
        self.assertEqual(status,307);self.assertEqual(body,b'')
        self.assertEqual([r[0] for r in calls],['connect','POST','close'])
        self.assertEqual(timeouts,[9,8,7])


if __name__=='__main__':unittest.main()
