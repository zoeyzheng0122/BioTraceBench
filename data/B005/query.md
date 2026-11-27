# B005 — Experimental-design curation

Paper: Proteomic analysis of 7-octenoic acid antifibrotic effects in TGF-β1 activated hepatic stellate cells
DOI: 10.1038/s41598-025-29722-8

## Objective
TGF-β1 alone versus TGF-β1 plus 7-OCT.

## Included scope
- Target material: LX-2 hepatic-stellate-cell preparations submitted to the selected label-free proteomics experiment.
- Assays: Label-free LC–MS/MS proteomics
- Time: The stimulation/co-treatment and harvest schedule of the proteomics comparison.

## Requested experimental factors
- TGF-beta1 stimulation and 7-OCT co-treatment, their doses and treatment/collection interval

## Excluded scope
- Huh-7 viability assays, molecular docking, migration and qPCR validation
- Any unactivated-control proteomics arm not explicitly present in this comparison

## Experiment resources (use supplied archives)
- PXD063183: https://www.ebi.ac.uk/pride/archive/projects/PXD063183

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
