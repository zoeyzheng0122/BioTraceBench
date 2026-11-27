# C037 — Clinical trial curation

Paper: Subcutaneous versus intravenous ultra-low-dose rituximab in rheumatoid arthritis: a randomized controlled PK-PD non-inferiority trial
DOI: 10.1093/rheumatology/keag420

## Objective
The ultra-low-dose rituximab comparison of 336 mg subcutaneously and 200 mg intravenously.

## Included scope
- Population: The randomized ultra-low-dose rituximab trial cohort, retaining the actual PK, disease-activity and B-cell analysis populations and their relationship to randomized groups.
- Measures: Rituximab serum concentration AUC0–6 months; DAS28-CRP disease-activity score; Peripheral B-cell count
- Time: AUC over 0–6 months; baseline to month 6 for DAS28-CRP/B-cell counts.

## Requested statistics
- Primary model AUC geometric-mean ratio with its reported CI; for DAS28-CRP, the six-month within-arm mean change with its CI reported in the abstract and the adjusted between-arm change contrast reported in Results; and the six-month B-cell comparison. Preserve endpoint-specific n and non-inferiority criteria. Do not digitize unlabeled B-cell plots or fabricate numerical summaries.

## Excluded scope
- Trapezoidal-AUC sensitivity, peak/trough concentration, month-3 and prior-dose subgroups
- ADA, quality of life, preferences and safety

## Case-specific application
- Use the numerical within-arm DAS28-CRP mean change and its CI in the abstract and the adjusted between-arm contrast in Results. Do not create additional result rows from qualitative-only arm descriptions. Apply the shared rules for statistical targets, comparison direction and endpoint-specific populations. Use available six-month B-cell measurements without digitizing unlabelled plots.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
