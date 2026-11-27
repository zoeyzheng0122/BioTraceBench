# C017 — Clinical trial curation

Paper: Improved health‐related quality of life with tirzepatide versus semaglutide in adults with obesity or overweight from the SURMOUNT‐5 trial
DOI: 10.1111/dom.70215

## Objective
The SURMOUNT-5 HRQoL comparison at the maximum tolerated doses.

## Included scope
- Population: The overall on-treatment population receiving at least one study dose in this SURMOUNT-5 HRQoL analysis.
- Measures: SF-36v2 Physical Component Summary; SF-36v2 Mental Component Summary; SF-36v2 General Health domain
- Time: Baseline to week 72.

## Requested statistics
- Arm-level baseline norm-based scores from the source baseline table and week-72 efficacy-model changes/contrasts for PCS/MCS/GH. Exclude duplicated figure baseline means, whole-cohort summaries, other domains and mental-health categorical outcomes.

## Excluded scope
- All other SF-36 domains and limited-function/weight-loss-category subgroups
- PHQ-9, PGI-S, weight-loss efficacy and safety

## Case-specific application
- Use Supplementary Table S2 for the requested baseline scores and Figure 1 for week-72 efficacy changes/contrasts. Resolve plotted significance symbols through their legends. Apply the shared rules for denominators, graphical values and conflicting dispersion terminology.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
