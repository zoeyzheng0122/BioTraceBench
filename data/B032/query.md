# B032 — Experimental-design curation

Paper: A xeno-free human iPSC-derived prostate organoid platform for multilineage differentiation and genetic manipulation
DOI: 10.1016/j.crmeth.2026.101538

## Objective
Week-6 monoculture organoids versus undifferentiated iPSCs.

## Included scope
- Target material: Monoculture-derived prostate organoids and the undifferentiated iPSC reference materials used in the matched bulk-transcriptomic experiment.
- Assays: Bulk RNA sequencing
- Time: Week 6 of monoculture differentiation and the undifferentiated reference.

## Requested experimental factors
- Monoculture organoid versus undifferentiated iPSC condition and culture stage

## Excluded scope
- Week-10 samples, scRNA-seq, co-culture, DHT withdrawal, gene manipulation and earlier-stage imaging experiments
- Independent histology/immunostaining and transcriptional-result extraction

## Experiment resources (use supplied archives)
- 10.5281/zenodo.20427357: https://doi.org/10.5281/zenodo.20427357
- PRJEB101277: https://www.ebi.ac.uk/ena/browser/view/PRJEB101277

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
