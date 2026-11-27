# B040 — Experimental-design curation

Paper: Free-floating long-term vascularized mesenchymal organoids
DOI: 10.1016/j.isci.2025.114548

## Objective
The organoid maturation time series, retaining documented HUVEC/MSC source and pooled-organoid relationships.

## Included scope
- Target material: Identifiable organoid pools sampled for the GSE297746 temporal bulk RNA-seq experiment. HUVEC and MSC starting cells are biological-source attributes, not additional sample rows.
- Assays: Bulk RNA sequencing
- Time: Days 3, 14, 28 and 60.

## Requested experimental factors
- Culture duration at collection
- HUVEC:MSC seeding ratio
- Matrigel concentration at seeding
- Initial cell number per organoid

## Excluded scope
- The separate day-14 spheroid/matrix-structure comparison within GSE297746
- GSE297680 scRNA-seq, tumor invasion, other functional assays and expression-result extraction

## Experiment resources (use supplied archives)
- GSE297746: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE297746

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
