"""Assemble complete prepared task inputs without external access."""
from .common import Stop, encoded, read, sha
from pathlib import Path
import base64
from .prompts import INITIAL
from .submission import schema as submission_schema


def capacity_precheck(reader, model, delivery=None):
    """Reject proven capacity failures before reading text or encoding images."""
    from model_conversation.input_limits import check
    images = []
    lower = sum(e.get('text_bytes', 0) for e in reader.entries.values())
    for entry in reader.entries.values():
        for image in entry['images']:
            mapped = (delivery or {}).get('images', {}).get(image['sha256'], {})
            inline = 'file_id' not in mapped
            meta = {**image, **{k: mapped[k] for k in ('width', 'height', 'bytes') if k in mapped}, 'inline': inline}
            if inline and mapped.get('path'):
                meta['bytes'] = Path(mapped['path']).stat().st_size
            if inline:
                lower += 4 * ((meta['bytes'] + 2) // 3)
            meta['encoded_bytes'] = 4 * ((meta['bytes'] + 2) // 3) if inline else 0
            images.append(meta)
    limits = model.get('api_limits', {})
    if check({'images': images}, limits) or lower > min(model['max_request_bytes'], limits.get('max_request_bytes', model['max_request_bytes'])):
        raise Stop('paused_capacity', 'Prepared metadata proves input capacity is exceeded; no truncation')

def corpus(reader):
    result = {'instruction': (reader.folder/'instruction.md').read_text()}
    for mid, entry in sorted(reader.entries.items()):
        path = reader.folder/mid/'content.txt'
        if path.exists():
            with path.open(encoding="utf-8", newline="") as stream:
                result[mid] = stream.read()
        elif entry.get('text_characters') or not entry.get('images'):
            raise Stop('blocked_materials', 'Missing complete representation: '+mid)
    return result


def image_part(reader, mid, index, delivery):
    meta = dict(reader.entries[mid]['images'][index])
    mapping = (delivery or {}).get('images', {}).get(meta['sha256'])
    if not mapping:
        meta, image = reader.image(mid, index)
        return meta, {'type': 'image_url', 'image_url': {'url': image}}
    path = Path(mapping['path'])
    if sha(path) != mapping['sha256']:
        raise Stop('tampered', 'Approved delivery image changed')
    if getattr(reader, 'manifest', {}).get('shared_inputs'):
        if mapping['sha256'] != meta['sha256'] or any(mapping.get(k) != meta[k] for k in ('width', 'height')):
            raise Stop('blocked_identity', 'Shared comparison forbids model-specific image transformations')
    else:
        meta['delivery'] = {k: mapping[k] for k in ('sha256', 'width', 'height', 'file_id') if k in mapping}
    if 'file_id' in mapping:
        return meta, {'type': 'file', 'file_id': mapping['file_id']}
    return meta, {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode()}}


def messages(reader, neutral=INITIAL, delivery=None, *, image_loader=image_part):
    texts=corpus(reader)
    parts=[{'type':'text','text':'Task instructions:\n'+texts.pop('instruction')},
           {'type':'text','text':"Complete transport schema (the entire response):\n"+
            encoded(submission_schema(read(reader.folder/'schema.json'))).decode()+
            "\nThe response has exactly database and annotations. Task instructions about direct root arrays, "
            "no wrapper or complete-response validation apply to the database member only. "
            "The schema under properties.database is the unchanged business schema."},
           {'type':'text','text':'Field dictionary:\n'+encoded(read(reader.folder/'dictionary.json')).decode()}]
    for mid, entry in sorted(reader.entries.items()):
        parts.append({'type':'text','text':'Material identity and location:\n'+encoded(entry).decode()})
        if entry['format'] == '.pdf':
            for page in entry['pdf']['pages']:
                start, end = page['text_start'], page['text_end']
                parts.append({'type': 'text', 'text': f"Material {mid}; PDF page {page['page']}; text characters {start}:{end}:\n" + texts[mid][start:end]})
                meta, part = image_loader(reader, mid, page['image_index'], delivery)
                parts.extend([{'type': 'text', 'text': 'PDF page location and image:\n' + encoded(meta).decode()},
                              part])
            continue
        if mid in texts:
            parts.append({'type':'text','text':f'Material {mid}; full text; original character offset 0:\n'+texts[mid]})
        for index in range(len(entry['images'])):
            meta,part=image_loader(reader,mid,index,delivery)
            parts.extend([{'type':'text','text':f'Material {mid}; image {index}:\n'+encoded(meta).decode()},
                          part])
    return [{'role':'system','content':neutral},{'role':'user','content':parts}]
