# B008 — Experimental-design curation

Paper: Activation of TP53 target genes in the primary response of triple-negative breast cancer cells to doxorubicin treatment
DOI: 10.1038/s41598-025-31087-x

## Objective
The initial doxorubicin exposure versus its corresponding DMSO vehicle controls; curate the reused dataset as reused data.

## Included scope
- Target material: HCC1806 cells represented in the GSE174692 transcriptomic comparison used by this article.
- Assays: Bulk RNA sequencing
- Time: The article-defined initial 24-hour doxorubicin comparison.

## Requested experimental factors
- Initial doxorubicin versus DMSO vehicle-control exposure, dose and collection interval

Include only the control-siRNA (siNT) samples used in the article’s Table 2. Exclude the MLK4-targeting siRNA (siMLK4) branch of GSE174692.

## Excluded scope
- CAL51, other GEO accessions, resistant-cell and TP53-deletion branches
- Etoposide, qPCR, viability and other independent validation assays

## Experiment resources (use supplied archives)
- GSE174692: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE174692

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
