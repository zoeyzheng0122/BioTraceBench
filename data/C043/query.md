# C043 — Clinical trial curation

Paper: Cognition and obstructive sleep apnea in Parkinson’s disease: randomized controlled trial of positive airway pressure
DOI: 10.1093/sleep/zsaf038

## Objective
The primary COPE-PAP cognition comparison.

## Included scope
- Population: The primary ITT population with Parkinson’s disease, reduced cognition and OSA.
- Measures: Montreal Cognitive Assessment score; PDQ-39 quality-of-life score; Parkinson’s Disease Sleep Scale score
- Time: Baseline to month 6, primary unadjusted ITT comparison.

## Requested statistics
- Observed baseline Table 2 summaries and primary unadjusted ITT Table 3 six-month means, changes and contrasts for MoCA/PDQ-39/PDSS. Keep observed baseline denominators distinct from imputed ITT endpoints. Exclude PP, covariate-adjusted sensitivity and other visits.

## Excluded scope
- Adjusted ITT, per-protocol, sensitivity and subgroup analyses
- Detailed neurocognitive, motor, depression, ESS and other outcomes

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
