# B018 — Experimental-design curation

Paper: Preliminary investigation on the impact of salty and sugary former foods on pig liver and plasma profiles using OMICS approaches
DOI: 10.1038/s41598-024-70310-z

## Objective
The salty-former-food branch of the liver LFQ proteomics experiment and its matched reference.

## Included scope
- Target material: Pig liver materials in the salty-former-food versus control comparison of the LFQ proteomics experiment.
- Assays: Label-free quantitative mass-spectrometry proteomics
- Time: The dietary exposure and terminal liver collection used for the selected proteomics comparison.

## Requested experimental factors
- Salty versus control diet, dietary salt exposure and exposure/terminal collection interval

## Excluded scope
- Sugary-diet (SU) samples/comparisons and PXD047855 plasma peptidomics
- Non-liver assays and numerical differential-protein results

## Experiment resources (use supplied archives)
- PXD049972: https://www.ebi.ac.uk/pride/archive/projects/PXD049972

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
