# B026 — Experimental-design curation

Paper: Single-cell RNA sequencing dataset of hearts from wild type and Cyp26b1 knockout mouse embryos
DOI: 10.1038/s41597-025-05497-5

## Objective
Cyp26b1 knockout versus wild type at E12.5; preserve source-supported embryo, pooled-heart and library relationships.

## Included scope
- Target material: Embryonic mouse heart preparations in the Cyp26b1 dataset.
- Assays: Single-cell RNA sequencing
- Time: Embryonic day E12.5 only.

## Requested experimental factors
- Cyp26b1 genotype and embryonic collection stage

## Excluded scope
- E10.5, E11.5 and E13.5 samples
- Cell-cluster annotations as sample identities, raw FASTQ processing and RDS/expression-result reanalysis

## Experiment resources (use supplied archives)
- 10.6084/m9.figshare.29088062: https://doi.org/10.6084/m9.figshare.29088062

## Library record scope
Curate the gene-expression cDNA libraries for the selected stage in Supplementary Table S3. Create one assay record per distinct cDNA library. Preserve companion oligo libraries and split FASTQ-file identities as technical context in Method; file partitions alone do not create additional assays.

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
