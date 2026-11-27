# C034 — Clinical trial curation

Paper: A Phase 2 Trial of Hydroxychloroquine in Individuals at Risk for Rheumatoid Arthritis
DOI: 10.1002/art.43366

## Objective
The primary StopRA prevention comparison.

## Included scope
- Population: The modified ITT population at risk for RA with elevated anti-CCP3 in StopRA.
- Measures: Development of clinical RA; Development of inflammatory arthritis; Participant-reported painful-joint count over the full 42-joint assessment
- Time: The primary month-36 endpoint; baseline/month-36 observed-data summaries for painful-joint counts.

## Requested statistics
- Month-36 RA/IA arm event counts and KM risk estimates/differences; full 42-joint painful-joint observed baseline/month-36 medians and differences. Exclude month-12 IA, diagnostic subdivisions and the subset that did not develop RA.

## Excluded scope
- Week-52, LOCF painful-joint variants, 32-joint and positive-count-only subsets
- Alternate intercurrent-event/per-protocol policies, risk-factor subgroups, stiff joints, other symptoms and safety

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
