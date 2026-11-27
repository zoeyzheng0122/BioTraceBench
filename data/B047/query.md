# B047 — Experimental-design curation

Paper: Matrix Stiffness Governs Fibroblasts’ Regulation of Gingival Immune Homeostasis
DOI: 10.1002/adma.202520717

## Objective
Figure 3C: the stimulated hydrogel-culture supernatant ELISA experiment.

## Included scope
- Target material: Culture supernatants actually assayed by ELISA in Figure 3C. Interventions act on the upstream GF-containing hydrogel culture, not on already collected supernatants.
- Assays: ELISA of secreted inflammatory mediators
- Time: The hydrogel stimulation-to-supernatant-collection schedule used in Figure 3C.

## Requested experimental factors
- Nominal matrix storage modulus (G′), retaining source numerical precision and units
- Pam3CSK4 concentration and stimulation-to-supernatant-collection duration from the hydrogel exposure method and Table T2
- The preceding culture interval as preparation history and anchored Time, without adding a separate routine-culture condition

## Excluded scope
- RNA-seq/qPCR, DNA-methylation/actin pharmacology, human-tissue/explant and myeloid co-culture branches
- Cytokine concentration values, BCA outputs and other independent assay results
- Unstimulated supplementary cytokine comparisons, other receptor agonists and the distinct explant-specific Pam3CSK4 dose
- Inferring donor, aliquot, pooling or run identities from replicate counts or positional result labels

## Case-specific culture and assay rules
Use every stiffness condition plotted in Figure 3C. Take agonist concentration from the hydrogel treatment entry in Table T2 and take stimulation-to-collection timing from the hydrogel exposure method. The preceding culture period is preparation history; distinguish it from time after agonist addition. Keep numerical Factor Value separate from Unit, retain source precision, and attach conditions to the source GF-containing hydrogel culture. Source human gingival fibroblasts and matrix/reagent provenance remain distinct.

Use the public Dryad README descriptions to identify Figure 3C files and group labels. The descriptions cover multiple experiments; maintain the Figure 3C boundary. For this task, represent each stiffness group as a group-level supernatant preparation. Replicate counts and Rep 1–4 result positions do not identify original donors, preparations or shared aliquots across cytokines. Do not infer physical pooling or generate biological samples from result position alone.

Keep BioLegend kit details and reported protein normalization in Method. Platform denotes the reported detection instrument; leave it null when the reader model is unreported. Do not import the microscope, flow cytometer or rheometer from another assay. Use one labelled aggregate ELISA assay when individual acquisitions are unassigned; mark the repository DOI as a dataset, not a sample/run accession.

## Row granularity and relationships
Use one group-level supernatant sample per Figure 3C stiffness condition and one labelled aggregate ELISA assay across those groups. Generic source fibroblasts, matrices and intermediate cultures stay in Biological Source / Sample Material, not extra sample rows. Conditions identify the source receiving culture. Positional result labels do not establish independent physical sample identities or aliquot crosswalks; multiple sample associations do not assert pooling.

## Experiment resources (use supplied archives)
- 10.5061/dryad.xksn02vw6: https://doi.org/10.5061/dryad.xksn02vw6

## Frozen supplementary annotations
- `related/Dryad-xksn02vw6/Dryad_README_from_landing.md`: complete publicly displayed README converted from the source page.
- `related/Dryad-xksn02vw6/Dryad_landing_source.html`, `Dryad_README_provenance.json` and `dryad-file-metadata.json`: source page, representation provenance and original README file metadata.
- `related/Dryad-xksn02vw6/PROVENANCE.md` and `metadata-manifest.json`: retrieval limits and checksums. The converted README is not byte-identical to the uploaded Markdown file.
Use only these metadata/README snapshots and the supplied article materials. Do not download raw data, full archives or numerical omics matrices. Expected local IDs and gold-answer row counts are not input requirements.

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
