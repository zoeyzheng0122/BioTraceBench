"""Read-only transport provenance, separate from model or scientific validity."""
from pathlib import Path

from ._json import digest, filehash, loads
from .contracts import VERSION

FILES = ('api-request.json', 'api-response.bin', 'api-http.json')


class ArchiveConflict(ValueError):
    """A local archive contradicts known request identity or saved checksums."""
    def __init__(self, assessment):
        self.assessment = assessment
        super().__init__('Local API archive conflict: '+ '; '.join(assessment['reasons']))


def inspect(folder, profile, request, body):
    folder = Path(folder)
    reasons, conflicts = [], []
    result = {'status':'unverified', 'reasons':reasons,
              'request_hash':digest(request), 'profile_hash':digest(profile)}
    try:
        frozen = loads((folder/'api-request.json').read_text(encoding='utf-8'))
    except (OSError, ValueError, UnicodeError):
        frozen = None
    if not isinstance(frozen, dict):
        conflicts.append('Archived request identity is unavailable')
    else:
        if frozen.get('profile') != profile or frozen.get('request_hash') != digest(request):
            conflicts.append('API request/profile identity changed')
        if frozen.get('body') != body or frozen.get('protocol_version') != request['protocol_version']:
            conflicts.append('Archived API wire/schema identity changed')
        if (frozen.get('version') != VERSION or frozen.get('endpoint') != profile['endpoint']
                or frozen.get('images') != request.get('images', [])):
            conflicts.append('Archived API transport metadata identity changed')
    path = folder/'transport-receipt.json'
    stamp = None
    if not path.exists():
        reasons.append('Transport receipt is missing')
    else:
        try:
            stamp = loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError, UnicodeError):
            reasons.append('Transport receipt is unreadable')
        if not isinstance(stamp, dict):
            reasons.append('Transport receipt is not a complete object')
            stamp = None
    if stamp is not None:
        for key, expected in (('provider','api'), ('profile_hash',digest(profile)),
                              ('request_hash',digest(request))):
            if key not in stamp:
                reasons.append('Transport receipt lacks '+key)
            elif stamp[key] != expected:
                conflicts.append('API receipt '+key+' identity changed')
        hashes = stamp.get('files')
        if not isinstance(hashes, dict):
            reasons.append('Transport receipt lacks file checksums')
        else:
            if set(hashes) != set(FILES):
                reasons.append('Transport receipt does not cover exactly the three transport files')
            # Never follow paths provided by the receipt.
            for name in FILES:
                if name not in hashes:
                    continue
                checksum = hashes[name]
                if not isinstance(checksum, str) or len(checksum) != 64 or any(c not in '0123456789abcdef' for c in checksum):
                    reasons.append('Transport receipt has an invalid checksum for '+name)
                elif not (folder/name).is_file() or filehash(folder/name) != checksum:
                    conflicts.append('API archive identity changed: '+name)
    if conflicts:
        result.update(status='conflict', reasons=conflicts+reasons)
    elif not reasons:
        result['status'] = 'verified'
    return result
