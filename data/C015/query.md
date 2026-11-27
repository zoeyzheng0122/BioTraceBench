# C015 — Clinical trial curation

Paper: Semaglutide Effects on Insulin Sensitivity and β-Cell Function in Patients With Schizophrenia, Prediabetes, and Obesity Treated With Second-Generation Antipsychotics: Findings From the HISTORI Trial, a 30-Week Randomized, Placebo-Controlled Trial With Semaglutide 1.0 mg Weekly
DOI: 10.2337/dc25-2041

## Objective
The semaglutide HOMA analysis in SGA-treated participants with schizophrenia.

## Included scope
- Population: The article-defined HOMA analysis population of SGA-treated participants with schizophrenia, prediabetes and overweight/obesity.
- Measures: HOMA2 insulin sensitivity (HOMA2-S); HOMA2 beta-cell function (HOMA2-B); HOMA insulin resistance (HOMA-IR)
- Time: Baseline to week 30.

## Requested statistics
- Main Table 2 week-30 arm HOMA changes and mixed-model treatment effects/CI/P. Do not substitute complete-data subgroup counts for model analysis n; exclude unreported baseline reconstructions, week-15 and unrelated metabolic outcomes.

## Excluded scope
- Week-15, weight-loss mediation, normal-glucose reference and antipsychotic subgroups
- Glucose, insulin, C-peptide, body weight and other parent-trial endpoints

## Case-specific application
- Retain the requested source-reported HOMA model effects with their own reported CIs. Apply the shared rules for endpoint denominators and unresolved formula or version attributes.

## Population scope
Include only the source-defined analysis populations used for the requested HOMA model estimates. Do not create separate rows for the original randomized arms, the overall randomized cohort, completion cohorts or laboratory-data cohorts that do not define a requested result. Retain relevant treatment assignment and eligibility within the selected analysis-population descriptions.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
