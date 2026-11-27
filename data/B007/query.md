# B007 — Experimental-design curation

Paper: Post-replicative chromatin accessibility predicts cell fate change
DOI: 10.1016/j.stemcr.2026.102821

## Objective
The naïve-to-primed differentiation chromatin-accessibility experiment, including its matched chromatin preparations.

## Included scope
- Target material: Mouse ESC/EpiLC preparations in the naïve-to-primed differentiation branch.
- Assays: Replication-coupled ATAC sequencing; The matched bulk/unreplicated ATAC controls for this same differentiation branch
- Time: 0, 9 and 48 hours after the switch to EpiLC induction conditions.

## Requested experimental factors
- Differentiation induction time, EdU/replication-labelling schedule and replication-coupled versus bulk chromatin preparation

## Excluded scope
- MEF reprogramming, proliferation-dye sorting and other experiments in GSE296014
- Flow cytometry, independent motif/ChIP datasets and accessibility result matrices

## Experiment resources (use supplied archives)
- GSE296014: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE296014

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
