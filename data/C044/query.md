# C044 — Clinical trial curation

Paper: Cognitive Behavioral Therapy Alone or in Combination with Eszopiclone in Comorbid Insomnia and Obstructive Sleep Apnea in Veterans with Posttraumatic Stress Disorder: A Randomized Trial
DOI: 10.1007/s11126-025-10143-9

## Objective
The BBTI comparison involving an initial two-week eszopiclone course.

## Included scope
- Population: The main intention-to-treat randomized analysis population of veterans with PTSD and COMISA.
- Measures: Pittsburgh Sleep Quality Index total score; Insomnia Severity Index total score; Epworth Sleepiness Scale score
- Time: Baseline and week 24 only. A requested change must span baseline to week 24; a requested between-arm contrast must explicitly refer to week 24.

## Requested statistics
- Table 3 baseline/week-24 adjusted means and week-24 treatment contrasts; directly reported whole-baseline-to-week-24 PSQI/ISI changes in the abstract. Whole-period ESS change remains missing if unreported. Exclude segmented vectors/interactions, generic group/trajectory tests and registry-only P statements.

## Excluded scope
- Week-6 outcome summaries; Vector 1/Vector 2 coefficients and their treatment interactions; model intercepts, generic group coefficients and whole-trajectory tests
- Questionnaire components/remission categories; CPAP adherence, depression/PTSD, sleep indices and safety
- Derived baseline-to-week-24 changes or treatment effects not directly reported in the sources

## Case-specific application
- Use directly reported whole-baseline-to-week-24 changes. Apply the shared denominator rules; do not construct changes by combining segmented model coefficients.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
