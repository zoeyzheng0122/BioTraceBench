"""One non-streaming POST, without redirects or hidden retries."""
import http.client
import time
from urllib.parse import urlsplit


def send(url,body,headers,timeout):
    target=urlsplit(url)
    if target.scheme!='https' or target.query or target.username or target.password:raise ValueError('credential-free HTTPS endpoint required')
    deadline=time.monotonic()+timeout
    connection=http.client.HTTPSConnection(target.hostname,port=target.port,timeout=timeout)
    def remaining():
        seconds=deadline-time.monotonic()
        if seconds<=0:raise TimeoutError('HTTP deadline exceeded')
        return seconds
    try:
        connection.connect();socket=connection.sock
        socket.settimeout(remaining())
        connection.request('POST',target.path or '/',body=body,headers=headers)
        socket.settimeout(remaining());response=connection.getresponse();pieces=[]
        while True:
            socket.settimeout(remaining());piece=response.read1(65536)
            if not piece:break
            pieces.append(piece)
        return response.status,dict(response.getheaders()),b''.join(pieces)
    finally:connection.close()
