# B043 — Experimental-design curation

Paper: Transcriptomic profiling of chlorogenic acid and taurine treatment in human skin cells provides insights into cellular senescence mechanisms
DOI: 10.3389/fmolb.2026.1748185

## Objective
The CGA-only RNA-seq comparison in normal human epidermal keratinocytes and its matched untreated reference.

## Included scope
- Target material: Normal human epidermal keratinocyte preparations in GSE302932.
- Assays: Bulk RNA sequencing
- Time: The 24-hour exposure in the reported skin-cell RNA-seq experiment.

## Requested experimental factors
- CGA alone versus untreated control, dose and exposure duration

## Excluded scope
- Taurine-alone/combined treatments, melanocytes and fibroblasts
- GWAS, TWAS, CMap, network/pathway analyses and other skin-cell experiments

## Experiment resources (use supplied archives)
- GSE302932: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE302932

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
