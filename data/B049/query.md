# B049 — Experimental-design curation

Paper: Matrix Stiffness Induces Endothelial Network Senescence
DOI: 10.1002/advs.76304

## Objective
Soft versus Stiff hydrogel conditions after the initial network-formation period.

## Included scope
- Target material: Human endothelial-network preparations used for the day-4 senescence-marker qRT-PCR comparison.
- Assays: qRT-PCR for CDKN1A/CDKN2A
- Time: 48 hours of initial network formation followed by 48 hours in the assigned stiffness condition (day 4).

## Requested experimental factors
- Soft versus dynamically stiffened hydrogel, stiffness-switch schedule and qRT-PCR collection interval

## Excluded scope
- Intermediate-stiffness conditions, Notch/JNK drug interventions and implant-capsule cohorts
- Western blot, immunofluorescence, dsDNA, SA-β-gal, sequencing and other assays

## Experiment resources (use supplied archives)
- 10.7924/r4r535: https://doi.org/10.7924/r4r535

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
