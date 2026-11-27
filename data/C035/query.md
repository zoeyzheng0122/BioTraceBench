# C035 — Clinical trial curation

Paper: Baricitinib in moderate to severe rheumatoid arthritis: dose-dependent efficacy and safety in a randomized clinical trial in a developing country
DOI: 10.1186/s41927-026-00638-8

## Objective
The week-24 comparison of baricitinib 4 mg and 2 mg daily, both with methotrexate.

## Included scope
- Population: The trial’s reported week-24 efficacy analysis population; retain randomized and endpoint-evaluable populations and their source-supported denominators separately.
- Measures: DAS28-CRP low disease activity; DAS28-CRP remission; Bangla HAQ Disability Index functional score
- Time: Week 24; baseline only for the B-HAQ change reference.

## Requested statistics
- Week-24 LDA counts/proportions/risk difference/RR, remission counts/proportions/test, and B-HAQ baseline/week-24 means/medians and reported improvement/test. Use longitudinal Table 3 baseline values for its change analysis; preserve conflicting Table 1 values in separate review records. Keep randomized baseline and per-protocol follow-up denominators distinct.

## Excluded scope
- DAS28-ESR, CDAI, SDAI and other response criteria
- Other continuous scores, biomarkers, earlier visits and safety

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
