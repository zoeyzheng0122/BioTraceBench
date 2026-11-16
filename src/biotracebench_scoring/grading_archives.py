"""Persist provenance observations outside the original transport archive."""
from model_api.archive_integrity import ArchiveConflict
from model_conversation.archive import digest, event, read, write


def assessment_path(out, attempt):
    return out/'archive-checks'/(digest(attempt)+'.json')


def assess(out, transport, packet, folder):
    if not (folder/'api-response.bin').exists() or not (folder/'api-http.json').exists():
        return None
    attempt = str(folder.relative_to(out))
    inspector = getattr(transport, 'inspect_archive', None)
    observed = inspector(packet['request'], folder) if inspector else {
        'status':'unverified', 'reasons':['Backend does not expose transport provenance inspection']}
    path = assessment_path(out, attempt)
    prior = read(path) if path.exists() else None
    if prior and (prior['output'] != packet['id'] or prior['attempt'] != attempt
                  or prior['packet_identity'] != digest(packet)):
        raise ValueError('Saved archive assessment belongs to different grading inputs')
    saved = {'output':packet['id'], 'attempt':attempt, 'packet_identity':digest(packet),
             **observed, 'observed_status':observed['status']}
    if prior and prior['status'] in {'unverified', 'conflict'}:
        if observed['status'] != 'conflict':
            saved['status'] = prior['status']
        saved['reasons'] = list(dict.fromkeys(prior['reasons']+observed['reasons']))
    if saved != prior:
        write(path, saved)
        event(out, 'archive_integrity_observed', output=packet['id'], attempt=attempt,
              integrity=saved['status'], observed_status=observed['status'], reasons=saved['reasons'])
    if saved['status'] == 'conflict':
        raise ArchiveConflict(saved)
    return saved
