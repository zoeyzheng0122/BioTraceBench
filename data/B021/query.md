# B021 — Experimental-design curation

Paper: Hypothyroidism impairs skeletal muscle regeneration after injury by altering myogenic and nonmyogenic pathways
DOI: 10.1172/jci.insight.197761

## Objective
The post-injury tibialis-anterior scRNA-seq comparison of thyroid status, retaining source-supported pooling and sample identities.

## Included scope
- Target material: Tibialis anterior muscle preparations in the control-versus-hypothyroid scRNA-seq experiment.
- Assays: Single-cell RNA sequencing
- Time: Day 5 after muscle injury.

## Requested experimental factors
- Thyroid status, hypothyroidism induction, cardiotoxin injury and post-injury collection day

## Excluded scope
- Uninjured/day-0 and day-14 sampling points
- Fucci models, histology, cell-type-specific follow-up assays and reanalysis of cell expression/count matrices

## Experiment resources (use supplied archives)
- GSE311479: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE311479

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
