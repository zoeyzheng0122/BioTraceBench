# C042 — Clinical trial curation

Paper: The Effects of Daridorexant on Patients With Comorbid Insomnia Disorder and Untreated Mild Obstructive Sleep Apnoea: A Post Hoc Subgroup Analysis of a Phase 3, Randomised Clinical Trial
DOI: 10.1111/jsr.70135

## Objective
The selected daridorexant 50-mg and placebo comparison in the mild-OSA subgroup.

## Included scope
- Population: The post hoc subgroup with comorbid insomnia and untreated mild OSA in the phase 3 daridorexant study.
- Measures: Wake after sleep onset; Latency to persistent sleep; Self-reported total sleep time
- Time: Baseline to month 3.

## Requested statistics
- Mild-OSA/COMISA selected 50-mg versus placebo subgroup: numerical baseline means, month-three LSM changes and placebo-adjusted contrasts. Exclude generic across-month descriptions, 25-mg results and other sleepiness endpoints.

## Excluded scope
- Daridorexant 25 mg, month-1 and participants without mild OSA
- IDSIQ/daytime-function, residual sleepiness and safety

## Case-specific application
- For the selected mild-OSA subgroup at month three, use the coherent point estimate/CI/P combinations reported together in Supplementary Table S2 and matching the main Results. Retain Figure S1 discrepancies in review records; more decimal places alone do not establish precedence.
- Keep the endpoint/model adjustment context and separate baseline observed summaries from model changes/contrasts. Do not combine an alternative figure estimate with table-only statistics.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
