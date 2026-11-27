# B013 — Experimental-design curation

Paper: Anti-resonance in developmental signaling regulates cell fate decisions
DOI: 10.7554/eLife.107794

## Objective
The frequency series at a fixed 55% duty cycle, retaining all explicitly registered frequencies and their replicates within that series.

## Included scope
- Target material: HEK293T Wnt input/output reporter-cell preparations in the LITOS screen. Represent each explicitly labelled frequency at the selected duty cycle as a separate condition-level preparation. Screen-repeat summaries alone do not establish individual biological sample IDs.
- Assays: End-point fluorescence imaging of the Wnt reporter screen
- Time: The 48-hour HEK293T LITOS stimulation experiment.

## Requested experimental factors
- Light-stimulation frequency, duty cycle and total stimulation duration

## Excluded scope
- All other duty cycles in the 96-condition screen and H9 differentiation experiments
- Separate live-cell stimulation experiments, simulations, re-running analysis code and fluorescence response values

## Experiment resources (use supplied archives)
- 10.5281/zenodo.17874586: https://doi.org/10.5281/zenodo.17874586

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
