# B017 — Experimental-design curation

Paper: A dataset of spatially resolved transcriptomics of post-natal cardiac development in mice
DOI: 10.1038/s41597-025-05838-4

## Objective
The postnatal cardiac-development Stereo-seq series, retaining source-supported animal, section, library and batch relationships.

## Included scope
- Target material: Measured heart sections in the P0/P7/P56 cardiac Stereo-seq dataset Animals remain biological-source description; chips/libraries do not substitute for biological preparations.
- Assays: Stereo-seq spatial transcriptomics
- Time: Postnatal P0, P7 and P56 sampling.

## Requested experimental factors
- Postnatal age and section preparation conditions distinguishing the requested spatial libraries

## Excluded scope
- Treating developmental stage as an administered intervention
- Independent validation assays and reprocessing FASTQ, spatial expression matrices or RDS files

## Experiment resources (use supplied archives)
- GSE298650: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE298650

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
