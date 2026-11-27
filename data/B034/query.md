# B034 — Experimental-design curation

Paper: Human gastric extracellular matrix hydrogels maintain organoid growth and reduce gene expression associated with stemness and inflammation
DOI: 10.1088/1748-605X/ae943e

## Objective
Matrigel versus hgECM supplemented with Matrigel within each explicitly matched line/pair; preserve line, matrix-donor and dissociation-protocol distinctions.

## Included scope
- Target material: The assayed human gastric organoid preparations in the matched A–D matrix-culture single-cell experiment. Describe the culture-matrix reagent and its donor provenance in Biological Source, Sample Material or Method; do not create matrix-only sample rows. Matrix donors are not automatically organoid cellular donors.
- Assays: 10x single-cell RNA sequencing
- Time: The four-day matrix-culture collection in the paired library experiment.

## Requested experimental factors
- Culture matrix (Matrigel or hgECM plus Matrigel), matrix proportions, culture duration and distinguishing dissociation protocol

## Excluded scope
- PXD081816 matrix proteomics, matrix rheology, growth and independent validation assays
- Inferring that pair labels imply one common donor across all lines

## Experiment resources (use supplied archives)
- GSE303526: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE303526

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
