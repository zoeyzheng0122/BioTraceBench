# C027 — Clinical trial curation

Paper: Testing a Personalized Approach to Chronic Low Back Pain: A Randomized Controlled Trial in Older Veterans
DOI: 10.1002/acr.25671

## Objective
The primary Personalized Aging Back Clinics comparison.

## Included scope
- Population: The intention-to-treat cohort of older veterans with chronic low back pain.
- Measures: Oswestry Disability Index; PROMIS-29 physical function; PROMIS Global physical health
- Time: Baseline to month 6.

## Requested statistics
- Baseline arm means, six-month arm changes and main adjusted mixed-model contrasts for ODI/PROMIS physical function/global physical health. Use exact model-specific secondary comparisons, not generic significance statements. Exclude other visits and healthcare-utilization endpoints.

## Excluded scope
- Months 3/9/12, mental-health and other PROMIS domains
- Pain, falls, life space, utilization and exploratory/sensitivity analyses

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
