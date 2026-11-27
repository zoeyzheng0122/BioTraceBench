# B030 — Experimental-design curation

Paper: Regional diversity of cranial skeletal stem cells governs bone morphogenetic protein-2 mediated bone regeneration
DOI: 10.1038/s41467-026-76286-w

## Objective
The in vitro BMP-2 osteogenic-differentiation comparison in nasal and femoral SSCs, including their matched no-BMP-2 references.

## Included scope
- Target material: Nasal- and femoral-derived skeletal stem-cell preparations in the in vitro BMP-2 osteogenesis experiment.
- Assays: Alizarin Red osteogenic-differentiation staining
- Time: The endpoint of the selected in vitro osteogenic differentiation assay.

## Requested experimental factors
- SSC anatomical origin, BMP-2 versus matched control, dose and osteogenic differentiation duration

## Excluded scope
- Mandibular, parietal and occipital SSCs and chondrogenesis assays
- Wnt5a/Box5 interventions, renal-capsule transplants, calvarial defects and baseline transcriptomics

## Experiment resources (use supplied archives)
- 10.6084/m9.figshare.31968258: https://doi.org/10.6084/m9.figshare.31968258

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
