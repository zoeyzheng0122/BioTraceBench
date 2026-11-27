# C049 — Clinical trial curation

Paper: The Effect of Digital Cognitive Behavioural Therapy for Insomnia in People With Co‐Morbid Insomnia and Sleep Apnoea (COMISA): A Pilot Randomised Controlled Trial
DOI: 10.1111/jsr.70114

## Objective
The randomized digital-CBTi comparison before delayed CBTi access.

## Included scope
- Population: The primary ITT population of adults with COMISA in this pilot trial.
- Measures: Insomnia Severity Index total score; PHQ-9 depression score; GAD-7 anxiety score
- Time: Baseline to week 8 before delayed CBTi access in controls.

## Requested statistics
- Table 2 baseline/week-eight estimated marginal means with reported CI half-widths, group-by-time tests and baseline-adjusted treatment contrasts with CI/d/P. Use Table 2/supplement over conflicting abstract effect size. Exclude within-CBTi-only effects, score subscales and post-delay-control comparisons.

## Excluded scope
- Weeks 16/24, ISI components and complete-case response/remission categories
- Sleepiness, fatigue, maladaptive sleep beliefs and other questionnaires

## Case-specific application
- For the PHQ-9 between-group contrast use the matching main Table 2/supplementary Depression analysis. The separately reported CBTi within-group effect is outside the requested output; distinguish it from the requested between-group effect during source review and do not create a within-group result row. Retain conflicting abstract versions in the separate review record.
- Preserve the reported contrast magnitudes without assigning an unreported software contrast/subtraction formula. Keep standardized d separate from raw-unit differences. Do not construct CI bounds from reported half-widths.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
