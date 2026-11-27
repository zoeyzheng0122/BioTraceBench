# C041 — Clinical trial curation

Paper: Longitudinal Outcomes of Bilateral and Unilateral Proximal Greater Occipital Nerve Pulsed Radiofrequency in Migraine: A Prospective Randomized Controlled Trial
DOI: 10.3390/medicina62081554

## Objective
The proximal GON-PRF treatment-side comparison.

## Included scope
- Population: The article-defined per-protocol population completing follow-up in the migraine GON-PRF trial.
- Measures: Monthly headache days; Monthly-headache-day responder criterion; Acute medication days
- Time: Baseline to month 6.

## Requested statistics
- Baseline/month-six arm MHD/AMD medians/IQR, month-six responder proportions/test, month-six absolute-score comparisons and explicitly reported month-six between-group MHD-reduction comparison. Attach within-arm tests to summaries; exclude baseline hypothesis tests, other visits and other migraine outcomes.

## Excluded scope
- Months 1/3 and overall longitudinal effects not specific to month 6
- VAS, HIT-6, MIDAS, GPE and safety

## Published participant-flow scope
Use the published article and its CONSORT diagram for the randomized parent cohort, its treatment arms and the requested per-protocol populations. Do not create a registry-enrollment population or link registry enrollment to the published analysis populations; registry enrollment is outside the requested table scope.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
