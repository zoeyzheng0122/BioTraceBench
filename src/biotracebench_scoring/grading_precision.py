"""Shared Qwen precision instructions; never compute or override a cell verdict."""
import copy
from model_conversation.archive import digest

CONTRACT = 'biotracebench-bidirectional-rounding-1'
NUMERIC_POLICY = (
    'Preserve original exact decimal values. Qwen first checks numeric equality; '
    'for the same continuous quantity, round the more precise side to the coarser '
    'written decimal precision using ROUND_HALF_UP and accept numeric equivalence '
    'only if the rounded value equals the other side. Apply in either direction; '
    'equal precision requires equality. Establish the same object, quantity, time '
    'and common unit through the approved finite unit catalog first. Counts, '
    'denominators and identifiers remain exact. Keep signs, comparators, interval '
    'bounds, scientific states and all other whole-cell assertions. No source-bound '
    'rounding exceptions, percentage tolerance, missing-value derivation, partial '
    'credit or programmatic scientific rejudgment.')

POLICY = {
    'version':CONTRACT,
    'scope':'all_tasks_generation_models_and_conditions',
    'decision_authority':'qwen_whole_cell_judgment',
    'comparison':'exact_first_then_round_more_precise_side_to_coarser_side',
    'precision_basis':'original_written_numeric_values_including_decimal_exponent',
    'rounding':'ROUND_HALF_UP',
    'negative_ties':'away_from_zero',
    'equal_precision':'numeric_equality_required',
    'integer_display':'zero_decimal_places_for_continuous_quantities_only',
    'counts_denominators_identifiers':'exact',
    'context':'same_scientific_object_quantity_time_direction_and_state',
    'units':'same_unit_or_approved_exact_conversion_to_a_common_unit',
    'compound_cells':'all_or_nothing_no_subitem_scores',
    'original_values':'preserved_without_rewriting',
    'rounding_reason':'state_both_original_values_target_precision_rounded_value_and_whole_cell_verdict',
    'citation_quality_gate':False}

INSTRUCTION = '''Use the shared bidirectional decimal-precision policy for ALL tasks and conditions. First check exact numeric equality. For two unequal representations of the SAME continuous quantity, identify their written decimal precision and round ONLY the more precise side ONCE to the coarser side's precision using ROUND_HALF_UP (ordinary rounding; ties away from zero). Accept numeric equivalence only when that rounded value equals the other side. This works whether prediction or gold is more precise. Equal precision requires equality. A continuous quantity written as an integer has zero decimal places; scientific notation's exponent determines its decimal place. Examples: 12.346 versus 12.35 is equivalent in either direction; 12.344 versus 12.35 is not. Counts (including count-valued results), sample sizes, denominators and identifiers remain exact even when written with decimals. Establish the same object, quantity, time, direction and same/approved common unit first; do not invent precision by reformatting unit conversions. Preserve comparator meaning, signs, interval endpoints, NR/NE and every other assertion. Apply allowed rounding to corresponding continuous components of a compound cell without splitting its score: one wrong assertion still makes the submitted whole cell incorrect. Do not rewrite either original value. When using rounding, state both original values, target precision, rounded value and the whole-cell reason in the existing cell reason. No per-study source-precision exception or extra source citation is required. Do not invent percentage tolerances or infer missing values.'''


def criteria(policy):
    """Validate the shared numeric precision policy."""
    if 'precision_rules' in policy:
        raise ValueError('Remove superseded source-bound precision_rules; whole-task grading uses shared bidirectional rounding')
    if policy.get('precision_contract', CONTRACT) != CONTRACT:
        raise ValueError('Whole-task precision_contract must use shared bidirectional rounding')
    if 'precision_policy' in policy and digest(policy['precision_policy']) != digest(POLICY):
        raise ValueError('Whole-task precision_policy differs from the approved shared rule')
    if 'numeric_policy' in policy and policy['numeric_policy'] != NUMERIC_POLICY:
        raise ValueError('Replace competing numeric_policy with the shared bidirectional rounding policy')
    return {'precision_contract':CONTRACT, 'precision_policy':copy.deepcopy(POLICY),
            'numeric_policy':NUMERIC_POLICY}
