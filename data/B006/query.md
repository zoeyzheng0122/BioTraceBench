# B006 — Experimental-design curation

Paper: Matrix stiffness induces midnolin-dependent lamin B1 degradation to control myoblast differentiation
DOI: 10.1038/s44319-026-00753-0

## Objective
The matrix-stiffness RNA-seq branch represented in the supplied GSE323368 sample records.

## Included scope
- Target material: C2C12 RNA-seq materials in the matrix-stiffness branch represented in the archived GSE323368 metadata.
- Assays: Bulk RNA sequencing
- Time: The 12-hour matrix-exposure point registered for this RNA-seq branch.

## Requested experimental factors
- Matrix/coating identity and stiffness, and RNA collection interval

## Excluded scope
- The separate differentiation time series within the same accession
- Early protein-degradation inhibitor, imaging and Western-blot experiments

## Experiment resources (use supplied archives)
- GSE323368: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE323368
- B006-published-source-data: https://pmc-oa-opendata.s3.amazonaws.com/PMC13172543.1/44319_2026_753_MOESM5_ESM.zip

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
