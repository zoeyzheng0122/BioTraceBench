# C006 — Clinical trial curation

Paper: Effects of a Psycho‐Behavioural Intervention on Cancer‐Related Fatigue Among Patients With Colorectal Cancer: A Pilot Randomised Controlled Trial
DOI: 10.1002/pon.70570

## Objective
The six-week psycho-behavioural pilot trial in post-treatment colorectal cancer.

## Included scope
- Population: Post-treatment colorectal cancer patients in the pilot randomized comparison, retaining the reported outcome-analysis denominators.
- Measures: Cancer Fatigue Scale total score; HPLP-II physical-activity subscale score; PROMIS Sleep Disturbance Short Form 4a score
- Time: Baseline T0 and within one week after the 6-week intervention (T1).

## Requested statistics
- For the three domains: arm-level T0/T1 means, group-by-time interaction F with its P, and Hedges g with CI. Exclude whole-cohort summaries, separate group/time main effects and duplicated P-only rows.

## Excluded scope
- Fatigue subscales, dietary behavior, anxiety and depression
- Feasibility, acceptability, qualitative interviews and attendance/recruitment metrics

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
