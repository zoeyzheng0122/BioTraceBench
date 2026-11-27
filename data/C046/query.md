# C046 — Clinical trial curation

Paper: Time to diagnosis and treatment of obstructive sleep apnoea using mandibular jaw movement monitoring versus polysomnography: an open-label, multicentre, randomised, controlled trial
DOI: 10.1016/j.lanepe.2026.101637

## Objective
The main SUNSAS diagnostic-pathway comparison.

## Included scope
- Population: The main randomized-analysis population of adults with suspected OSA in SUNSAS; retain the source-defined population for each timing endpoint.
- Measures: Time from randomization to diagnostic consultation; Time from randomization to treatment initiation; Epworth Sleepiness Scale score
- Time: Timing endpoints start at randomization; ESS at baseline and 3 months after diagnostic consultation, not 3 months after randomization.

## Requested statistics
- Main-analysis randomization-origin time-to-diagnosis/treatment medians and tests; ESS baseline and primary PP change/contrast three months after diagnostic consultation. Exclude post hoc at-home-PSG comparisons, mITT ESS sensitivity and post-randomization ESS timing as an alternate endpoint.

## Excluded scope
- ESS at 3 months post-randomization and mITT/imputed ESS supporting variants
- Severity subgroups, quality of life, productivity, accuracy, economics and PAP adherence

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
