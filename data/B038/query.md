# B038 — Experimental-design curation

Paper: Long-term daily light exposure boosts human retinal organoid differentiation
DOI: 10.1038/s42003-026-10216-w

## Objective
The DIV210 proteomics comparison of native labelled primary-line control and light-conditioned pools, including the reported second-line validation.

## Included scope
- Target material: Human retinal-organoid preparations submitted to the DIV210 proteomics experiment.
- Assays: Mass-spectrometry proteomics
- Time: DIV210 collection.

## Requested experimental factors
- Daily light versus control, exposure regimen and collection DIV

## Excluded scope
- Other ages, qPCR, Western blot and immunofluorescence branches
- Treating each organoid within a reported pool or each technical replicate as an independent donor

## Experiment resources (use supplied archives)
- PXD065849: https://www.ebi.ac.uk/pride/archive/projects/PXD065849

## Unresolved acquisition mapping
Create separate acquisition/library records only when both their identities and links to the selected preparations are supported. Otherwise retain the source-supported aggregate, use the reported project/study accession, and explain the unresolved mapping in Method; do not assign every file to every sample.

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
