# C031 — Clinical trial curation

Paper: Exploring possibilities towards PeRsonalIsed MEdicine in Rheumatoid Arthritis (PRIMERA): tailored modifications to standard treat-to-target management—a multicentre, randomised, open-label trial
DOI: 10.1136/rmdopen-2026-007217

## Objective
The primary PRIMERA treat-to-target comparison.

## Included scope
- Population: The main randomized-analysis population of DMARD-naïve RA in PRIMERA.
- Measures: ts/bDMARD use; Disease Activity Score (DAS); Low disease activity under the source-defined DAS threshold
- Time: ts/bDMARD use at month 10; the reported overall 10-month DAS analysis; LDA at month 3.

## Requested statistics
- Ten-month ts/bDMARD use counts/proportions and published difference; overall ten-month longitudinal DAS Wald test; month-three LDA counts/proportions and difference. Exclude per-visit DAS and other LDA times.

## Excluded scope
- Separate visit-by-visit DAS rows, time-to-LDA, remission and autoantibody subgroups
- Per-protocol analyses, other medication timelines, PROs and safety

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
