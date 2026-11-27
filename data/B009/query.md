# B009 — Experimental-design curation

Paper: Imbalanced chromatin distribution in cellular senescence specifies paraspeckle dynamics
DOI: 10.1186/s13059-025-03757-6

## Objective
Five-day etoposide versus the matched five-day vehicle condition.

## Included scope
- Target material: U2OS materials in the fixed-cell endogenous NONO/NEAT1_2 paraspeckle-imaging comparison.
- Assays: Sequential RNA-FISH/immunofluorescence with confocal imaging
- Time: The 5-day treatment endpoint.

## Requested experimental factors
- Etoposide versus vehicle, dose and exposure duration

## Excluded scope
- Nine-day exposure, live NONO-GFP tracking and other imaging branches
- IMR90, oxidative stress, HP1α manipulation and separate biochemical assays

## Experiment resources (use supplied archives)
- 10.6084/m9.figshare.29955509.v3: https://doi.org/10.6084/m9.figshare.29955509.v3

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
