# B016 — Experimental-design curation

Paper: PiR48444 inhibits MSC osteogenic differentiation and bone regeneration via targeting METTL7A/eIF4E-mediated BMP2 m6A methylation
DOI: 10.1038/s42003-026-09583-1

## Objective
The SHED piR48444-knockdown ALP-staining experiment and its matched reference.

## Included scope
- Target material: SHED dental-pulp-stem-cell preparations undergoing the selected osteogenic differentiation experiment.
- Assays: ALP staining
- Time: Day 7 of the selected osteogenic differentiation experiment.

## Requested experimental factors
- piR48444 knockdown versus matched control and osteogenic differentiation/ALP collection day

## Excluded scope
- piR48444 overexpression, other piRNAs, other MSC sources and downstream METTL7A/BMP2/PIWIL1 interventions
- Day-14 ARS, qPCR, sequencing, in vivo bone-defect and other validation assays

## Experiment resources (use supplied archives)
- 10.6084/m9.figshare.31042333: https://doi.org/10.6084/m9.figshare.31042333

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
