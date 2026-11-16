"""Scientific identities independent of a grader's current record mapping.

Only declared internal identifiers are removed. Native scientific accessions,
states, times and values remain evidence; source aliases affect context only.
Ambiguous identities never establish a reusable complete alignment.
"""
import json
from collections import Counter, defaultdict
from model_conversation.archive import digest, encoded
from .scoring_input import strict_json


def scope(packet):
    p = packet['request']['payload']
    return {'binding': packet.get('consistency_scope', {}),
            'task': p['task_definition'], 'dictionary': p['dictionary_json'],
            'policy': p['scoring_policy_json'], 'sources': p['sources'],
            'aliases': p.get('consistency_memory', {}).get('context_aliases', [])}


def _cyclic_schema(dictionary):
    active, done = set(), set()
    def visit(table):
        if table in active:return True
        if table in done:return False
        active.add(table)
        if any(visit(target) for target in dictionary[table].get('references', {}).values()
               if target in dictionary):return True
        active.remove(table); done.add(table)
        return False
    return any(visit(table) for table in dictionary)


class Context:
    def __init__(self, packet, records=()):
        self.packet = packet
        self.dictionary = json.loads(packet['request']['payload']['dictionary_json'])
        self.cyclic_schema = _cyclic_schema(self.dictionary)
        self.rows = {r['id']: r for r in packet['inventory']['rows']}
        self.cells = defaultdict(list)
        for c in packet['inventory']['cells']:
            self.cells[c['row']].append(c)
        self.mapped = {r['prediction_row']: r['reference_row'] for r in records
                       if r['verdict'] == 'matched'}
        self.locations = {rid: (r['table'], r['row_index']) for rid, r in self.rows.items()
                          if r['side'] == 'reference'}
        aliases = packet['request']['payload'].get('consistency_memory', {}).get('context_aliases', [])
        self.aliases = {(a['table'], a['field'], v): min(a['values'])
                        for a in aliases for v in a['values']}
        ids = defaultdict(list)
        self.identifier_keys = {}
        for rid, row in self.rows.items():
            field = self.dictionary.get(row['table'], {}).get('identifier')
            c = next((c for c in self.cells[rid] if c['field'] == field and c['nonempty']), None)
            if c:
                key = (row['side'], row['table'], c['value_json'])
                ids[key].append(rid)
                self.identifier_keys[rid] = key
        self.targets = {k: values[0] for k, values in ids.items() if len(values) == 1}
        self.duplicate_ids = {k for k, values in ids.items() if len(values) != 1}
        self.edges = {}
        self.unresolved = set()
        for rid, row in self.rows.items():
            refs = self.dictionary.get(row['table'], {}).get('references', {})
            edges = {}
            for c in self.cells[rid]:
                if c['field'] not in refs or not c['nonempty']:
                    continue
                raw = strict_json(c['value_json'])
                values = raw if isinstance(raw, list) else [raw]
                endpoints = [self.targets.get((row['side'], refs[c['field']], encoded(v).decode()))
                             for v in values]
                if any(x is None for x in endpoints):
                    self.unresolved.add(rid)
                edges[c['field']] = endpoints
            self.edges[rid] = edges
        # Schema-bound depth is independent of row order, arbitrary IDs and
        # unrelated row counts. Indistinguishable/duplicate objects are refused.
        colors = {rid: digest(self.normalized(rid, lambda target: self.rows[target]['table']))
                  for rid in self.rows}
        for _ in range(len(self.dictionary) + 1):
            colors = {rid: digest(self.normalized(rid, lambda target: colors[target]))
                      for rid in self.rows}
        counts = Counter((r['side'], r['table'], colors[rid]) for rid, r in self.rows.items())
        self.objects = {}
        for rid, row in self.rows.items():
            content = any(c['nonempty'] and c['role'] not in
                          {'identifier', 'provenance', 'out_of_scope'} for c in self.cells[rid])
            if (content and rid not in self.unresolved
                    and self.identifier_keys.get(rid) not in self.duplicate_ids
                    and counts[(row['side'], row['table'], colors[rid])] == 1):
                self.objects[rid] = colors[rid]

    def normalized(self, rid, resolve):
        row = self.rows[rid]
        fields = []
        for c in self.cells[rid]:
            if c['role'] in {'identifier', 'provenance', 'out_of_scope'}:
                continue
            text = self.aliases.get((row['table'], c['field'], c['value_json']), c['value_json'])
            endpoints = self.edges.get(rid, {}).get(c['field'])
            if endpoints and all(x is not None for x in endpoints):
                tokens = [resolve(x) for x in endpoints]
                if all(x is not None for x in tokens):
                    text = {'association_targets': sorted(tokens, key=digest)}
            fields.append((c['field'], c['role'], c['present'], text))
        return {'table': row['table'], 'fields': sorted(fields)}

    def input_identity(self):
        if (len(self.objects) != len(self.rows) or self.duplicate_ids
                or self.unresolved or self.cyclic_schema):
            return None
        return digest({'scope': scope(self.packet), 'objects': {
            side: sorted(self.objects[rid] for rid, row in self.rows.items() if row['side'] == side)
            for side in ('prediction', 'reference')}})

    def location(self, rid):
        row = self.rows[rid]
        target = rid if row['side'] == 'reference' else self.mapped.get(rid)
        return self.locations.get(target)

    def located(self, rid, *, require_mapping=True):
        if rid in self.unresolved or (require_mapping and (
                self.location(rid) is None or rid not in self.objects)):
            return None
        if any(self.location(target) is None for values in self.edges[rid].values()
               for target in values if target is not None):
            return None
        return {'location': self.location(rid) if require_mapping else None,
                **self.normalized(rid, self.location)}

    def local_identity(self, prediction_row, reference_row):
        if (self.mapped.get(prediction_row) != reference_row
                or prediction_row not in self.objects or reference_row not in self.objects):
            return None
        sides = {}
        for rid in (prediction_row, reference_row):
            root = self.located(rid)
            if root is None:
                return None
            targets, seen = set(), {rid}
            pending = [target for values in self.edges[rid].values() for target in values]
            while pending:
                target = pending.pop()
                if target is None:return None
                if target in seen:continue
                seen.add(target); targets.add(target)
                pending.extend(next_target for values in self.edges[target].values()
                               for next_target in values)
            linked = [self.located(target) for target in targets]
            if any(x is None for x in linked):
                return None
            relevant = {rid, *targets}
            incoming = []
            for other, row in self.rows.items():
                if row['side'] != self.rows[rid]['side']:
                    continue
                spec = self.dictionary.get(row['table'], {})
                relation = (row['table'] == 'condition' or row['table'].endswith('_relation')
                            or (not spec.get('identifier') and len(spec.get('references', {})) > 1))
                if relation and any(target in relevant for values in self.edges[other].values()
                                    for target in values):
                    value = self.located(other, require_mapping=False)
                    if value is None:
                        return None
                    incoming.append(value)
            sides[self.rows[rid]['side']] = {
                'object': root, 'linked_objects': sorted(linked, key=digest),
                'conditions_and_relations': sorted(incoming, key=digest)}
        return digest({'scope': scope(self.packet), 'local_scientific_context': sides})

    def comparison_value(self, cell):
        endpoints = self.edges[cell['row']].get(cell['field'])
        if endpoints and all(x is not None and self.location(x) is not None for x in endpoints):
            return encoded({'association_targets': sorted([self.location(x) for x in endpoints],
                                                          key=digest)}).decode()
        return cell['value_json']

    def alignment(self, records):
        identity = self.input_identity()
        if identity is None:
            return None
        pairs = [{'prediction_object': self.objects[r['prediction_row']] if r['prediction_row'] else None,
                  'reference_object': self.objects[r['reference_row']] if r['reference_row'] else None,
                  'verdict': r['verdict'], 'reason': r['reason']} for r in records]
        return {'input_identity': identity, 'pairs': sorted(pairs, key=lambda p: digest({
            k: p[k] for k in ('prediction_object', 'reference_object', 'verdict')}))}

    def restore(self, alignment):
        if alignment['input_identity'] != self.input_identity():
            raise ValueError('Frozen record alignment belongs to a different scientific input')
        by_side = {side: {key: rid for rid, key in self.objects.items()
                         if self.rows[rid]['side'] == side} for side in ('prediction', 'reference')}
        result = []
        for pair in alignment['pairs']:
            p, g = pair['prediction_object'], pair['reference_object']
            if ((p is not None and p not in by_side['prediction'])
                    or (g is not None and g not in by_side['reference'])):
                raise ValueError('Frozen record object is absent from the current inventory')
            result.append({'prediction_row': by_side['prediction'].get(p),
                           'reference_row': by_side['reference'].get(g),
                           'verdict': pair['verdict'], 'reason': pair['reason']})
        for side in ('prediction', 'reference'):
            actual = [x[side + '_row'] for x in result if x[side + '_row'] is not None]
            if len(actual) != len(set(actual)) or set(actual) != {
                    rid for rid, row in self.rows.items() if row['side'] == side}:
                raise ValueError('Frozen record alignment does not cover the current inventory')
        return result
