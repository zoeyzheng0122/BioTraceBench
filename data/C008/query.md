# C008 — Clinical trial curation

Paper: Patient-reported outcomes with trastuzumab deruxtecan in hormone receptor-positive, HER2-low or HER2-ultralow metastatic breast cancer: results from the randomized DESTINY-Breast06 trial
DOI: 10.1016/j.esmoop.2025.105082

## Objective
The overall DESTINY-Breast06 time-to-deterioration comparison.

## Included scope
- Population: The combined HER2-low/HER2-ultralow ITT population of DESTINY-Breast06.
- Measures: TTD in EORTC QLQ-C30 physical functioning; TTD in EORTC QLQ-C30 pain; TTD in EORTC QLQ-C30 fatigue
- Time: The reported time-to-deterioration analysis, preserving its event threshold, time origin and censoring rules.

## Requested statistics
- Primary overall-population median TTD per arm and between-group HR for each requested scale, with reported CI/nominal P. Exclude other scales and treatment-component subgroups.

## Excluded scope
- The separate HER2-low analysis and comparisons against individual TPC drugs
- Change-from-baseline analyses, all other scales, efficacy and safety endpoints

## Case-specific application
- Use the requested ITT scale analyses and their matching medians, CIs and HRs. Derive the identities and meanings of the reported populations and risk sets from the source, applying the shared denominator rules. Retain the source censoring rules. Exclude HER2-low-only and individual TPC-drug comparisons.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
