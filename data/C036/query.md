# C036 — Clinical trial curation

Paper: Adjunctive Pentoxifylline Enhances Clinical Remission and Reduces Inflammatory Biomarkers in Mild-to-Moderate Ulcerative Colitis: A Randomized Double-Blind Placebo-Controlled Pilot Trial
DOI: 10.3390/ph19040552

## Objective
The primary pentoxifylline add-on comparison in mesalamine-treated ulcerative colitis.

## Included scope
- Population: The primary intention-to-treat population with mild-to-moderate UC.
- Measures: Partial Mayo score; Clinical remission under the source-defined PMS rule; IBDQ-32 quality-of-life score
- Time: Baseline to week 24, primary ITT analysis.

## Requested statistics
- ITT Tables 2/4: baseline/week-24 PMS/IBDQ-32 medians, explicitly reported percentage changes and tests; remission counts/proportions/test. Include labeled adjusted P supplement. Exclude PP, clinical-response endpoint and medication-naive/experienced subgroup analyses.

## Excluded scope
- Per-protocol, mesalamine-exposure subgroups, clinical-response categories and other visits
- Inflammatory biomarkers and exploratory regression models

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
