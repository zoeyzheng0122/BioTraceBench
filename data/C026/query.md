# C026 — Clinical trial curation

Paper: Aquatic therapy compared to standard care for chronic low back pain: a randomized controlled trial
DOI: 10.1080/17581869.2026.2613633

## Objective
The analyzed aquatic-therapy comparison in chronic low back pain.

## Included scope
- Population: The analyzed chronic-low-back-pain cohort in this two-arm aquatic-therapy trial.
- Measures: NPRS pain score; ODI disability score; Combined HADS psychological score (not separate anxiety/depression subscales)
- Time: Baseline and week 10.

## Requested statistics
- Table 3 NPRS, ODI and combined HADS outcome: adjusted baseline/week-10 arm means, within-arm changes, week-10 group comparisons and group-by-time F with P/df/eta-squared supplements. Exclude SF-12 and other psychological scales.

## Excluded scope
- Other psychological, sleep and quality-of-life measures
- Parent-trial muscle morphology, other visits and subgroup analyses
- Separate HADS anxiety/depression subscale results and other psychological measures

## Case-specific application
- Use the requested adjusted Table 3 outcomes. Preserve a reported between-group MD and its own CI without inferring its subtraction direction from the two adjusted means or the table column order. Keep the task-requested F/df/partial-eta-squared supplements with the corresponding analysis.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
