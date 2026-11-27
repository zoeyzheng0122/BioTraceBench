# C007 — Clinical trial curation

Paper: Electronic Patient-Reported Outcome Monitoring With Alert-Based Interventions in Metastatic Breast Cancer
DOI: 10.1001/jamaoncol.2026.2661

## Objective
The primary electronic-PRO monitoring comparison in metastatic breast cancer.

## Included scope
- Population: The article-defined modified intention-to-treat population with metastatic breast cancer.
- Measures: CAT Core fatigue T score; CAT Core physical-functioning T score; CAT Core health-related-quality-of-life T score
- Time: Baseline and month 6 only.

## Requested statistics
- Use the main baseline table for observed arm-level baseline means/SD and the primary Results paragraphs for six-month adjusted fatigue arm means and three domain treatment differences/CI. Exclude combined-cohort summaries, baseline significance tests, changes, sensitivity/imputed-model presentations in other figures and protocol-planned populations.

## Excluded scope
- 9/12-month trajectories, emotional functioning and other PRO domains
- Subgroups, missing-data sensitivities, healthcare utilization and survival

## Case-specific application
- Use the baseline PRO table for requested baseline arm summaries. If the abstract or narrative Results repeats a different baseline mean, retain the table value and the discrepancy in the review record. Keep the six-month model analysis separate from baseline descriptives.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
