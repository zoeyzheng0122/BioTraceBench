# C002 — Clinical trial curation

Paper: A randomized clinical study comparing trabectedin combined with regional hyperthermia with trabectedin in patients with advanced soft tissue sarcoma: HyperTET, a German Interdisciplinary Sarcoma Group trial
DOI: 10.1016/j.esmoop.2026.106921

## Objective
The primary randomized HyperTET comparison.

## Included scope
- Population: Eligible randomized patients with advanced soft tissue sarcoma in the HyperTET ITT analysis set.
- Measures: Progression-free survival; Overall survival; Objective response rate
- Time: The main efficacy analysis at the reported data cutoff; use the reported response-assessment window for ORR.

## Requested statistics
- Primary main-text stratified PFS/OS arm medians and HRs; main-text ORR responder counts with the source-reported assessable denominator. Main Results has priority over conflicting supplementary response counts. Exclude univariate forest-plot estimates, alternate logistic response models and cycle-count subgroups.

## Excluded scope
- All cycle-defined/post hoc subgroups and exploratory multivariable models
- DCR, treatment exposure and safety

## Case-specific application
- Use the main Results primary stratified PFS/OS analysis and requested response counts. If its matching CI differs from the abstract, retain the main Results version and record the abstract discrepancy; do not combine bounds from different versions.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
