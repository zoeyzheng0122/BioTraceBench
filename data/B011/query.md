# B011 — Experimental-design curation

Paper: IVNS1ABP mutation drives cellular senescence in newly identified progeroid neuropathy
DOI: 10.1038/s41467-026-70756-x

## Objective
The NPC-stage IVNS1ABP genotype comparison in isogenic pair III.

## Included scope
- Target material: NPC preparations from the article’s isogenic pair III.
- Assays: Bulk RNA sequencing
- Time: The NPC-stage RNA-seq sampling point.

## Requested experimental factors
- IVNS1ABP genotype (control, F253C/F253C or knockout) and NPC collection stage

## Excluded scope
- iPSC-stage sequencing within the same accession
- AP-MS, organoid functional validation and independent immunostaining

## Experiment resources (use supplied archives)
- GSE270946: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE270946

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
