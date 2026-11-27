# B048 — Experimental-design curation

Paper: Ex vivo- generated lymphoid progenitors encompass both T cell and innate lymphoid cell fates
DOI: 10.3389/fimmu.2025.1617707

## Objective
The source-comparison scRNA-seq experiment in DLL4-cultured ProT products.

## Included scope
- Target material: Day 7 ProT products submitted to scRNA-seq, without implying Day 0 sequencing.
- Assays: Single-cell RNA sequencing
- Time: After 7 days of ProT culture.

## Requested experimental factors
- Cord-blood versus mobilized-peripheral-blood source, DLL4 platform and ProT culture duration

## Excluded scope
- Mass/flow cytometry, CD161-sorted functional studies, BCL11B perturbation and transplantation
- Treating a CD7 transcript-filtered analysis subset as a newly collected sample and extracting cell-cluster results

## Experiment resources (use supplied archives)
- GSE292844: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE292844

- Frozen database metadata: `related/GEO-GSE292844-family.soft.txt`, `related/ENA-PRJNA1241729-run-metadata.tsv`.

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
