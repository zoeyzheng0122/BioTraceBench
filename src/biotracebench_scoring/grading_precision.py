"""Shared whole-field precision instructions; never compute or override a cell verdict."""
import copy
from model_conversation.archive import digest

CONTRACT = 'biotracebench-source-directed-precision-1'
NUMERIC_POLICY = (
    "Establish the same object, quantity, time, direction, comparator and unit. "
    "Test numeric equality first. For unequal continuous quantities, round only a finer prediction "
    "once to the source-supported reference precision (ROUND_HALF_UP, ties away from zero). "
    "Require the rounded prediction to equal the original reference. If the source precision is unknown, "
    "require exact equality. Counts, denominators and identifiers require exact agreement. "
    "Apply the rule to corresponding components, preserving units, signs, bounds, states and all other "
    "assertions. Score the whole field once. When rounding, record both original values, the source "
    "locator, the target precision and the rounded value."
)

POLICY = {
    'version':CONTRACT,
    'scope':'all_tasks_generation_models_and_conditions',
    'decision_authority':'model_whole_cell_judgment',
    'comparison':'exact_first_then_round_finer_prediction_to_supported_reference_precision',
    'precision_basis':'source_supported_reference_decimal_place_otherwise_exact',
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

INSTRUCTION = NUMERIC_POLICY

def criteria(policy):
    """Validate the shared numeric precision policy."""
    if 'precision_rules' in policy:
        raise ValueError('Remove superseded source-bound precision_rules; whole-task grading uses source-directed precision')
    if policy.get('precision_contract', CONTRACT) != CONTRACT:
        raise ValueError('Whole-task precision_contract must use source-directed precision')
    if 'precision_policy' in policy and digest(policy['precision_policy']) != digest(POLICY):
        raise ValueError('Whole-task precision_policy differs from the approved shared rule')
    if 'numeric_policy' in policy and policy['numeric_policy'] != NUMERIC_POLICY:
        raise ValueError('Replace competing numeric_policy with the source-directed precision policy')
    return {'precision_contract':CONTRACT, 'precision_policy':copy.deepcopy(POLICY),
            'numeric_policy':NUMERIC_POLICY}
