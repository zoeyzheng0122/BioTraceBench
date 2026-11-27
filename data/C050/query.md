# C050 — Clinical trial curation

Paper: Bilateral hypoglossal nerve stimulation for obstructive sleep apnea: a nonrandomized clinical trial
DOI: 10.5664/jcsm.11822

## Objective
The primary 12-month bilateral hypoglossal nerve stimulation assessment.

## Included scope
- Population: The source-defined populations for the selected coprimary outcomes and Table 2 continuous-AHI summaries, together with the reported participant-flow context necessary to interpret these analyses.
- Measures: AHI response under the coprimary criterion; ODI response under the coprimary criterion; AHI as a continuous quantity
- Time: Baseline to the primary 12-month assessment.

## Requested statistics
- Primary worst-case-imputed AHI/ODI responder counts/proportions/performance-goal tests and Table 2 paired continuous total-AHI baseline/12-month summaries/change/test. Exclude PP/FAS sensitivity responses, unrelated baseline denominators and positional/REM/NREM AHI subdivisions.

## Excluded scope
- Continuous ODI, oxygenation, other follow-up and patient-reported outcomes
- Safety

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
