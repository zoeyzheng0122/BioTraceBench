# B022 — Experimental-design curation

Paper: A multiomics analysis identifies retinol metabolism in fibroblasts as a key pathway in wound healing
DOI: 10.1172/jci.insight.194188

## Objective
The dietary vitamin-A wound-tissue DIA proteomics comparison.

## Included scope
- Target material: Day-5 wound-tissue materials in the untargeted DIA proteomics comparison.
- Assays: Untargeted DIA mass-spectrometry proteomics
- Time: Five days after wounding.

## Requested experimental factors
- Vitamin-A-deficient versus chow diet, exposure duration and post-wounding collection day

## Excluded scope
- PXD061256 SureQuant targeted proteomics and unwounded-skin samples
- RNA-seq, metabolomics, Western blot, immunostaining and other wound experiments

## Experiment resources (use supplied archives)
- PXD061167: https://www.ebi.ac.uk/pride/archive/projects/PXD061167

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
