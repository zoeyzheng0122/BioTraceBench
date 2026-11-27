# B046 — Experimental-design curation

Paper: Anti-Inflammatory and Metabolic Effects of Fresh Versus Freeze-Dried Platelet-Rich Plasma on Equine Osteoarthritis in an Ex Vivo Cartilage-Synovium Explant Co-Culture System: A Pilot Study
DOI: 10.3390/vetsci13070654

## Objective
The PRP-formulation comparison and cytokine-only reference in the selected tissue-extract metabolomics experiment. Retain the group-level representation specified below while aliquot/acquisition mappings remain unavailable.

## Included scope
- Target material: Tissue extracts actually submitted to untargeted metabolomics from the selected cartilage–synovium co-culture groups. Identify the actual assayed material from the metabolomics preparation method and preserve unresolved tissue composition/pooling.
- Assays: Untargeted LC-MS metabolomics
- Time: Only harvest intervals explicitly assigned to the selected metabolomics preparations.

## Requested experimental factors
- IL-1β concentration and applicable formulation-specific PRP concentration, with numerical Factor Value and separate Unit
- Only metabolomics-specific harvest intervals explicitly assigned to selected preparations; otherwise Time remains null

## Excluded scope
- Blank/untreated control and TA groups; pooled QC, analytical blanks and standards as target samples or assays
- Independent PRP characterization, qPCR, ELISA, functional markers, metabolite values and pathway results
- Importing 48-hour/96-hour endpoints from parallel assays or interpreting explant wells as independent horses
- Assigning preparations, acquisition counts, duplicate status or harvest times from filenames and suffixes without a supplied crosswalk

## Case-specific material, condition and mapping rules
Use the tissue-grinding/extraction protocol to describe the assayed material. Keep source cartilage/synovium donors separate from the horse supplying PRP as a reagent. A study-wide donor count does not establish physical pooling in each preparation. Preserve unassigned tissue-component and donor/well relationships in descriptions and external notes.

Keep PRP formulation in Sample Name / Sample Material and in the quantitative factor name where needed. Conditions contain supported numerical IL-1β and formulation-specific PRP concentrations, with separate units, attached to the source receiving co-culture. Do not add categorical PRP-type condition rows, invent numerical zero-dose controls, or expand routine preparation recipes. Use a metabolomics-specific collection interval only when explicitly mapped; otherwise leave Time null and document the gap outside the condition table. The parallel functional-assay endpoints do not establish a metabolomics harvest time.

The supplied Figshare inventories list files and ZIP entries, not biological assignments. Native abbreviations, numbering, repeated suffixes and POS/NEG prefixes alone cannot establish treatment membership, donor identity, independent replicates, technical repeats or collection times. Do not count the two ESI modes or repeated-suffix files as additional biological preparations. Pooled analytical QC is separate from target material and does not establish pooling of the target samples.

## Row granularity and relationships
Represent each selected treatment group as one group-level metabolomics material and use one labelled aggregate assay across the selected materials while explicit aliquot/acquisition mappings are unavailable. If a supplied experimental-design source identifies actual preparations and their complete associations, retain that supported granularity; counts and filenames alone are insufficient. Do not create donor-level samples from well counts or additional assays for unassigned time points. Mark dataset/study accessions as such; do not place them in Sample Accession.

## Experiment resources (use supplied archives)
- 10.6084/m9.figshare.27753327: https://doi.org/10.6084/m9.figshare.27753327

## Frozen supplementary annotations
- `related/Figshare-27753327/Figshare_project_file_inventory.csv` and `figshare-project.json`: project file metadata.
- `related/Figshare-27753327/Figshare_archive_entry_inventory.csv` and `figshare-zip-directory.json`: ZIP central-directory entries only.
- `related/Figshare-27753327/PROVENANCE.md` and `metadata-manifest.json`: retrieval method, mapping limits and checksums.
Use only these metadata/README snapshots and the supplied article materials. Do not download raw data, full archives or numerical omics matrices. Expected local IDs and gold-answer row counts are not input requirements.

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
