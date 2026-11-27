# C012 — Clinical trial curation

Paper: Tirzepatide in Adults With Type 1 Diabetes: A Phase 2 Randomized Placebo-Controlled Clinical Trial
DOI: 10.2337/dc25-2379

## Objective
The primary tirzepatide trial comparison in adults with type 1 diabetes and obesity.

## Included scope
- Population: Adults with type 1 diabetes and obesity in the trial’s primary ITT weight analysis.
- Measures: Body weight; HbA1c; Total daily insulin dose
- Time: Baseline to week 12.

## Requested statistics
- Main Table 2 analysis baseline/week-12 values, arm changes and adjusted contrasts for weight, HbA1c and total insulin units/day; also explicitly reported weight-percentage difference and relative insulin percentage difference. Preserve ratio of geometric means as a ratio. Exclude Table 1 observational baseline descriptives and insulin subtypes/units-per-kg.

## Excluded scope
- Weight-responder categories, basal/bolus insulin breakdowns and per-kg dose variants
- Body composition, vascular/metabolic assays, other glycemic endpoints and safety

## Case-specific application
- Use the published report for actual randomization, treatment received and efficacy analysis; distinguish any differing planned protocol populations or regimens. Retain directly reported weight-change confidence intervals literally.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
