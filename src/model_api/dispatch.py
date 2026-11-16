"""Durable local send boundary; absence is proof only with a new preparation."""
import json
import os
from pathlib import Path

from ._json import digest, loads

PROTOCOL = 'model-api-dispatch-1'
PREPARED = 'send-prepared.json'
STARTED = 'dispatch-started.json'


def _create(path, value):
    # Flush both the marker and its directory before any network sender can run.
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
        stream.flush()
        os.fsync(stream.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def preparation(profile, request, body):
    return {'protocol':PROTOCOL, 'profile_hash':digest(profile),
            'request_hash':digest(request), 'body_hash':digest(body)}


def state(folder, expected=None):
    """Never infer zero consumption merely from an absent response or old marker."""
    folder = Path(folder)
    prepared, started = folder/PREPARED, folder/STARTED
    if not prepared.exists():
        if started.exists():
            raise ValueError('Dispatch marker has no matching preparation')
        return 'legacy_unknown'
    stamp = loads(prepared.read_text(encoding='utf-8'))
    if (not isinstance(stamp, dict) or set(stamp) != {'protocol','profile_hash','request_hash','body_hash'}
            or stamp.get('protocol') != PROTOCOL or expected is not None and stamp != expected
            or any(not isinstance(stamp[k],str) or len(stamp[k]) != 64
                   or any(c not in '0123456789abcdef' for c in stamp[k])
                   for k in ('profile_hash','request_hash','body_hash'))):
        raise ValueError('Send preparation identity changed')
    if started.exists():
        marker = loads(started.read_text(encoding='utf-8'))
        if marker != {'protocol':PROTOCOL, 'preparation_identity':digest(stamp)}:
            raise ValueError('Dispatch/preparation identity changed')
        return 'may_have_been_sent'
    if any((folder/name).exists() for name in
           ('api-response.bin','api-http.json','transport-receipt.json','api-result.json','network-interruption.json')):
        raise ValueError('Response/interruption contradicts the not-sent preparation')
    frozen = folder/'api-request.json'
    if frozen.exists():
        value = loads(frozen.read_text(encoding='utf-8'))
        if (not isinstance(value,dict) or value.get('request_hash') != stamp['request_hash']
                or digest(value.get('profile')) != stamp['profile_hash']
                or digest(value.get('body')) != stamp['body_hash']):
            raise ValueError('Unsent request/preparation identity changed')
    return 'not_sent'


def prepare(folder, expected):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder/PREPARED
    if path.exists():
        state(folder, expected)
    else:
        # Do not retrofit new zero-consumption proof onto old ambiguous attempts.
        if any((folder/name).exists() for name in
               ('api-request.json',STARTED,'api-response.bin','api-http.json','transport-receipt.json')):
            raise ValueError('Existing API attempt lacks send preparation; no resend')
        _create(path, expected)


def start(folder, expected):
    folder = Path(folder)
    if state(folder, expected) != 'not_sent':
        raise ValueError('API send already started; recover instead of resending')
    _create(folder/STARTED, {'protocol':PROTOCOL, 'preparation_identity':digest(expected)})
