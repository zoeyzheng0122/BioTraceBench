# B023 — Experimental-design curation

Paper: Reduced collagen degradation in pelvic urine precedes kidney fibrosis induced by unilateral ureteral obstruction
DOI: 10.1038/s41598-025-29217-6

## Objective
Compare renal-pelvis and bladder urine preparations collected on day 3 after unilateral ureteral obstruction (UUO), using the individual-urine CE-MS profiling experiment. Preserve all source-distinguishable sample names and their native CE-MS Analysis IDs.

## Included scope
- Target material: Individual urine preparations labelled as UUO pelvis or UUO bladder at day 3 in Supplementary Table S1, worksheet "Peptide relative abundances".
- Assays: Individual-urine capillary electrophoresis–mass spectrometry (CE-MS) peptidome profiling, excluding the separate peptide-sequence identification workflow.
- Time: Day 3 after UUO surgery.

## Requested experimental factors
- UUO procedure, urine compartment and post-surgery collection day. Describe the surgery/model and compartment in biological_model, biological_source or sample_material; record the numerical post-UUO collection interval in the condition table.

## Excluded scope
- Sham-operated samples, day-7 collections and other surgical/time branches.
- The separate Orbitrap Fusion CE-MS/MS peptide-sequence identification experiment, its RAW/MSF acquisitions, and PXD064569 acquisition mapping. The PRIDE archive is background evidence for this excluded branch, not the source of the target CE-MS sample-to-assay mapping.
- Kidney histology/fibrosis assays, peptide abundance values, statistical comparisons, correlations and peptide-sequence results.

## Row granularity and relationships
One sample per source-distinguishable urine preparation in the supplied Table S1 metadata. Read the group headings, Sample Name row and Analysis ID row together; do not turn a treatment/compartment group into a pooled sample. Retain native sample labels without interpreting suffixes as verified animal identities. Do not infer physical pooling, technical replicates or cross-compartment donor pairing from similar labels, equal suffixes, column order or group totals. Describe shared animal-cohort provenance where supported, and preserve individual pairing only if an explicit donor key is supplied.
One assay per native CE-MS Analysis ID, associated with its own urine preparation. Preserve that local identifier in Method; it is not a public sample accession. Do not assign PXD064569 to these CE-MS assays or duplicate them using the excluded CE-MS/MS branch. Use null for unsupported public sample/experiment accessions.

## Materials, missing values and response
Use the complete supplied paper, relevant supplements, figures and archived metadata. For Table S1, use only the group headings and native sample/analysis identifiers; do not extract, recalculate or score the numerical peptide-abundance matrix. Read captions and footnotes. Use frozen local sources. Preserve native labels, precision, units and zeros; use null for unsupported optional values. IDs/row order and synonymous wording do not change scientific identity.

## Experiment resources (use supplied archives)
- Main article: Methods, Animals; Mass-spectrometry analysis and data processing.
- `related/CE-MS-sample-header-metadata.csv`: native group, Analysis ID and Sample Name headers transcribed from Supplementary Table S1, worksheet "Peptide relative abundances"; the numerical peptide-abundance workbook is excluded from this input package.
- Supplementary Figure S1: animal-cohort and collected-urine counts.
- PXD064569 archive and EXP_DESIGN.xlsx: excluded CE-MS/MS sequence-identification branch, provided only to distinguish the acquisition workflows.

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
