# C028 — Clinical trial curation

Paper: Responsiveness of Outcome Measures in Chronic Non-Specific Low Back Pain: A Secondary Analysis of a Randomized Controlled Trial
DOI: 10.3390/jpm16070338

## Objective
The pooled T0–T1 measurement-responsiveness analysis.

## Included scope
- Population: The pooled analysis cohort reported for the T0–T1 responsiveness estimates in this secondary analysis.
- Measures: NRS pain intensity; ODI disability score; Roland–Morris Disability Questionnaire score
- Time: T0 to T1, after the 2-week intervention.

## Requested statistics
- Table 2 T0–T1 mean change/SD and SMD/CI for NRS/ODI/RMDQ only. Do not recalculate SMD or infer its sign convention from the mean change. Exclude AUC and later T2 follow-up.

## Excluded scope
- T0–T2, Bournemouth, EQ-5D, AUC/ROC and anchor correlations
- Responder classification and arm-specific treatment-effect estimates

## Case-specific application
- Raw mean changes and reported SMDs are different principal statistics. Preserve each reported sign independently; do not reverse an SMD to match a raw change or reconstruct an unspecified standardization/sign convention.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
