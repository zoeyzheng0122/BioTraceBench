# B004 — Experimental-design curation

Paper: Recombinant ADAMTS-1 promotes muscle regeneration accompanied by downregulation of Notch signaling
DOI: 10.3892/ijmm.2025.5718

## Objective
rADAMTS-1-treated versus corresponding untreated/control differentiation materials.

## Included scope
- Target material: C2C12 preparations used for the rADAMTS-1 differentiation RNA-seq experiment.
- Assays: Bulk RNA sequencing
- Time: Three days of differentiation in the selected RNA-seq experiment.

## Requested experimental factors
- rADAMTS-1 versus control, concentration and differentiation duration

## Excluded scope
- Mouse muscle-injury regeneration and primary-cell proliferation experiments
- Independent differentiation staining and protein-level validation assays

## Experiment resources (use supplied archives)
- 10.5281/zenodo.17579631: https://doi.org/10.5281/zenodo.17579631

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
