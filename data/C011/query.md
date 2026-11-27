# C011 — Clinical trial curation

Paper: App-based multimodal lifestyle-intervention for essential hypertension (HYPE): a decentralized randomised controlled trial
DOI: 10.3389/fdgth.2025.1672553

## Objective
The primary HYPE efficacy comparison.

## Included scope
- Population: The HYPE ITT population with uncontrolled essential hypertension.
- Measures: Mean home systolic blood pressure; Mean home diastolic blood pressure; Body weight
- Time: Baseline and week 12.

## Requested statistics
- Main Table 2 observed baseline/week-12 arm means and reported changes; primary MICE-ITT ANCOVA contrasts. Include absolute weight summaries and baseline-relative percentage changes/contrasts, retaining the separately reported effect sizes and their own intervals.

## Excluded scope
- Quality of life, food literacy and responder categories
- Per-protocol/subgroup and safety analyses

## Case-specific application
- Use main Table 2 observed baseline/week-12 summaries and the primary MICE-ITT ANCOVA contrasts. Raw-unit contrasts and standardized d are separate principal statistics with their own CIs; do not assign the CI printed beside d to the raw-unit contrast.
- Retain reported point estimates at the selected table precision. Follow-up completers, PP counts, subgroup totals and test df do not establish each observed endpoint denominator.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
