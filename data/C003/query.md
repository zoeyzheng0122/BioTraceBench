# C003 — Clinical trial curation

Paper: Orelabrutinib versus chemoimmunotherapy in treatment-naïve chronic lymphocytic leukemia/small lymphocytic lymphoma: a randomized, phase 3 trial
DOI: 10.1038/s41392-026-02818-x

## Objective
The primary randomized treatment-naive CLL/SLL comparison reported in this study.

## Included scope
- Population: The treatment-naïve CLL/SLL ITT population of the randomized phase 3 study.
- Measures: IRC-assessed progression-free survival; IRC-assessed overall response rate; IRC-assessed duration of response
- Time: The interim efficacy analysis reported in this article.

## Requested statistics
- IRC PFS and DoR: arm medians and primary HRs. IRC ORR: the reported Table 2 responder counts/proportions and primary OR. Recover response categories and the DoR responder population from the statistical analysis plan response definitions and the matching reported analysis. Exclude landmark rates and investigator alternatives.

## Excluded scope
- Investigator-assessed outcomes, OS and landmark survival estimates
- Subgroups, biomarkers, PROs and safety

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
