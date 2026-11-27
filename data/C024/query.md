# C024 — Clinical trial curation

Paper: Comparative Effects of Minodronate and Alendronate on Low Back Pain in Postmenopausal Osteoporosis and Age Influence: A Head-to-Head, Randomized Clinical Trial
DOI: 10.2147/CIA.S541940

## Objective
The ITT minodronate–alendronate efficacy comparison.

## Included scope
- Population: Postmenopausal participants with osteoporosis-related low back pain in the intention-to-treat (ITT) efficacy population only, retaining the source-reported endpoint-specific analysis denominators.
- Measures: VAS low-back-pain score; Lumbar-spine bone mineral density; Total-hip bone mineral density
- Time: VAS baseline to week 12; BMD baseline to week 24.

## Requested statistics
- For week-12 VAS, extract the mean reductions and 95% CIs stated in the main Results VAS paragraph and the abstract-reported endpoint between-group P value. Use the main Results week-12 time label; do not add the differently labelled serial visits from Table S2.
- For lumbar-spine and total-hip BMD, use only the W24 column of Supplementary Table S3: extract each treatment arm's mean percentage change, its SD, and the between-group P value. Table S3 time-specific cells take precedence over BMD prose, abstract summaries and figures. Do not import abstract-only BMD CIs or repeat W12 values as W24.
- Keep each between-group P value in a separate result row because no between-group difference estimate is requested.

## Excluded scope
- Per-protocol (PP) and other sensitivity-analysis populations/results
- Age-stratified analyses, other VAS visits and bone-turnover markers
- Safety and other outcomes
- Registry records whose population and interventions do not match this osteoporosis trial

## Case-specific application
- For requested VAS reductions use the main Results week-12 report, with the requested abstract endpoint P. Recover units from the adopted source; retain conflicting presentations in separate review records.
- For BMD use only Supplementary Table S3 W24 cells and their own SD/P; exclude W12 and abstract-only CI alternatives. Apply the shared denominator rules.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
