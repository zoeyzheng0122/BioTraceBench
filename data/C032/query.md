# C032 — Clinical trial curation

Paper: Specific carbohydrate diet versus Mediterranean diet in adult patients with mild to moderate ulcerative colitis: a randomized controlled-feeding trial
DOI: 10.3389/fnut.2026.1838160

## Objective
The primary controlled-feeding comparison of Specific Carbohydrate Diet and Mediterranean diet.

## Included scope
- Population: The primary ITT population of adults with mild-to-moderate UC in the controlled-feeding pilot trial.
- Measures: Partial Mayo Clinic score; Clinical remission under the reported pMCS criterion; Fecal calprotectin normalization under the reported criterion
- Time: Baseline to week 6, primary ITT/BOCF analysis.

## Requested statistics
- Arm-level raw and ANCOVA-adjusted week-six pMCS summaries/changes and primary contrast; week-six remission and FC normalization count/proportion/test in their applicable populations. Exclude combined-cohort summaries, baseline-normalization results, later visits and unrelated biomarkers.

## Excluded scope
- Week-10, complete-case/sensitivity analyses and other inflammatory thresholds
- Quality of life, microbiome and metagenomic outcomes

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
