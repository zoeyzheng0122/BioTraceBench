"""Versioned fixed-reference counting; never infer facts or amend raw gold."""

CONTRACT = 'biotracebench-fixed-reference-1'


def fixed_reference(policy):
    version = policy.get('reference_contract')
    if version is None:
        return False  # Historical source-state policies remain replayable.
    if version != CONTRACT:
        raise ValueError('Unknown fixed-reference contract')
    if policy.get('compound_fields'):
        raise ValueError('Fixed-reference contract requires whole-field scoring')
    return True


def blank(value):
    """Only null/blank strings are absent; zero, false and states are content.

    Structured submissions are preserved, including empty containers. A type
    error cannot be hidden by treating arbitrary JSON objects as a blank cell.
    """
    return value is None or isinstance(value, str) and not value.strip()


def counted(item):
    if not item:
        return False
    if 'count_as_field' in item:
        return item['count_as_field']
    return bool(item['exists'] and item['state'] != 'not_applicable')
