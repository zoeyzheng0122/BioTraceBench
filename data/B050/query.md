# B050 — Experimental-design curation

Paper: Evaluation of MSC‐Secretome Effects in an Ex Vivo Compartmentalized Osteochondral Interface Model
DOI: 10.1155/sci/3275855

## Objective
The cartilage-side supernatant MMP-activity experiment assessing inflammatory and MSC-secretome exposures, including its untreated reference.

## Included scope
- Target material: Day-3 cartilage-side supernatants actually submitted to the MMP activity assay. Keep explant origins and CM/pCM reagent provenance in descriptive fields; do not create separate producer-cell or excised-cartilage Western-blot samples.
- Assays: Fluorometric MMP activity assay of cartilage supernatants
- Time: Day 3 after the defined inflammatory/conditioned-medium treatment, following the reported acclimatization.

## Requested experimental factors
- Inflammatory cytokine combination, CM/pCM treatment and source-supported dose, cartilage compartment and supernatant collection interval

## Excluded scope
- Other collection days, bone-side outcomes, Western blots, metabolic-activity and sGAG assays
- Independent model-integrity and conditioned-medium characterization experiments, and numerical MMP results

## Experiment resources (use supplied archives)
- 10.5281/zenodo.18173753: https://doi.org/10.5281/zenodo.18173753

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
