# B031 — Experimental-design curation

Paper: 9-cis-Retinoic Acid Improves Disease Modelling in iPSC-Derived Liver Organoids
DOI: 10.3390/cells14130983

## Objective
Archived iPSC-derived hepatocyte preparations versus HepaRG references.

## Included scope
- Target material: The source-registered iHEP_P2 preparations and HepaRG reference preparations in GSE292959; exclude iHSC stellate-cell preparations.
- Assays: Bulk RNA sequencing
- Time: The collection stage of the registered iHEP_P2/HepaRG comparison; do not equate a title suffix with differentiation day or assume a Day-21 mapping without explicit support.

## Requested experimental factors
- Preparation identity and source-reported differentiation/collection stage; do not transfer 9CRA status from a separate functional branch.

## Excluded scope
- Earlier iPSC/iHepatocyte differentiation points and primary human hepatocyte reference samples
- Stellate-cell, 9CRA, fibrosis, mixed-organoid and independent functional assays

## Experiment resources (use supplied archives)
- GSE292959: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE292959

- Frozen database metadata: `related/GEO-GSE292959-family.soft.txt`, `related/ENA-PRJNA1242238-run-metadata.tsv`.

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
