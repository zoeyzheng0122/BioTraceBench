# B012 — Experimental-design curation

Paper: Stereotyped Subclones Revealed by High‐Density Single‐Cell Lineage Tracing Support Robust Development
DOI: 10.1002/advs.202406208

## Objective
The non-differentiating HESC reference and the differentiating colonies in this simultaneous PLP lineage/transcriptome experiment; keep colony identity and paired assay relationships only when explicitly supported.

## Included scope
- Target material: Lineage-tracer hESC preparations and colonies in the simultaneous PLP lineage/transcriptome experiment.
- Assays: Single-cell transcriptome sequencing; Matched expressed-lineage-barcode sequencing
- Time: The 10-day primordial-lung-progenitor differentiation experiment and its matched HESC reference.

## Requested experimental factors
- Non-differentiating reference versus PLP differentiation, induction duration and lineage-labelling context

## Excluded scope
- The separate full 20-day differentiation experiment and later alveolar-sphere validation
- Reconstructing lineage trees, counting cells as independent biological sources, or extracting clone/transcriptomic results

## Experiment resources (use supplied archives)
- PRJNA1099925: https://www.ebi.ac.uk/ena/browser/view/PRJNA1099925

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
