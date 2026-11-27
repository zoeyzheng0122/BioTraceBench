# B041 — Experimental-design curation

Paper: The molecular signature of degeneration in explanted decellularized allogeneic heart valves
DOI: 10.3389/fcvm.2026.1865343

## Objective
Construct the three basic tables for the NanoString Human Fibrosis V2 comparison of explanted decellularized aortic homografts and native/reference aortic-valve tissues. Use the main article's Table 1 to determine explant eligibility and the supplied source annotations to identify preparations and profiles.

## Included scope
- Explants: include aortic-valve cases explicitly eligible for the fibrosis panel in main-text Table 1. Read the anatomy and Analysis columns together: F and F + I are eligible; I alone is not.
- References: retain individually identifiable aortic-reference preparations from the Figshare fibrosis Summary annotation, corroborated by the Fibrosis_raw_counts profile headers. Reference tissues need not appear as individual rows in Table 1, which lists the explanted homografts.
- Assays: NanoString nCounter Human Fibrosis V2 expression profiles only.
- Time: reported implantation-to-explantation intervals and the FFPE tissue preparations used for the selected comparison.

## Requested experimental factors and field placement
- Record the reported implantation-to-explantation interval as a numeric Factor Value in months. Exact conversion using 12 months per year is allowed; retain the source's compound interval in anchored Time text. Do not invent a zero interval for reference tissues.
- Describe homograft versus native/reference status, aortic anatomy and FFPE preservation in the appropriate Samples description fields. Keep original graft donor, recipient and reference-tissue donor roles distinct; do not infer the cellular origin of measured RNA from the explant recipient.
- Describe supported processing history in Sample Material or Method. A cohort-level statement that most explants underwent decalcification does not identify which preparations underwent it, or their duration. Do not assume an optional extra decalcification step for every sample or enumerate routine extraction recipes as additional condition rows.

## Source priority and conflict handling
Determine explant anatomy and fibrosis-panel eligibility from main-text Table 1; retain only securely matched eligible explants and separately labelled aortic-reference preparations. Link the fibrosis Summary and native fibrosis-profile headers by supported identifying attributes. For securely matched explants, Table 1 governs conflicting clinical attributes. A short Lab ID, worksheet title, copied normalized header or row position does not independently establish identity, eligibility or another acquisition. Preserve conflicting values and unresolved candidate associations in notes, use null for unsupported fields, and do not infer donor demographics, per-preparation decalcification, pooling, extra repeats or public sample accessions.

## Excluded scope
- Pulmonary valves, inflammation-only aortic cases and the separate human-inflammation panel.
- Additional Figshare candidates without a supported Table 1 aortic/fibrosis correspondence, even if a metadata field labels them AV.
- Immunostaining, gene-expression values, inferred causal treatment effects and unsupported donor/profile assignments.

## Row granularity and relationships
One sample per independently identifiable eligible tissue preparation. Keep individually labelled references separately; do not also add an aggregate reference-group sample. One condition per requested reported interval and receiving sample, with anchored text time. One assay per distinguishable selected fibrosis profile; preserve its supported sample association and do not duplicate raw/normalized representations or infer extra acquisitions. Use a labelled aggregate only where individual profiles genuinely cannot be identified. Multiple associated sample IDs do not establish physical pooling.

## Supplied source annotation
Use the frozen local files in `related/` alongside the paper and supplement:
- `Figshare-32051796-v3-fibrosis-sample-annotation.csv`: Summary columns I:O, with the published values preserved.
- `Figshare-32051796-v3-fibrosis-raw-profile-headers.csv`: native profile labels from the Fibrosis_raw_counts header.
- `Figshare-32051796-v3-fibrosis-av-normalized-headers.csv`: published grouping/header rows for checking conflicting normalized-sheet labels.
- `Figshare-32051796-v3-annotation-provenance.md`: source version, file identity and extraction details.

These are source annotations, not corrected answers. Do not retrieve raw acquisitions or numerical expression matrices for this task.

## Materials, missing values and response
Use the complete supplied paper, relevant supplements, figures and archived metadata. Read headers, captions and footnotes with values. Duplicate representations are one report. Use frozen local sources; inspect sample mappings, not numerical omics matrices or raw data. Do not digitize unlabelled plots or calculate absent results; the exact interval-unit conversion specified above is permitted. Preserve native labels, precision, units, zeros and NR/NE. Use null for unsupported optional values and explain material ambiguity/conflict in existing descriptions and notes. Unreadable evidence is unresolved. IDs/row order and synonymous wording do not change scientific identity.

## Experiment resources (use supplied archives)
- Figshare frozen source version: https://doi.org/10.6084/m9.figshare.32051796.v3
- Original source workbook: `Data figshare.xlsx`, Figshare file ID `66986135`; only sample annotations and profile headers are required.

## Shared table rules and output
Use [the shared basic table rules](../shared/basic-rules.md) and the fixed three-table schema. Apply the case-specific scope and rules above. Write descriptions in English and return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys.

Accession fields use Database:Identifier (level/type), for example PRIDE:PXD057572 (project). Use canonical database capitalization, one space before the parenthesis, and semicolon-space between multiple entries. Preserve actual levels, identifier versions and order; put longer descriptions outside the accession field.
