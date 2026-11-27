# B045 — Experimental-design curation

Paper: SLAMF7 defines subsets of human effector CD8 T cells
DOI: 10.1038/s41598-024-80971-5

## Objective
Extract the identifiable CMV-specific CD8 T-cell RNA preparations whose native library titles specify no CD27 or CD45RA fraction. Retain donor age background only when a supplied library-to-donor mapping establishes it; the selected scope does not require reconstruction of an unavailable age comparison.

## Included scope
- Target material: Total-RNA preparations from source-labelled CMV-specific CD8 T-cell materials in GSE282172, excluding explicitly CD27/CD45RA-fractionated libraries. Native RHP and antigen/preparation labels identify libraries, not proven donors.
- Assays: Bulk RNA sequencing
- Time: Baseline/ex vivo collection for selected transcriptomes; source-linked donor background only.

## Requested experimental factors
- Ex vivo collection state and CMV specificity as sample descriptions; donor age/background only when explicitly linked to the selected library
- No categorical collection-state or age-group condition rows; leave the condition table empty when no requested numerical experimental factor is supported

## Excluded scope
- Explicit CD27 or CD45RA fractions; EBV/Flu-specific preparations; naïve and TE controls; unrelated disease cohorts
- Flow-cytometric phosphorylation, TCR/IL-15 or receptor-stimulation branches, expression reanalysis and TCR-repertoire results
- Inferring donor identity, age group, pooling or biological replicate relationships from RHP order, numbered peptide labels or Mix

## Case-specific identity and conflict rules
Use the supplied GEO records and ENA annotations to match native library title, sample accession and experiment/run. Select CMV-labelled titles with no explicit CD27 or CD45RA fraction; preserve numbered and Mix preparation labels without translating them into donor identities or confirmed pools. This operational inclusion boundary does not prove a sorting phenotype absent from the source. Put actual assayed total RNA in Sample Material, and source cells/donor background in Biological Source.

Assign age or age group only through an explicit library-to-donor crosswalk; otherwise state that the linkage is unknown in Biological Source. Cohort totals and library order do not establish donor age.

Use structured sample/experiment instrument metadata in Platform. Retain the conflicting article/library-protocol instrument in Method and the source locations in external notes. Retain the conflicting read-length statements as unresolved; do not select a scalar read length or generate additional assays from the discrepancy. This precedence rule specifies extraction behavior, not the proven physical sequencer.

## Row granularity and relationships
Keep one source-distinguishable RNA preparation per selected native library; do not merge libraries into assumed donors. Keep one assay per identifiable acquisition/experiment and retain parent/run accessions together where supplied; an SRX and its SRR are not separate assays. Generic source cells and routine intermediates stay descriptive. Multiple sample IDs do not prove pooling.

## Experiment resources (use supplied archives)
- GSE282172: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE282172

## Frozen supplementary annotations
- `related/ENA-PRJNA1187529/ENA_source_annotations.csv` and `ena-run-annotations.json`: all returned project run annotations, including excluded materials.
- `related/ENA-PRJNA1187529/SAMN44795456.xml` and `SRX26753616.xml`: representative source-record spot checks.
- `related/ENA-PRJNA1187529/PROVENANCE.md` and `metadata-manifest.json`: provenance and checksums.
Use only these metadata/README snapshots and the supplied article materials. Do not download raw data, full archives or numerical omics matrices. Expected local IDs and gold-answer row counts are not input requirements.

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
