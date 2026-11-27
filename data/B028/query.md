# B028 — Experimental-design curation

Paper: Loss of calcium‐dependent phospholipase A2 contributes to multi‐omic changes in mouse denervated skeletal muscle
DOI: 10.14814/phy2.70906

## Objective
The gastrocnemius RNA-seq experiment testing cPLA2 status and the denervation procedure, including matched sham comparisons.

## Included scope
- Target material: Mouse gastrocnemius preparations in the cPLA2 loss-of-function RNA-seq experiment.
- Assays: Bulk RNA sequencing
- Time: The terminal RNA-seq collection after the article-defined denervation/sham schedule.

## Requested experimental factors
- cPLA2 genotype, denervation versus sham and post-procedure collection interval

## Excluded scope
- Lipidomics, metabolomics, respiration, GPCR and independent functional assays
- Expression values and differential-expression/pathway conclusions

## Experiment resources (use supplied archives)
- 10.6084/m9.figshare.32125855: https://doi.org/10.6084/m9.figshare.32125855

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
