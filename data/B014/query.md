# B014 — Experimental-design curation

Paper: Temporal multiomics gene expression data across human embryonic stem cell-derived polyhormonal cell differentiation
DOI: 10.1038/s41597-026-06606-8

## Objective
The initial-to-terminal RNA-seq comparison in the polyhormonal-cell differentiation experiment.

## Included scope
- Target material: RUES2 hESC-derived materials in the polyhormonal-cell differentiation dataset.
- Assays: Bulk RNA sequencing
- Time: Day 0 and Day 17 collection points only.

## Requested experimental factors
- Differentiation stage and collection day; earlier induction steps remain preparation history

## Excluded scope
- All RNA-seq collection points other than Day 0 and Day 17, including intermediate-day samples and separate upstream-material rows
- Ribosome profiling, proteomics, other lineage branches and expression matrices

## Experiment resources (use supplied archives)
- GSE305933: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE305933

- Frozen database metadata: `related/GEO-GSE305933-family.soft.txt`.

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
