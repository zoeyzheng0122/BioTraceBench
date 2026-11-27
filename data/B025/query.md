# B025 — Experimental-design curation

Paper: Exercise Training Stimulates the Release of Glutathione Peroxidase 1 ( GPX1 )‐Enriched Extracellular Vesicles That Promote Angiogenesis
DOI: 10.1096/fj.202505096RR

## Objective
Exercise-associated EVs (ExerVs) versus sedentary EVs (SedVs), retaining the actual donor-to-plasma-to-EV material chain where supported.

## Included scope
- Target material: Selected mouse plasma-derived EV preparations Donor identity is biological-source context; totals do not establish individual chains.
- Assays: NanoLC-MS proteomics
- Time: Collection immediately after the final bout of the 4-week endurance-training protocol.

## Requested experimental factors
- Exercise versus sedentary regimen, training duration and plasma collection relative to final bout

## Excluded scope
- EV injections, HUVEC assays, immobilization/recovery and GPX1 liposome experiments
- Cryo-EM/NTA and other independent characterization assays

## Experiment resources (use supplied archives)
- PXD064533: https://www.ebi.ac.uk/pride/archive/projects/PXD064533

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
