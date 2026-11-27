"""Lossless bounded statistics comparison; the output remains ONE field item."""
import json

from .scoring_items import CI, P_VALUE, DISPERSION, PERCENTAGE, DENOMINATOR


def normalize(text, factor, canonicalize, multiply):
    """Accept only completely labelled segments; retain duplicate statistics.

    Ordered segments preserve attribution by position. Unsupported prose or
    explicit per-segment units require whole-field human review, never dropping
    qualifiers, assigning partial credit or guessing a missing analysis target.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    tokens, dimensional = [], False
    def number(value, scale=False):
        return canonicalize(multiply(value, factor) if scale else multiply(value, '1'))[1]
    for part in text.split(';'):
        part = part.strip()
        if not part:
            continue
        if match := CI.fullmatch(part):
            if factor is None:
                return None
            tokens.append(('CI', number(match['level']) if match['level'] is not None else None,
                           number(match['lower'], True), number(match['upper'], True)))
            dimensional = True
        elif match := DISPERSION.fullmatch(part):
            if factor is None:
                return None
            tokens.append((match['kind'].upper(), number(match['value'], True)))
            dimensional = True
        elif match := P_VALUE.fullmatch(part):
            tokens.append(('P', {'≤':'<=','≥':'>='}.get(match['operator'],match['operator']), number(match['value'])))
        elif match := PERCENTAGE.fullmatch(part):
            tokens.append(('percentage', number(match['value'])))
        elif match := DENOMINATOR.fullmatch(part):
            tokens.append(('denominator', (match['kind'] or 'unspecified').lower(),
                           str(int(match['count'])) if match['count'] else None))
        else:
            return None
    return json.dumps(tokens, separators=(',',':')), dimensional
