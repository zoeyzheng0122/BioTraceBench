# C001 — Clinical trial curation

Paper: Adjuvant icotinib for resected EGFR-mutated stage II–IIIA non-small-cell lung cancer (ICTAN, GASTO1002): a randomized comparison study
DOI: 10.1038/s41392-025-02358-w

## Objective
The 12-month icotinib comparison in ICTAN.

## Included scope
- Population: The ICTAN intention-to-treat population with completely resected EGFR-mutated stage II–IIIA NSCLC after adjuvant chemotherapy.
- Measures: Investigator-assessed disease-free survival (DFS); Overall survival (OS); Brain-metastasis-free survival (BMFS)
- Time: The main efficacy analysis and data cutoff reported in this article.

## Requested statistics
- DFS: reported arm medians and primary DFS HR; OS/BMFS: primary HRs only. Exclude landmark rates, event counts, per-protocol and subgroup analyses.

## Excluded scope
- The 6-month icotinib arm and all comparisons involving it
- Landmark survival rates, event-count endpoints, subgroup/per-protocol analyses, quality of life and safety

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
