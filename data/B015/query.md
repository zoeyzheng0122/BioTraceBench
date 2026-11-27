# B015 — Experimental-design curation

Paper: Stem Cell Differentiation Disperses Transcriptional Clusters via a Conserved Surface‐Condensate Trajectory
DOI: 10.1002/advs.75924

## Objective
The early neuronal-induction comparison assessed by Pol II immunofluorescence in ESC46C cells.

## Included scope
- Target material: Mouse ESC46C fixed-cell preparations used for Pol II immunofluorescence.
- Assays: Pol II Ser5P/Ser2P immunofluorescence imaging
- Time: The control/reference and 12-hour RHB-A induction points.

## Requested experimental factors
- RHB-A induction versus undifferentiated control and induction duration

## Excluded scope
- Other induction time points and the separate LIF-withdrawal protocol
- Fly/zebrafish experiments, H3K27ac/Western blot, mitotic-fraction archives and condensate simulation

## Experiment resources (use supplied archives)
- 10.5281/zenodo.19473110: https://doi.org/10.5281/zenodo.19473110

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
