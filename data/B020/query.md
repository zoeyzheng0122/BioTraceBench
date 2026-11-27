# B020 — Experimental-design curation

Paper: Estrogen Stabilizes Interferon-Inducible Genes During Skeletal Muscle Regeneration
DOI: 10.1177/10998004251411301

## Objective
The hormone-replacement microarray experiment across its reported post-injury time series.

## Included scope
- Target material: Right lateral gastrocnemius materials from the ovariectomized-mouse estrogen-treatment injury experiment.
- Assays: Affymetrix Mouse Gene 1.0 ST microarray
- Time: 32, 96 and 192 hours after injury.

## Requested experimental factors
- OVX hormone replacement (17beta-estradiol or placebo), dose, muscle-injury procedure and post-injury collection time

## Excluded scope
- Independent CD169 immunostaining and other tissue/protein validation
- Gene-expression values, differential-expression, correlation and pathway results

## Experiment resources (use supplied archives)
- GSE311704: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE311704

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
