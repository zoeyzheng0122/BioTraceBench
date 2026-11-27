# B002 — Experimental-design curation

Paper: Comparative effects of standardized Centella asiatica extract (ECa 233) and its active compound mixture on proteomics and mitochondrial function
DOI: 10.1038/s41598-025-12622-2

## Objective
The treatment-formulation proteomics comparison in differentiated SH-SY5Y cells.

## Included scope
- Target material: Differentiated SH-SY5Y preparations used for proteomics.
- Assays: Mass-spectrometry proteomics
- Time: The treatment and collection interval of the reported proteomics experiment.

## Requested experimental factors
- Treatment formulation (control, ECa 233 or MDS + ASS), compound concentrations and exposure duration

## Excluded scope
- Rat hippocampal electrophysiology and long-term potentiation experiments
- Independent mitochondrial respiration, pharmacological validation and other non-proteomic assays

## Experiment resources (use supplied archives)
- PXD057572: https://www.ebi.ac.uk/pride/archive/projects/PXD057572

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
