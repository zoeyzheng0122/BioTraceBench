# C005 — Clinical trial curation

Paper: Polatuzumab Vedotin Plus Rituximab, Gemcitabine, and Oxaliplatin in Relapsed or Refractory Diffuse Large B-Cell Lymphoma: Results From the Phase III, Randomized POLARGO Trial
DOI: 10.1200/JCO-25-02849

## Objective
The randomized POLARGO cohort.

## Included scope
- Population: Transplant-ineligible R/R DLBCL patients in the randomized POLARGO ITT efficacy population.
- Measures: Overall survival; Investigator-assessed progression-free survival; IRC-assessed overall response rate at end of treatment
- Time: The primary/final randomized-cohort analysis; ORR at the article-defined end of treatment.

## Requested statistics
- Main efficacy Table 2 OS/PFS medians and primary HRs; IRC end-of-treatment ORR counts/proportions and explicitly reported between-arm rate difference. Exclude landmark survival rates and CR-only response.

## Excluded scope
- Nonrandomized safety run-in, CR-only rate and other response categories
- Subgroup/sensitivity analyses, other survival landmarks and safety

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
