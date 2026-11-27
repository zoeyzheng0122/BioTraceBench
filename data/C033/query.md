# C033 — Clinical trial curation

Paper: Abatacept versus hydroxychloroquine for prevention of rheumatoid arthritis in individuals with palindromic rheumatism: a randomized open-label trial
DOI: 10.1038/s41591-026-04395-6

## Objective
The primary PALABA prevention comparison in palindromic rheumatism.

## Included scope
- Population: The modified full analysis set with failure imputation in seropositive palindromic rheumatism.
- Measures: Development of persistent RA-classifying arthritis; Intensity of palindromic joint attacks on the reported VAS; Palindromic-rheumatism symptom remission
- Time: The 24-month trial period; use the source-defined pre-randomization reference interval for attack-intensity change.

## Requested statistics
- Primary failure-imputed 24-month RA arm counts/proportions and risk difference/test; pre-randomization and 24-month period-level attack-intensity medians and comparison; 0–24-month remission counts/proportions/test using observed denominator in Supplementary Table 7. Exclude alternate logistic models, overall-cohort results and 0–12-month remission.

## Excluded scope
- Available-data-only/per-protocol analyses, time-to-RA and visit-specific trajectories
- Attack frequency/duration, antibodies and safety

## Case-specific application
- For remission use the endpoint-specific observed denominator in Supplementary Table 7. Derive its population membership from the source. Retain the primary reported risk difference and its CI, applying the shared rules for comparison direction.

## Eligibility source
Use the published article Methods to define eligibility for the published analyses. Treat frozen registry eligibility as version context rather than a second population definition. Preserve source-reported post-randomization exclusions and do not assert that every randomized participant actually met all eligibility criteria.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
