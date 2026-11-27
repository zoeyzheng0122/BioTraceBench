# B039 — Experimental-design curation

Paper: Female metabolic resilience and male-biased protein quality defects under hypoxia in human brain organoids
DOI: 10.1016/j.isci.2026.115714

## Objective
The article-defined hypoxic-injury condition versus healthy/normoxic controls for BXS0115 only; retain the actual hypoxia/reoxygenation schedule.

## Included scope
- Target material: BXS0115-derived human cerebral-organoid preparations in the hypoxic-injury proteomics experiment.
- Assays: Mass-spectrometry proteomics
- Time: The 4-month organoid injury experiment and its source-defined harvest endpoint.

## Requested experimental factors
- Hypoxia versus normoxic control, oxygen level, hypoxia/reoxygenation schedule and organoid age

## Excluded scope
- MAA3, HYS0103, PK and SP lines and cross-sex pooled comparisons
- Other maturation ages, metabolic/mitochondrial imaging, LDH/qPCR and unrelated Mendeley-resource assays

## Experiment resources (use supplied archives)
- 10.5281/zenodo.17993221: https://doi.org/10.5281/zenodo.17993221

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
