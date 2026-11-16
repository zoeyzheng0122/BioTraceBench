"""Declared native labels for identity only; no outcome or semantic inference."""
import re

COMPONENT_CONTRACT = 'biotracebench-native-components-1'
NORMALIZATIONS = {'exact', 'casefold', 'uppercase', 'positive_integer'}


def _normalize(value, kind):
    if not value or not value.strip():
        return None
    if kind == 'positive_integer':
        if not re.fullmatch(r'[0-9]+', value) or len(value) > 100 or int(value) <= 0:
            return None
        return str(int(value))
    if kind == 'casefold':
        return value.casefold()
    if kind == 'uppercase':
        return value.upper()
    return value


def validate(rule):
    if not isinstance(rule, dict) or not isinstance(rule.get('basis'), str) or not rule['basis'].strip():
        raise ValueError('Native identity rule requires a written basis')
    if set(rule) == {'pattern', 'basis'}:
        patterns = [rule['pattern']]
    else:
        if (set(rule) != {'contract', 'components', 'basis'} or rule['contract'] != COMPONENT_CONTRACT
                or not isinstance(rule['components'], dict) or not rule['components']):
            raise ValueError('Unknown native identity component contract')
        patterns = []
        for name, component in rule['components'].items():
            if (not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_]*', name)
                    or not isinstance(component, dict)
                    or set(component) - {'patterns', 'normalization', 'aliases'}
                    or not isinstance(component.get('normalization'), str)
                    or component.get('normalization') not in NORMALIZATIONS
                    or not isinstance(component.get('patterns'), list) or not component['patterns']):
                raise ValueError('Native identity components require explicit patterns and normalization')
            aliases = component.get('aliases', {})
            if not isinstance(aliases, dict) or any(
                    not isinstance(k, str) or not isinstance(v, str)
                    or _normalize(k, component['normalization']) != k
                    or _normalize(v, component['normalization']) != v for k,v in aliases.items()):
                raise ValueError('Native component aliases must be explicit normalized labels')
            patterns.extend(component['patterns'])
    for pattern in patterns:
        if not isinstance(pattern, str) or 'identity' not in re.compile(pattern).groupindex:
            raise ValueError('Native label extraction requires a named identity group')


def extract(raw, rule):
    if not isinstance(raw, str):
        return None
    if 'components' not in rule:
        # Preserve the exact historical single-label behavior, including its
        # refusal to infer an identity from multiple occurrences.
        hits = list(re.finditer(rule['pattern'], raw))
        label = hits[0].group('identity') if len(hits) == 1 else None
        return ('native_label', label) if label and label.strip() else None
    parts = []
    for name, component in sorted(rule['components'].items()):
        values = set()
        for pattern in component['patterns']:
            for hit in re.finditer(pattern, raw):
                value = _normalize(hit.group('identity'), component['normalization'])
                if value is None:
                    return None
                values.add(component.get('aliases', {}).get(value, value))
        if len(values) != 1:
            return None  # Missing or conflicting evidence never becomes a guess.
        parts.append((name, values.pop()))
    return ('native_components', tuple(parts))
