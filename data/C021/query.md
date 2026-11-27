# C021 — Clinical trial curation

Paper: Physiotherapy informed by acceptance and commitment therapy for chronic low back pain: A randomized trial
DOI: 10.1142/S1013702526500022

## Objective
The PACT-versus-usual-physiotherapy comparison with DNS-based graded exercise.

## Included scope
- Population: Participants with chronic low back pain in the PACT-versus-usual-care randomized comparison.
- Measures: SRQ-E external regulation; SRQ-E introjected regulation; SRQ-E identified regulation; SRQ-E intrinsic motivation
- Time: Baseline and immediately after the 6-week intervention.

## Requested statistics
- Four SRQ-E subscale arm means at baseline/post; arm changes with within-group tests/effect sizes; between-group effect sizes/tests for baseline, post and change. Do not force conflicting effect-size labels into a single inferred metric.

## Excluded scope
- Disability, pain acceptance, exercise adherence and autonomy support
- Other follow-up times and non-SRQ-E outcomes

## Case-specific application
- An explicitly labelled row test plus the source test-to-effect-size convention may identify the metric. Where the abstract and matching table/method disagree about the metric, retain a generic reported effect size and mark the metric unresolved. An unlabelled row test does not establish a metric.
- Preserve table qualitative grades as source-reported when they conflict with stated cutoffs; do not reclassify them. Retain unexplained printing suffixes in the review record without inventing their meaning or changing the numerical component. Keep each independent effect size separate from its raw change.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
