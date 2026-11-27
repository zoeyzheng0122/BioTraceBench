# B042 — Experimental-design curation

Paper: Extracellular vesicles derived from induced pluripotent stem cells mediate anti-inflammatory effects in primary human macrophages
DOI: 10.1038/s41598-026-49621-w

## Objective
iPSC-EV-treated macrophages versus the source-labelled EV-unexposed CTRL within the selected PXD067612 macrophage proteomics experiment. Retain supported PBMC-donor and EV-passage relationships; assign LPS/ATP only when the source links them to these preparations, not from parallel functional experiments or general methods.

## Included scope
- Target material: PBMC-derived macrophage recipient preparations in the selected PXD067612 proteomics experiment. PBMC origins and iPSC EV reagent provenance remain descriptive; EV producer cells are not macrophage donors.
- Assays: Macrophage mass-spectrometry proteomics
- Time: The treatment/collection interval of the macrophage proteomics experiment.

## Requested experimental factors
- iPSC-EV versus EV-unexposed control, supported EV dose/passage and treatment/collection interval; LPS/ATP only if explicitly assigned to these proteomics materials

## Excluded scope
- NT-2-EV-treated macrophages and PXD067567 EV-cargo-only proteomics
- miRNA panels, chemotaxis and independent functional assays

## Experiment resources (use supplied archives)
- PXD067612: https://www.ebi.ac.uk/pride/archive/projects/PXD067612

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
