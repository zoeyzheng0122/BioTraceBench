# C048 — Clinical trial curation

Paper: Aroxybutynin and atomoxetine (AD109) for obstructive sleep apnea: a randomized phase 3 trial (SynAIRgy)
DOI: 10.1093/ajrccm/aamag215

## Objective
The primary SynAIRgy comparison.

## Included scope
- Population: The article-defined primary ITT population receiving at least one dose in SynAIRgy.
- Measures: AHI under the primary event/desaturation definition; ODI under the reported key-secondary-endpoint definition; PROMIS-Fatigue T score
- Time: Baseline to week 26, primary ITT estimand.

## Requested statistics
- Main ITT Table 2 arithmetic AHI/ODI/PROMIS changes and contrasts; Results AHI geometric-mean percentage reductions/test; directly reported baseline/week-26 observed summaries with endpoint n. Use main-table precision for its estimates. Exclude on-treatment alternatives, categorical AHI responders and superseded qualitative placeholders.

## Excluded scope
- On-treatment estimand, earlier visits, responder/severity categories and subgroups
- Hypoxic burden, sleep impairment and safety

## Case-specific application
- Use main ITT Table 2 for requested arithmetic model changes/contrasts and Table E1 for matching observed baseline/week-26 summaries with endpoint-specific n. Keep observed n distinct from randomized/analysis-set totals.
- Keep geometric-mean percentage reductions separate from arithmetic changes and observed medians. Retain only numerically reported CI limits; do not estimate geometric-reduction limits from Figure 2 error bars.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
