# B029 — Experimental-design curation

Paper: PTBP1 inhibition reprograms myogenesis to rescue impaired muscle regeneration in mdx mice through correcting E2A splicing
DOI: 10.1038/s41467-026-70669-9

## Objective
PTBP1 knockdown versus its matched negative control during differentiation.

## Included scope
- Target material: C2C12 preparations undergoing differentiation in the PTBP1 knockdown experiment.
- Assays: Myotube immunofluorescence imaging
- Time: The differentiated-myotube imaging endpoint of this comparison; record source-defined intervals from transfection initiation, including the differentiation-medium switch and imaging collection.

## Requested experimental factors
- PTBP1 knockdown versus negative control, differentiation regimen and imaging collection interval

## Excluded scope
- PTBP1 overexpression, proliferation-phase and E12/E47 rescue/co-intervention branches
- Western blot, in vivo AAV/mdx, protein-degradation and other assays

## Experiment resources (use supplied archives)
- 10.6084/m9.figshare.29153381: https://doi.org/10.6084/m9.figshare.29153381

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
