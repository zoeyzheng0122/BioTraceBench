# C038 — Clinical trial curation

Paper: Efficacy, Safety, and Pharmacokinetics of Upadacitinib Among Patients in East Asia With Moderately to Severely Active Ulcerative Colitis: A Post Hoc Subanalysis of Randomized Phase 3 Studies
DOI: 10.1111/jgh.70634

## Objective
The UC1 induction comparison of upadacitinib 45 mg daily and placebo.

## Included scope
- Population: East Asian patients in the UC1 (U-ACHIEVE induction) efficacy analysis population only.
- Measures: Clinical remission per adapted Mayo score; Clinical response per adapted Mayo score; Endoscopic improvement
- Time: UC1 induction week 8 only.

## Requested statistics
- Table 2 East Asian UC1 week-eight percentages/CI and reported treatment differences for the three specified criteria. Include responder counts only if explicitly reported; do not infer them from rounded percentages. Exclude overall UC1, UC2 and maintenance results.

## Excluded scope
- UC2, UC3, pooled/global populations and biologic-failure subgroups
- Other efficacy thresholds, PK and safety

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
