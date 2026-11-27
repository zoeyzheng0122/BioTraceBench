# C014 — Clinical trial curation

Paper: Semaglutide Injection in Indian Patients With Type 2 Diabetes Mellitus: A Randomised, Phase III, Active‐Controlled Study
DOI: 10.1111/dom.70891

## Objective
The primary synthetic-semaglutide comparison in the Indian phase III study.

## Included scope
- Population: The per-protocol efficacy population in the Indian phase III semaglutide non-inferiority study.
- Measures: HbA1c; Fasting blood glucose; Post-prandial blood glucose; Body weight
- Time: Baseline to week 24 in the primary per-protocol efficacy population.

## Requested statistics
- Primary per-protocol Week-24 arm changes for all four requested observations and reported between-group estimates or independent tests; also reported percentage weight loss. HbA1c non-inferiority applies only to HbA1c. Exclude ITT sensitivity results, earlier visits and threshold-achiever endpoints.

## Excluded scope
- ITT/sensitivity analyses, earlier visits, HbA1c achievement categories and BMI
- Lipids, blood pressure, safety and immunogenicity

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
