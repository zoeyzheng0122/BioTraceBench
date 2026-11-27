# B044 — Experimental-design curation

Paper: Optimizing DCD donor liver function with resveratrol during machine perfusion
DOI: 10.1038/s41598-025-26147-1

## Objective
The preservation-strategy comparison in the donor-liver RNA-seq experiment. Apply the acquisition-specific platform precedence below.

## Included scope
- Target material: Rat donor-liver tissue preparations in the selected preservation/reperfusion RNA-seq experiment.
- Assays: Bulk RNA sequencing
- Time: Collection after 1 hour of normothermic reperfusion.

## Requested experimental factors
- Asystolic warm-ischemia duration before preservation.
- Preservation temperature and duration for each selected preservation group.
- Normothermic reperfusion temperature and duration from reperfusion initiation to tissue collection.
- Resveratrol concentration during preservation for RES preparations, when supported.

Group identity belongs in Sample Name / Sample Material; do not create categorical group-name condition rows. Use numeric Factor Value with a separate Unit for the requested quantitative factors. Condition Target identifies the donor liver receiving the intervention, including when the assayed preparation is extracted RNA. Attach every condition to its receiving Sample ID and repeat supported shared conditions for each identifiable preparation. Preserve anchored English Time. Do not invent numerical zero-dose controls or expand routine preparation recipes into conditions.

## Sample membership and accession mapping
Use `related/ENA-PRJNA1309769/ENA_source_annotations.csv` and the accompanying source XML/JSON snapshots together with the article figures. Identify preparations from sample_alias, experiment_alias and library_name, and establish their preservation assignments from the selected experiment’s article design and figures. Match accessions through the supplied metadata fields, not row order or similar-looking suffixes. Generic sample titles alone do not establish a group. Preserve each identifiable preparation separately and link its Sample Accession to the registered experiment/run. One assay represents one identifiable acquisition; retain its parent experiment accession on the same row. Source-read labels such as R1 do not override the registered library layout.

## Platform conflict and source precedence
For Platform, prioritize acquisition-specific registered experiment metadata over the article's general sequencing-platform statement. Retain the conflicting instrument reported in the article in Method and explain the precedence decision in external notes with source locations. Do not combine the conflicting instruments as a confirmed joint platform or create another assay from this discrepancy. If experiment-specific metadata conflict with one another, leave the unresolved field null and document the conflicting sources; do not decide by majority vote. This curation rule chooses the reproducible extraction source and does not establish which physical sequencer was actually used.
For preservation groups, doses and intervals, use the selected experiment's article design, figure captions and relevant supplementary methods. ENA aliases establish preparation-to-accession links. Keep the two-hour preservation/reperfusion comparison separate from the three-hour dose-finding experiment.

## Excluded scope
- Perfusate time series, histology, metabolite and other functional assays.
- The naïve group and the separate three-hour resveratrol dose-finding experiment.
- Routine anesthesia, perfusate recipes, flow rates, flushing volumes, and library-preparation quantities as experimental conditions.
- Guessing preservation assignments from generic sample titles, file order or expression similarity.

## Experiment resources (use supplied archives)
- PRJNA1309769: https://www.ebi.ac.uk/ena/browser/view/PRJNA1309769

## Frozen sample annotations
- `related/ENA-PRJNA1309769/README.md`: snapshot provenance and file inventory.
- `related/ENA-PRJNA1309769/ENA_source_annotations.csv`: native aliases, sample/experiment/run accessions and acquisition metadata.
- `related/ENA-PRJNA1309769/ena-run-annotations.json`, `SAMN*.xml` and `SRX*.xml`: archived public metadata.
Use these supplied annotations without downloading raw reads or numerical omics matrices. No expected local IDs or answer row counts are supplied.

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
