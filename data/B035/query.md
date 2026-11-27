# B035 — Experimental-design curation

Paper: Early differential impact of MeCP2 mutations on functional networks in Rett syndrome patient-derived human cortical organoids
DOI: 10.1038/s41467-026-71458-0

## Objective
R306C versus its isogenic control in the global CAG-driven GCaMP6f calcium-imaging branch.

## Included scope
- Target material: Patient-derived MECP2 R306C cortical organoids and their matched isogenic-control preparations.
- Assays: Three-photon calcium imaging
- Time: The 3-month cortical-organoid imaging experiment.

## Requested experimental factors
- MECP2 R306C versus isogenic genotype, organoid age and CAG-driven GCaMP6f reporter context

## Excluded scope
- V247X and its controls, DLX-marked cell-specific imaging and other organoid ages
- RNA-seq, WES, EEG comparisons and independent functional validation
- Drug-rescue, acute blocker, CAY10683/Baclofen and CNQX/AP5/bicuculline challenge branches; reporter-specific GAD2/DLX alternatives

## Experiment resources (use supplied archives)
- 10.5281/zenodo.18487289: https://doi.org/10.5281/zenodo.18487289
- B035-published-source-data: https://pmc-oa-opendata.s3.amazonaws.com/PMC13260836.1/41467_2026_71458_MOESM4_ESM.xlsx

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
