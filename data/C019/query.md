# C019 — Clinical trial curation

Paper: Polypill for heart failure with reduced ejection fraction: the POLY-HF randomized trial
DOI: 10.1038/s41591-026-04504-5

## Objective
The primary POLY-HF comparison.

## Included scope
- Population: The POLY-HF cohort: the primary modified-ITT CMR analysis and the source-defined clinical-event and adherence analyses.
- Measures: CMR left ventricular ejection fraction; Heart-failure hospitalization or emergency-department visit (composite); Medication adherence from blood drug concentrations
- Time: Baseline/month 6 for CMR; the article-defined 6-month clinical-event and adherence windows.

## Requested statistics
- Primary modified-ITT CMR LVEF arm estimates/contrast, HF hospitalization/ED episode rates and rate ratio, and TDM adherence counts/proportions and primary risk ratio/unadjusted test. Exclude death-composite HR, alternate LVEF populations and other endpoints.

## Excluded scope
- Full-ITT/imputed CMR, echocardiographic LVEF, responder/subgroup/sensitivity analyses
- Other adherence definitions, NT-proBNP, medication dosing and safety

## Population scope
Include only populations used for the requested results and the source-supported parent/evaluable populations explicitly needed to link those analyses. Exclude unrelated screening, completion, background and alternative-analysis populations; do not add extra population rows.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
