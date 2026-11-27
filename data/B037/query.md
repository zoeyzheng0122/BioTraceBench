# B037 — Experimental-design curation

Paper: TGF- β signaling promotes astroglial activation and TDP-43 proteinopathy in organoid models of frontotemporal lobar degeneration
DOI: 10.1172/JCI190035

## Objective
GRN−/− versus GRN+/+ at the same 16-week collection point.

## Included scope
- Target material: Native WTC11/isogenic GRN-null CX organoid preparations at 16 weeks in GSE282668; exclude KOLF2.1J and its R493X cohort.
- Assays: Single-cell RNA sequencing
- Time: Week 16 only.

## Requested experimental factors
- GRN genotype and organoid collection age

## Excluded scope
- Weeks 5/25, the independent GRN R493X cohort and TGF-β inhibition
- Animal tissue, functional assays and transcriptomic cluster/trajectory results

## Experiment resources (use supplied archives)
- GSE282668: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE282668

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
