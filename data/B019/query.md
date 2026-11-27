# B019 — Experimental-design curation

Paper: The long non-coding RNA landscape of endurance exercise training
DOI: 10.1016/j.molmet.2026.102358

## Objective
The male gastrocnemius RNA-seq comparison at the final endurance-training endpoint and its matched reference.

## Included scope
- Target material: Male Fischer 344 rat gastrocnemius (SKM-GN/SKMGN) materials in the MoTrPAC-derived RNA-seq resource.
- Assays: Bulk RNA sequencing
- Time: The 8-week training endpoint and its matched control collection.

## Requested experimental factors
- Endurance training versus sedentary control and training/collection duration

## Excluded scope
- Female rats, vastus lateralis and every other tissue, reference RNA/vial controls and other training durations
- ATAC-seq, methylation, proteomics, cross-tissue analyses and lncRNA expression results

## Experiment resources (use supplied archives)
- GSE242358: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE242358

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
