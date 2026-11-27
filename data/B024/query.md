# B024 — Experimental-design curation

Paper: Extracellular C1qbp inhibits myogenesis by suppressing NFATc1
DOI: 10.1038/s41598-024-66549-1

## Objective
The gastrocnemius proteomics comparison in the young-mouse activity-loading experiment.

## Included scope
- Target material: Gastrocnemius preparations in the young male C57BL/6 activity-loading experiment.
- Assays: Mass-spectrometry proteomics
- Time: The terminal collection after the 3-week loading/unloading regimens.

## Requested experimental factors
- Treadmill running speed, incline, daily exercise duration and total regimen duration, and tail-suspension hindlimb unloading duration through terminal collection.
- Represent quantitative conditions with numeric Factor Value and a separate Unit. Retain intervention identity in the factor name and sample descriptions. Do not infer an unreported number of exercise days per week.

## Excluded scope
- The separate old-versus-young mouse cohort
- Histology and recombinant-C1qbp/NFATc1 cell intervention/functional assays

## Case-specific preparation and acquisition rules
Retain the Exercise and Unloading preparations and their RAW acquisitions in Sample_Code.xlsx. Use one group-level preparation per documented regimen and one assay per associated RAW file, retaining native file and acquisition labels in Method. Leave animal membership, pooling and fraction identity unresolved unless explicitly documented. Exclude Young and Old acquisitions and processed/search-result files as independent assays.
Describe the assayed material as the muscle-derived peptide digest. Report the instrument and LC system in Platform, and preparation/acquisition/analysis methods in Method. A project accession may be used in Experiment/Run Accession when no public acquisition accession is supplied; do not use it as a sample accession. Record material source disagreements in notes, including conflicting digestion times or software versions, without choosing an unsupported precise value.

## Experiment resources (use supplied archives)
- PXD043715: https://www.ebi.ac.uk/pride/archive/projects/PXD043715
- Local archive: related/PRIDE-PXD043715-files.json and related/PRIDE-PXD043715-files.csv (complete project inventory).
- Local acquisition-name mapping: related/Sample_Code.xlsx (unaltered official PRIDE file). Read the mapping and filename metadata, not numerical proteomic matrices or raw spectra.

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
