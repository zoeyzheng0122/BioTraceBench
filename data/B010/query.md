# B010 — Experimental-design curation

Paper: ATR regulates OCT4 phosphorylation and safeguards human naïve pluripotency
DOI: 10.1038/s41598-025-97829-z

## Objective
Naïve versus primed pluripotent states in the reported OCT4-targeted purification/MS series; retain explicitly distinguishable clones and runs.

## Included scope
- Target material: Affinity-purified OCT4 preparations actually used for the selected targeted MS experiment
- Assays: Affinity-purification LC–MS/MS for OCT4 phosphorylation-site mapping
- Time: The primed/naïve culture-state and sample-preparation schedule of this targeted MS experiment.

## Requested experimental factors
- Naive versus primed pluripotent state, reported clone identity, and state-specific culture/collection interval

## Excluded scope
- PXD030230 global phosphoproteomics
- ATR inhibition, UV/CPT DNA-damage, apoptosis and independent Western-blot/functional assays

## Experiment resources (use supplied archives)
- PXD033619: https://www.ebi.ac.uk/pride/archive/projects/PXD033619

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
