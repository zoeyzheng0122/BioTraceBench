"""Freeze-before-send and archive-before-parse, with network-free recovery."""
import json
import os
import time
from http.client import HTTPException
from pathlib import Path

from ._json import digest, filehash, read, write
from ._json import loads
from . import http
from . import dispatch
from .config import load_profile
from .contracts import ApiFailure, VERSION
from .protocols import request_body, response_value
from .archive_integrity import ArchiveConflict, inspect


def redact_json(value,key,depth=0):
    """Sanitize decoded strings, including JSON embedded inside model text."""
    if isinstance(value,str):
        replaced=value.replace(key,'[REDACTED]')
        if replaced!=value:return replaced
        if depth<20:
            try:nested=loads(value)
            except (ValueError,RecursionError):return value
            sanitized=redact_json(nested,key,depth+1)
            if sanitized!=nested:return json.dumps(sanitized,ensure_ascii=False,separators=(',',':'))
        return value
    if isinstance(value,list):return [redact_json(v,key,depth+1) for v in value]
    if isinstance(value,dict):return {k.replace(key,'[REDACTED]'):redact_json(v,key,depth+1) for k,v in value.items()}
    return value


def safe_response(raw,key):
    try:
        value=loads(raw.decode('utf-8'));sanitized=redact_json(value,key)
        if sanitized!=value:return json.dumps(sanitized,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    except (UnicodeError,ValueError,RecursionError):pass
    return raw.replace(key.encode(),b'[REDACTED]').replace(json.dumps(key,ensure_ascii=True)[1:-1].encode(),b'[REDACTED]')


class Backend:
    def __init__(self,profile,*,sender=None):
        self.profile=load_profile(profile)
        self.sender=sender or http.send

    def describe(self):
        return self.profile.identity()

    def preflight(self,request):
        return request_body(self.profile,request)

    def _send_values(self,request):
        body=self.preflight(request);p=self.profile.value
        key=os.environ.get(p['key_env'])
        if not key:raise ApiFailure('missing credential environment variable: '+p['key_env'],'paused_account','account','credential')
        if any(ord(c)<32 or ord(c)==127 for c in key):raise ApiFailure('invalid credential header value','paused_account','account','credential')
        try:key.encode('latin-1')
        except UnicodeError:raise ApiFailure('invalid credential header encoding','paused_account','account','credential') from None
        # A credential value accidentally included by the caller must never become a snapshot.
        encoded=json.dumps(body,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')
        if redact_json(body,key)!=body or key in p['endpoint']:raise ApiFailure('credential appears in request content','failed_validation')
        return body,encoded,key

    def check_send(self,request):
        """Local readiness only; preflight and offline recovery remain credential-free."""
        try:self._send_values(request)
        except Exception as error:
            error.dispatch_state='not_sent'
            raise

    def prepare_send(self,request,attempt_dir):
        self.check_send(request)
        dispatch.prepare(attempt_dir,dispatch.preparation(self.profile.value,request,self.preflight(request)))

    def invoke(self,request,attempt_dir):
        folder=Path(attempt_dir);body,encoded,key=self._send_values(request);p=self.profile.value
        expected=dispatch.preparation(p,request,body)
        dispatch.prepare(folder,expected)
        if dispatch.state(folder,expected)!='not_sent':
            raise ApiFailure('attempt already reserved; recover or use a new attempt directory')
        marker=folder/'api-request.json'
        frozen={'version':VERSION,'profile':p,'request_hash':digest(request),'protocol_version':request['protocol_version'],
                'endpoint':p['endpoint'],'body':body,'images':request.get('images',[])}
        # Exclusive creation also prevents concurrent direct callers from submitting twice.
        if marker.exists():
            if read(marker)!=frozen:raise ValueError('Unsent API request identity changed')
        else:
            with marker.open('x',encoding='utf-8') as stream:
                stream.write(json.dumps(frozen,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
                stream.flush()
                os.fsync(stream.fileno())
        headers={'Content-Type':'application/json','Accept':'application/json'}
        if p['protocol']=='anthropic':headers.update({'x-api-key':key,'anthropic-version':p.get('api_version','2023-06-01')})
        elif p['protocol']=='gemini':headers['x-goog-api-key']=key
        else:headers['Authorization']='Bearer '+key
        dispatch.start(folder,expected)
        start=time.monotonic()
        try:
            status,response_headers,raw=self.sender(p['endpoint'],encoded,headers,p['timeout'])
        except (OSError,TimeoutError,HTTPException):
            raise ApiFailure('connection interrupted; execution or consumption unknown',
                             category='transport_interrupted') from None
        elapsed=round(time.monotonic()-start,6)
        # Exact bytes except a vendor echo of the credential; record the redaction explicitly.
        safe=safe_response(raw,key)
        raw_path=folder/'api-response.bin'
        allowed={'content-type','x-request-id','request-id','retry-after','x-ratelimit-remaining-requests'}
        saved_headers={k.lower():str(v).replace(key,'[REDACTED]') for k,v in response_headers.items() if k.lower() in allowed}
        write(folder/'api-http.json',{'status':status,'headers':saved_headers,'elapsed_seconds':elapsed,'credential_echo_redacted':raw!=safe})
        raw_temp=folder/'api-response.bin.tmp';raw_temp.write_bytes(safe);raw_temp.replace(raw_path)
        write(folder/'transport-receipt.json',{'provider':'api','profile_hash':digest(p),'request_hash':digest(request),
            'files':{name:filehash(folder/name) for name in ('api-request.json','api-response.bin','api-http.json')}})
        try:result=self.recover(request,folder)
        except ApiFailure as exc:
            if hasattr(exc,'response'):write(folder/'api-result.json',exc.response.as_dict())
            raise
        write(folder/'api-result.json',result.as_dict())
        return result

    def inspect_archive(self,request,attempt_dir):
        """Inspect local provenance without changing the archive or contacting a provider."""
        return inspect(attempt_dir,self.profile.value,request,self.preflight(request))

    def recover(self,request,attempt_dir):
        folder=Path(attempt_dir)
        if not (folder/'api-response.bin').exists() or not (folder/'api-http.json').exists():return None
        assessment=self.inspect_archive(request,folder)
        if assessment['status']=='conflict':raise ArchiveConflict(assessment)
        meta=read(folder/'api-http.json');raw=(folder/'api-response.bin').read_bytes();status=meta['status']
        try:value=loads(raw.decode('utf-8'))
        except (UnicodeError,ValueError):
            if status in {401,402,403}:raise ApiFailure('API credential or quota rejected (HTTP '+str(status)+')','paused_account','account','credential') from None
            raise ApiFailure('HTTP response is not a JSON envelope; see sanitized archive','failed_validation' if status==200 else 'paused_unknown') from None
        if not isinstance(value,dict):raise ApiFailure('HTTP envelope must be an object','failed_validation')
        if status!=200:
            error=value.get('error',{});code=(error.get('code') or error.get('type')) if isinstance(error,dict) else None
            if status in {401,402,403} or code in {'insufficient_quota','quota_exceeded','billing_hard_limit_reached'}:
                raise ApiFailure('API credential or quota rejected (HTTP '+str(status)+')','paused_account','account','credential')
            if status in {400,404,405,413,415,422}:raise ApiFailure('API model, parameters or capacity rejected (HTTP '+str(status)+')','paused_configuration','configuration')
            # Only documented rejection envelopes establish that inference was not accepted.
            if status==429 and code in {'rate_limit_exceeded','rate_limit_error'} or status==529 and code=='overloaded_error':
                raise ApiFailure('API explicitly rejected execution (HTTP '+str(status)+')','paused_service','service',retryable=True)
            raise ApiFailure('HTTP '+str(status)+'; execution or consumption unknown')
        try:
            result=response_value(self.profile,value,meta['headers'],meta['elapsed_seconds'],folder)
        except (KeyError,TypeError,AttributeError):raise ApiFailure('malformed provider envelope; original response archived','failed_validation') from None
        return result
