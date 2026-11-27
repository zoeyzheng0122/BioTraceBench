# C020 — Clinical trial curation

Paper: Semaglutide and cardiovascular risk in type 1 diabetes: A predictive modelling analysis in a double‐blind, randomised, placebo‐controlled cross‐over trial
DOI: 10.1111/dom.70525

## Objective
The semaglutide cardiovascular-risk secondary analysis over the completed treatment periods.

## Included scope
- Population: The cardiovascular-risk secondary-analysis cohort completing both treatment periods without established CVD.
- Measures: Predicted 10-year CVD risk using ST1RE; Predicted 10-year CVD risk using SDRN; Body weight; HbA1c
- Time: Baseline to the end of each 15-week treatment period.

## Requested statistics
- Baseline pooled median 10-year risk; reported period-specific risk percentage changes and paired placebo-adjusted contrasts; reported paired weight/HbA1c contrasts.

## Excluded scope
- The sensitivity analysis excluding transient microalbuminuria and actual CVD events
- All other risk-model input variables and parent-trial glycemic outcomes

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
