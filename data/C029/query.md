# C029 — Clinical trial curation

Paper: The feasibility of delivering and evaluating stratified care integrated with telehealth (‘Rapid Stratified Telehealth’) for patients with low back pain: a feasibility and pilot randomised controlled trial
DOI: 10.1007/s10067-026-07955-w

## Objective
The randomized Rapid Stratified Telehealth pilot comparison.

## Included scope
- Population: The randomized pilot trial groups, retaining the actual denominator used for appointment waiting-time summaries.
- Measures: Waiting time from randomization to first rheumatologist appointment; Pain in the past 7 days; Roland–Morris disability score
- Time: Waiting time to the first appointment; baseline to month 3 for pain and RMDQ.

## Requested statistics
- Reported waiting-time medians/IQR and explicit qualitative waiting-time comparison; baseline/month-three observed pain/RMDQ medians/IQR with actual assessed denominators. Do not calculate missing contrasts or significance.

## Excluded scope
- Other visits, appointment counts, other feasibility outcomes and PROMIS domains
- Qualitative interviews, utilization and safety

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
