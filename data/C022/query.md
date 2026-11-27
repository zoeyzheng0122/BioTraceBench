# C022 — Clinical trial curation

Paper: Evaluation of the Impact of a Smartphone App on Adherence to an Exercise Program in People With Chronic Low Back Pain: Randomized Controlled Trial
DOI: 10.2196/77736

## Objective
The primary exercise-app comparison during usual multidisciplinary rehabilitation.

## Included scope
- Population: The intention-to-treat population in the chronic-low-back-pain exercise-app trial.
- Measures: Exercise Adherence Rating Scale Part B; Pain intensity on the Numeric Rating Scale; Oswestry Disability Index
- Time: The 6-month comparison and each outcome’s explicitly reported baseline/reference assessment.

## Requested statistics
- EARS/NRS/ODI: Table 1 baseline arm mean/SD and Table 2 six-month arm mean/SD, main-text adjusted between-group differences with CI/P, and all Table 2 effect sizes (ES) with their own CI/P. Preserve Table 2 NRS scale; do not rescale from conflicting prose. Do not infer ES formula/sign or model denominator from follow-up counts. Exclude the separately labelled confirmatory EARS comparison.

## Excluded scope
- Three-week outcomes and other measures
- Separately designated confirmation models, other sensitivity versions, standalone within-arm/trajectory tests and calculated changes

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
