# C018 — Clinical trial curation

Paper: Bimagrumab plus semaglutide alone or in combination for the treatment of obesity: a randomized phase 2 trial
DOI: 10.1038/s41591-026-04204-0

## Objective
The comparison of bimagrumab 30 mg/kg plus semaglutide 2.4 mg with semaglutide 2.4 mg plus matching bimagrumab placebo.

## Included scope
- Population: The source-defined analysis populations for the selected main Table 2 absolute-weight comparison and the Results fat/lean analyses in the primary 48-week treatment period.
- Measures: Body weight; Total body fat mass by DXA; Total body lean mass by DXA
- Time: Baseline to week 48 in the primary treatment period; preserve the source-defined estimand for each selected result.

## Requested statistics
- Selected two arms only: main Table 2 absolute weight LSM change, efficacy-estimand Results percentage fat/lean LSM changes, and explicit tests against semaglutide 2.4 mg. Preserve each source estimand; exclude double-placebo contrasts, other arms and week 72.

## Excluded scope
- All other arms, placebo-only comparisons, week-72 extension and treatment-regimen analyses beyond the explicitly selected main Table 2 absolute-weight comparison
- Appendicular/visceral measures, waist, responder categories, metabolic and safety outcomes

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
