# C047 — Clinical trial curation

Paper: The impact of home-based telerehabilitation pranayama on sleep quality and wellbeing in mild to moderate obstructive sleep apnea syndrome. A randomized controlled trial
DOI: 10.1186/s13030-026-00359-x

## Objective
The home-based telerehabilitation pranayama trial.

## Included scope
- Population: The article’s final analyzed population with mild-to-moderate OSA, preserving its relation to randomized participants.
- Measures: Pittsburgh Sleep Quality Index total score; Epworth Sleepiness Scale score; Fatigue Severity Scale score
- Time: Baseline to week 8.

## Requested statistics
- Table 2 baseline/week-eight arm means/SD and published within-arm improvements with paired P; independent between-arm tests for PSQI/ESS/FSS. Preserve source improvement sign and analyzed versus allocated counts. Exclude other questionnaires.

## Excluded scope
- Questionnaire components and other follow-up intervals
- Quality of life, mood and other questionnaires

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
