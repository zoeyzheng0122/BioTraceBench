# B036 — Experimental-design curation

Paper: ​Temporal proteomic profiling of iPSC-derived human liver organoids reveals optimal maturation for drug metabolism and toxicology
DOI: 10.1038/s41598-025-32539-0

## Objective
The temporal TMT proteomics experiment of liver-organoid maturation, retaining supported preparation and multiplex/channel identities.

## Included scope
- Target material: iPSC-derived human liver organoid preparations used in the temporal TMT proteomics experiment.
- Assays: TMT mass-spectrometry proteomics
- Time: Days 7, 15, 30 and 45.

## Requested experimental factors
- Organoid maturation/collection stage and distinguishing culture-stage conditions

## Excluded scope
- Independent toxicant-exposure, viability and immunofluorescence assays
- Protein expression results or inferring an optimal maturation stage from abundance

## Experiment resources (use supplied archives)
- PXD063438: https://www.ebi.ac.uk/pride/archive/projects/PXD063438

## Unresolved acquisition mapping
Create separate acquisition/library records only when both their identities and links to the selected preparations are supported. Otherwise retain the source-supported aggregate, use the reported project/study accession, and explain the unresolved mapping in Method; do not assign every file to every sample.

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
