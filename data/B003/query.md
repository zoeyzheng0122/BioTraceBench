# B003 — Experimental-design curation

Paper: Regulatory role of vitamin D 3 on myogenesis and fibrogenesis under Vdr gene silencing and TGF-β1 stimulation in skeletal muscle cells
DOI: 10.1038/s41598-025-25496-1

## Objective
Vdr siRNA versus negative-control siRNA; transfer co-treatments from other experiments only if the source explicitly assigns them to these proteomics samples.

## Included scope
- Target material: C2C12 skeletal-muscle-cell preparations collected for Vdr-knockdown proteomics.
- Assays: Mass-spectrometry proteomics
- Time: The transfection and collection schedule of the selected proteomics comparison.

## Requested experimental factors
- Vdr-targeting versus negative-control siRNA, transfection dose and collection interval

Extract siRNA identity, concentration and timing only when supported for the selected proteomics preparations. Distinguish transfection incubation duration from proteomics collection time. Do not infer collection time, co-treatments or replicate counts from other experiments; leave unsupported fields null.

## Excluded scope
- Vitamin-D-metabolite dose experiments and independent TGF-β1 combination experiments
- Western blots, staining, mitochondrial functional assays and other validation experiments

## Experiment resources (use supplied archives)
- PXD062669: https://www.ebi.ac.uk/pride/archive/projects/PXD062669

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
