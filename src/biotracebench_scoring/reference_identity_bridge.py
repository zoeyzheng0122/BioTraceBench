"""Validate a source-authored bridge between two reference inventories.

This module validates explicit decisions; it does not decide scientific
identity, transfer marks, or alter either inventory.
"""
from model_conversation.archive import digest

FORMAT = 'biotracebench-reference-identity-bridge-1'


def _rows(inventory):
    selected = [row for row in inventory['rows'] if row['side'] == 'reference']
    rows = {row['id']: row for row in selected}
    if len(rows) != len(selected):
        raise ValueError('Duplicate reference row identity')
    cells = {row_id: {} for row_id in rows}
    for cell in inventory['cells']:
        if cell['side'] != 'reference':
            continue
        if cell['row'] not in rows or cell['field'] in cells[cell['row']]:
            raise ValueError('Invalid reference cell binding')
        cells[cell['row']][cell['field']] = cell
    return rows, cells


def _evidence(item, sources):
    source_id, quote = item.get('source_id'), item.get('quote')
    if (not isinstance(source_id, str) or not isinstance(quote, str) or not quote.strip()
            or source_id not in sources or quote not in sources[source_id]):
        raise ValueError('Bridge decision requires an exact frozen source quote')
    if not isinstance(item.get('reason'), str) or not item['reason'].strip():
        raise ValueError('Bridge decision requires an explicit scientific reason')


def _scientific(cell):
    return {k: v for k, v in cell.items() if k not in ('id', 'row', 'row_index')}


def validate_reference_bridge(before, after, sources, bridge):
    """Check one-to-one identity, evidence, and an exact inventory change list.

    The author supplies all pairs, additions and removals. Unchanged scientific
    fields anchor each pair; changed fields must be individually declared with
    exact old/new inventory attributes. Sources are the frozen task excerpts.
    """
    if bridge.get('format') != FORMAT:
        raise ValueError('A versioned reference identity bridge is required')
    if bridge.get('before_identity') != digest(before) or bridge.get('after_identity') != digest(after):
        raise ValueError('Reference inventory identity mismatch')
    author = bridge.get('author', {})
    if (author.get('kind') != 'native_codex' or
            any(not isinstance(author.get(k), str) or not author[k].strip()
                for k in ('agent_id', 'session_id'))):
        raise ValueError('Bridge requires an attributable native Codex author')
    for key in ('rows', 'cells'):
        if [x for x in before[key] if x['side'] == 'prediction'] != [
                x for x in after[key] if x['side'] == 'prediction']:
            raise ValueError('Reference bridge cannot change submitted output inventory')
    if before['diagnostics'] != after['diagnostics']:
        raise ValueError('Reference bridge cannot change submission diagnostics')
    source_map = {}
    for source in sources:
        if source['id'] in source_map or not isinstance(source.get('text'), str):
            raise ValueError('Frozen source identities must be unique and readable')
        source_map[source['id']] = source['text']
    old_rows, old_cells = _rows(before)
    new_rows, new_cells = _rows(after)
    seen_old, seen_new = set(), set()
    for pair in bridge.get('pairs', []):
        old, new = pair.get('before'), pair.get('after')
        if old not in old_rows or new not in new_rows or old in seen_old or new in seen_new:
            raise ValueError('Reference pairs must be unique and one-to-one')
        if any(old_rows[old].get(k) != new_rows[new].get(k) for k in ('table','declared_table')):
            raise ValueError('Reference pairs must preserve the object table')
        seen_old.add(old); seen_new.add(new); _evidence(pair, source_map)
        a, b = old_cells[old], new_cells[new]
        anchors = pair.get('anchors')
        if not isinstance(anchors, list) or not anchors or len(set(anchors)) != len(anchors):
            raise ValueError('Paired records need distinct scientific identity anchors')
        for field in anchors:
            if (field not in a or field not in b or a[field]['role'] != 'scientific'
                    or not a[field]['nonempty'] or _scientific(a[field]) != _scientific(b[field])):
                raise ValueError('Identity anchors must be unchanged nonempty scientific fields')
        actual = {field for field in set(a) | set(b)
                  if field not in a or field not in b or _scientific(a[field]) != _scientific(b[field])}
        declared = pair.get('changes', [])
        if len({change['field'] for change in declared}) != len(declared) or {x['field'] for x in declared} != actual:
            raise ValueError('Reference cell changes must be declared exactly')
        for change in declared:
            field = change['field']; _evidence(change, source_map)
            if (change.get('before') != (_scientific(a[field]) if field in a else None)
                    or change.get('after') != (_scientific(b[field]) if field in b else None)):
                raise ValueError('Declared reference cell values do not match inventories')
    for name, rows, seen in (('removed', old_rows, seen_old), ('added', new_rows, seen_new)):
        for item in bridge.get(name, []):
            row = item.get('row')
            if row not in rows or row in seen:
                raise ValueError('Added or removed reference row is invalid or duplicated')
            _evidence(item, source_map); seen.add(row)
        if seen != set(rows):
            raise ValueError('Bridge must account for every reference row')
    return {'before_identity': digest(before), 'after_identity': digest(after),
            'pairs': len(bridge.get('pairs', [])), 'removed': len(bridge.get('removed', [])),
            'added': len(bridge.get('added', []))}
