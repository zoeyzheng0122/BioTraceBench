"""Validate an embedded approved unit snapshot and explicit quantity contexts.

The snapshot is part of the policy identity and replay capsule. No file lookup,
dimension inference, reference repair or source access occurs during scoring.
"""
import copy
from decimal import Decimal, InvalidOperation

from model_conversation.archive import digest
from .scoring_items import field_role

FAMILIES = {'mass', 'volume', 'fixed_duration', 'pressure_pa', 'molar_concentration',
            'mass_concentration', 'daily_exposure_duration', 'event_rate_spelling'}
TARGETS = {'condition.factor_value': 'factor_unit', 'result.result_value': 'result_unit'}


def compile_unit_rules(catalog, bindings, dictionary, policy=None):
    """Return table rules; all conversion choices are frozen in the policy."""
    if not isinstance(catalog, dict) or catalog.get('approved') is not True:
        raise ValueError('Exact unit catalog requires an approved snapshot')
    if catalog.get('activated') is not True:
        raise ValueError('Explicit quantity bindings require an activated unit catalog')
    families = catalog.get('families')
    if not isinstance(families, dict) or set(families) != FAMILIES:
        raise ValueError('Exact unit catalog must contain only the eight approved families')
    unit_names = set()
    for name, family in families.items():
        if not isinstance(family, dict):
            raise ValueError('Unit family must be an object')
        canonical, scales = family.get('canonical'), family.get('scales')
        if not isinstance(scales, dict) or not scales or canonical not in scales:
            raise ValueError('Unit family requires a canonical unit and scales')
        for unit, scale in scales.items():
            if not isinstance(unit, str) or not unit.strip() or unit in unit_names or not isinstance(scale, str):
                raise ValueError('Unit labels must be nonempty, unique and use exact string scales')
            try:
                number = Decimal(scale)
            except InvalidOperation:
                raise ValueError('Invalid exact unit scale') from None
            if not number.is_finite() or number <= 0:
                raise ValueError('Exact unit scales must be positive and finite')
            unit_names.add(unit)
        if Decimal(scales[canonical]) != 1:
            raise ValueError('Canonical unit must have scale one')
    if not isinstance(bindings, dict):
        raise ValueError('Unit quantity bindings must be a mapping')
    result = {}
    for field, binding in bindings.items():
        if (field not in TARGETS or not isinstance(binding, dict)
                or set(binding) != {'unit_field', 'required_context', 'context_guards', 'whole_field_companions', 'basis'}
                or binding.get('unit_field') != TARGETS[field]
                or not isinstance(binding.get('basis'), str) or not binding['basis'].strip()):
            raise ValueError('Unit bindings require an approved value/unit pair and quantity basis')
        table, key = field.split('.')
        if table not in dictionary:
            continue
        spec = dictionary[table]
        known = {f['key'] for f in spec['fields']}
        # A synthetic/non-unit schema can share the policy without acquiring fields.
        if key not in known or binding['unit_field'] not in known:
            continue
        if any(field_role(table, k, spec, policy or {}) != 'scientific' for k in (key, binding['unit_field'])):
            raise ValueError('Unit conversion targets must be scientific value and unit fields')
        for category in ('required_context', 'context_guards', 'whole_field_companions'):
            names = binding[category]
            if (not isinstance(names, list) or any(not isinstance(k, str) for k in names)
                    or len(set(names)) != len(names) or not set(names) <= known
                    or any(field_role(table, k, spec, policy or {}) != 'scientific' for k in names)):
                raise ValueError('Unit quantity context and companions require declared scientific fields')
        if not binding['required_context']:
            raise ValueError('Unit conversion requires independent quantity context')
        forbidden = {key, binding['unit_field'], spec.get('identifier')}
        if forbidden.intersection(binding['required_context'] + binding['context_guards']):
            raise ValueError('Quantity context cannot be a value, unit or local identifier')
        companions = binding['whole_field_companions']
        if set(companions) - ({'supplementary_statistics'} if table == 'result' else set()):
            raise ValueError('Only an explicitly declared whole supplementary field may follow result units')
        if set(companions).intersection(spec.get('references', {})):
            raise ValueError('Scientific associations cannot be unit companions')
        result.setdefault(table, {})[key] = {
            **copy.deepcopy(binding), 'catalog_families': copy.deepcopy(families),
            'catalog_identity': digest(catalog)}
    return result


def quantity_context(left, right, rule):
    """Called only after independent alignment and association resolution."""
    for key in rule['required_context']:
        a, b = left['items'].get(key), right['items'].get(key)
        if (not a or not b or not a['exists'] or not b['exists']
                or a['state'] != 'reported' or b['state'] != 'reported'
                or a['value'] != b['value'] or a['value'][0] == 'unresolved'
                or a['value'] in (('text',''), ('source_unreported',))):
            return False
        if a['value'][0] == 'references' and any(not isinstance(v, str) for v in a['value'][1]):
            return False
    for key in rule['context_guards']:
        a, b = left['items'].get(key), right['items'].get(key)
        if b and b.get('count_as_field') is False:
            continue  # A blank gold guard declares no extra reference condition.
        if not a or not b or a['exists'] != b['exists'] or a['state'] != b['state'] or a['value'] != b['value']:
            return False
        if a['state'] not in {'reported', 'not_reported', 'not_applicable'}:
            return False
    return True
