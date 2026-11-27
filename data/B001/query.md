# B001 — Experimental-design curation

Paper: Seco-Duocarmycin SA in Aggressive Glioblastoma Cell Lines
DOI: 10.3390/ijms26062766

## Objective
Seco-DSA treatment versus untreated LN18 controls.

## Included scope
- Target material: LN18 glioblastoma cells and the actual cell preparations/lysates used for the selected proteomics experiment.
- Assays: LC–MS/MS proteomics
- Time: The 48-hour treatment and its proteomics sample-collection endpoint.

## Requested experimental factors
- Seco-DSA exposure (including the selected untreated condition), concentration and duration

## Excluded scope
- T98G, dose-screening and cell-viability experiments
- Independent migration, invasion, apoptosis and other functional assays

## Experiment resources (use supplied archives)
- PXD061023: https://www.ebi.ac.uk/pride/archive/projects/PXD061023

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
