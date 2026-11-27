# B033 — Experimental-design curation

Paper: Human meibomian gland organoids to study epithelial homeostasis and dysfunction
DOI: 10.1093/procel/pwaf095

## Objective
The native tissue versus matching cultured organoids, retaining donor-to-derived-material links only where supported.

## Included scope
- Target material: Human meibomian-gland tissue preparations and their matching organoid preparations in the parallel scRNA-seq experiment.
- Assays: 10x single-cell RNA sequencing
- Time: The collection/culture stage used for the paired tissue/organoid sequencing experiment.

## Requested experimental factors
- Native tissue versus matched organoid preparation and reported collection/culture stage

## Excluded scope
- Mouse cultures, lipidomics, drug treatments and MAPK-inhibitor branches
- Cell-type proportions, clustering/marker results and independent functional assays

## Experiment resources (use supplied archives)
- SRP497138: https://www.ncbi.nlm.nih.gov/sra?term=SRP497138

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
