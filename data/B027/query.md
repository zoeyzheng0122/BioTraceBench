# B027 — Experimental-design curation

Paper: Mouse skeletal muscle satellite cells co-opt the tenogenic gene Scleraxis to instruct regeneration
DOI: 10.7554/eLife.95854

## Objective
Scx conditional-knockout versus control mice; retain documented muscle pooling without inferring donor identities.

## Included scope
- Target material: Sorted YFP-lineage satellite-cell preparations submitted to the selected scRNA-seq experiment
- Assays: 10x single-cell RNA sequencing
- Time: 2.5 days after BaCl2 injury.

## Requested experimental factors
- Scx conditional genotype, BaCl2 injury and collection interval

## Excluded scope
- CUT&RUN, independent cultured-myoblast and differentiation/fusion experiments
- External muscle atlases, trajectory/cluster results and other post-injury time points

## Experiment resources (use supplied archives)
- 10.6084/m9.figshare.24783750: https://doi.org/10.6084/m9.figshare.24783750

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
