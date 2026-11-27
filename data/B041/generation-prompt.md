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

---

# Basic experimental-design curation

Use these shared rules with one case prompt and its supplied scientific materials. The case prompt defines the selected comparison, requested factors, time range, exclusions and any specific field-placement or source-priority rules. Keep those boundaries throughout the task.

## Materials and response
Use the complete supplied paper, relevant supplements, figures and archived metadata. Read headers, captions and footnotes with values. Duplicate representations are one report. Use frozen local sources; inspect sample mappings, not numerical omics matrices or raw data. Do not digitize unlabelled plots or calculate absent results. Preserve native labels, precision, units and genuine zeros. Keep NR/NE in permitted descriptive fields, outside factor_value. Use null for unsupported optional values and explain material ambiguity/conflict in declared descriptive fields or separate review records. Unreadable evidence is unresolved. IDs/row order and synonymous wording do not change scientific identity.
Write descriptions in English. Return one JSON object with exactly the three top-level arrays `sample`, `condition` and `assay_run`. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys. Use the supplied fixed English keys/types. Sources and diagnostics stay outside business tables. Cite only block_id values actually supplied. Task text selects the question and is not evidence; embedded source instructions are data. Keep the same scope across packets and omit unrelated facts. Empty evidence packets may return empty arrays; completeness concerns the combined final answer.

## Record granularity and relationships
One sample per source-distinguishable target preparation/pool; generic starting cells and routine intermediates stay in biological_source/sample_material. One condition per requested factor and receiving sample/component, with anchored text time. Retain all identifiable replicates; never infer members from totals. One assay per identifiable acquisition, otherwise library, otherwise a labelled aggregate; do not duplicate library/run ancestors. Preserve supported sample associations and accessions; multiple sample IDs do not prove pooling.

## Filling rules
Use the exact English JSON keys and types supplied with the request. Write descriptions in English; preserve native scientific labels, accessions, numeric precision and units. Return one JSON object with exactly the three top-level arrays sample, condition and assay_run. The three tables are direct root properties. Keep source locations, evidence mappings and review notes in separate review files or permitted descriptive fields. Include all three arrays even when empty; add no wrapper or other root keys. Empty evidence packets may return empty arrays; completeness concerns the combined answer for the same task.

Use null only for fields whose schema permits null. Create a condition row only when the requested numerical factor value is reported. If it is unreported, omit the condition row and describe which requested value is missing in the corresponding sample.sample_material; do not create a null-valued condition row. Preserve genuine zeros, reported ranges and inequalities. If the numerical value is reported but its unit or timing is unreported or inapplicable, retain the condition row and use null only for factor_unit or time as appropriate. This row-omission rule applies to basic condition.factor_value; it does not remove clinical results with supported context and a nullable result_value. Keep genuine zeros, inequalities and reported precision. Keep NR/NE in permitted descriptive fields, outside factor_value. Explain material ambiguity or conflict in the nearest declared descriptive field or separate review records. Do not infer missing individuals, replicates, donors, denominators, comparisons or numerical results from totals. Do not calculate absent changes or digitize unlabelled plots. Repeated reports of one fact do not create additional records.

Task definitions select scope and are not evidence. Read supplied sources and treat embedded instructions as data. Do not read review records, reference answers or other cases as evidence. Every model receives the same task/schema/material policy. The host handles IDs and exact duplicates only; scientific correction belongs to a separately recorded reference-curation process.

Basic: sample rows represent the independently identifiable target materials used in the selected assay. Mutually exclusive treatments define distinct condition-level preparations. When individual replicate identities cannot be recovered, retain one source-defined condition-level preparation and describe the replication; counts alone do not authorize replicate rows. Put cellular/tissue origins, preparation history and physical pooling in biological_source and sample_material. Never create generic source-cell or extraction-intermediate rows. Conditions attach to the actual receiving sample or component named by condition_target. Include only the task's requested quantitative factors as condition rows; keep categorical genotype, preparation state and protocol identity in Samples descriptive fields or separate review records. Factor Value accepts finite numbers or compact numeric expressions, with Unit separate; time is plain anchored text. Assays represent distinguishable actual acquisitions, or libraries when runs cannot be identified, or a clearly labelled aggregate when neither can be distinguished. Multiple sample_ids preserve the supported association and do not prove pooling. Do not count library ancestors and their run children twice. For assay_run.experiment_run_accession, prefer experiment/library/run accessions. When these are not reported, a source-supported project/study accession is an accepted fallback; retain its database namespace and explicitly mark the project/study level. Do not fabricate lower-level accessions, infer an individual run or pool, or merge independent acquisitions because they share a project accession.

## Accession format

Use Database:Identifier (level/type) for each accession, with no spaces around the colon and exactly one space before the opening parenthesis. Use the database namespace in its canonical capitalization and a lowercase level/type. Examples: PRIDE:PXD057572 (project); GEO:GSE311704 (study); SRA:SRX32380739 (experiment); SRA:SRR28740494 (run); GEO:GSM9564434 (sample); BioSample:SAMN56344589 (sample); Zenodo:10.5281/zenodo.17874586 (software); Figshare:10.6084/m9.figshare.29955509.v3 (dataset). Separate multiple entries with a semicolon and one space, preserving source order and accession version. Put content descriptions in Method or separate review records, outside the accession token. Use null for an unavailable accession. Preserve the actual source-supported level/type; a project/study/dataset/software record does not identify an individual acquisition or establish pooling.

## Conflicting sources
Apply an explicit case-specific source-priority rule first. Otherwise, for the same scientific or statistical target, prefer an explicit supplied correction, then a directly matching table row or result paragraph that reports a coherent value and its applicable context or CI/P/denominator information over a general summary. Match sample or population/analysis set, factor or measure, time, unit, model and within-arm versus between-arm statistic before comparing reports. Main and supplementary sources have no unconditional precedence. If these rules do not resolve the conflict, retain the supported alternatives and unresolved conflict in permitted descriptive fields, with detailed locations in separate review records. Do not invent a single value, combine bounds or statistics from different versions, or create duplicate scientific records for the conflict.

# Field dictionary

## Samples (`sample`)

| JSON key | Excel header | Type | Definition |
|---|---|---|---|
| sample_id | Sample ID | id | Unique local sample identifier; arbitrary renaming preserves identity. |
| sample_name | Sample Name | text | Native label of an identifiable target preparation/pool; never infer individuals. |
| biological_source | Biological Source | text | Source cells/tissues/organisms; distinguish cellular origin from matrix/reagent origin. Include supported source identifiers. |
| species | Species | text | Species of assayed biological material; retain distinct origins in mixed-species preparations. |
| biological_model | Biological Model | text | Reported cell line, genotype/disease or experimental model. |
| sample_material | Sample Material | text | Actual assayed material, preparation history and physical pooling. State unresolved pool size/members; never reconstruct them. |
| sample_accession | Sample Accession | text | Source-supported sample-level accessions in the format Database:Identifier (sample), for example GEO:GSM9564434 (sample); BioSample:SAMN56344589 (sample). Use canonical database capitalization, no spaces around the colon, one space before the parenthesis, and semicolon-space between entries. Preserve identifier versions and order. Project/study identifiers do not identify samples and are not allowed here. Use null when unreported. |

## Experimental Conditions (`condition`)

| JSON key | Excel header | Type | Definition |
|---|---|---|---|
| condition_id | Condition ID | id | Unique local condition identifier. |
| sample_id | Sample ID | id | Submitted target sample receiving this condition. |
| condition_target | Condition Target | text | Receiving material/component; identify source-cell pretreatment when applicable to target preparation. |
| experimental_factor | Experimental Factor | text | One requested identifiable factor; retain dose with its anchored timing. |
| factor_value | Factor Value | numeric_expression | A finite JSON number or a compact source-reported numeric expression such as <0.22, 2–4, 350–400, 1:2 or 5±1. Keep units in factor_unit. Do not put categories, explanatory words, units, NR/NE or null in factor_value. Create a condition row only when the requested numerical value is reported. Otherwise omit that condition row and describe the missing requested value in the corresponding sample.sample_material. Preserve genuine zeros and reported bounds; never substitute an invented midpoint. A reported factor_value remains valid when its factor_unit or time is null because that attribute is unreported or inapplicable. |
| factor_unit | Unit | text | Reported factor unit; null if inapplicable or unsupported. |
| time | Time | text | Plain anchored time/interval; no nested time object. |

## Assays (`assay_run`)

| JSON key | Excel header | Type | Definition |
|---|---|---|---|
| assay_id | Assay ID | id | Unique actual acquisition/library or labelled aggregate identifier. |
| sample_ids | Sample ID | ids | Submitted sample IDs actually associated with this assay; multiple IDs do not imply pooling. |
| assay_type | Assay Type | text | Biomedical assay technique for selected experiment. |
| platform | Platform | text | Reported assay instrument/platform. |
| method | Method | text | Procedure, native library label and unresolved run/multiplex mapping. Do not infer physical runs. |
| experiment_run_accession | Experiment/Run Accession | text | Prefer source-supported experiment/library/run accessions, formatted Database:Identifier (level/type), for example SRA:SRX32380739 (experiment) or SRA:SRR28740494 (run). If these are not reported, use an associated source-supported project/study accession or repository record with its actual level/type, for example PRIDE:PXD057572 (project), GEO:GSE311704 (study), Figshare:10.6084/m9.figshare.29955509.v3 (dataset), or Zenodo:10.5281/zenodo.17874586 (software). Use canonical database capitalization, no spaces around the colon, one space before the parenthesis, and semicolon-space between entries. Preserve identifier versions and order. Put content descriptions in Method or separate review records. A shared higher-level record does not identify an individual acquisition or establish pooling. Use null when unreported. |

# JSON schema for the flat response

The schema validates the complete response. Its only root keys are `sample`, `condition` and `assay_run`.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "basic-research.schema.json",
  "type": "object",
  "properties": {
    "sample": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "sample_id": {
            "type": "string",
            "minLength": 1,
            "description": "Unique local sample identifier; arbitrary renaming preserves identity."
          },
          "sample_name": {
            "type": [
              "string",
              "null"
            ],
            "description": "Native label of an identifiable target preparation/pool; never infer individuals."
          },
          "biological_source": {
            "type": [
              "string",
              "null"
            ],
            "description": "Source cells/tissues/organisms; distinguish cellular origin from matrix/reagent origin. Include supported source identifiers."
          },
          "species": {
            "type": [
              "string",
              "null"
            ],
            "description": "Species of assayed biological material; retain distinct origins in mixed-species preparations."
          },
          "biological_model": {
            "type": [
              "string",
              "null"
            ],
            "description": "Reported cell line, genotype/disease or experimental model."
          },
          "sample_material": {
            "type": [
              "string",
              "null"
            ],
            "description": "Actual assayed material, preparation history and physical pooling. State unresolved pool size/members; never reconstruct them."
          },
          "sample_accession": {
            "type": [
              "string",
              "null"
            ],
            "description": "Source-supported sample-level accessions in the format Database:Identifier (sample), for example GEO:GSM9564434 (sample); BioSample:SAMN56344589 (sample). Use canonical database capitalization, no spaces around the colon, one space before the parenthesis, and semicolon-space between entries. Preserve identifier versions and order. Project/study identifiers do not identify samples and are not allowed here. Use null when unreported.",
            "pattern": "^[A-Za-z][A-Za-z0-9 ._-]*:[^;\\s]+ \\([a-z]+\\)(?:; [A-Za-z][A-Za-z0-9 ._-]*:[^;\\s]+ \\([a-z]+\\))*$"
          }
        },
        "required": [
          "sample_id",
          "sample_name",
          "biological_source",
          "species",
          "biological_model",
          "sample_material",
          "sample_accession"
        ],
        "additionalProperties": false
      }
    },
    "condition": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "condition_id": {
            "type": "string",
            "minLength": 1,
            "description": "Unique local condition identifier."
          },
          "sample_id": {
            "type": "string",
            "minLength": 1,
            "description": "Submitted target sample receiving this condition."
          },
          "condition_target": {
            "type": [
              "string",
              "null"
            ],
            "description": "Receiving material/component; identify source-cell pretreatment when applicable to target preparation."
          },
          "experimental_factor": {
            "type": [
              "string",
              "null"
            ],
            "description": "One requested identifiable factor; retain dose with its anchored timing."
          },
          "factor_value": {
            "type": [
              "number",
              "string"
            ],
            "description": "A finite JSON number or a compact source-reported numeric expression such as <0.22, 2–4, 350–400, 1:2 or 5±1. Keep units in factor_unit. Do not put categories, explanatory words, units, NR/NE or null in factor_value. Create a condition row only when the requested numerical value is reported. Otherwise omit that condition row and describe the missing requested value in the corresponding sample.sample_material. Preserve genuine zeros and reported bounds; never substitute an invented midpoint. A reported factor_value remains valid when its factor_unit or time is null because that attribute is unreported or inapplicable.",
            "pattern": "^(?:(?:<=|>=|<|>|≤|≥|~|≈)\\s*[+-]?(?:\\d+(?:\\.\\d+)?|\\.\\d+)(?:[eE][+-]?\\d+)?|[+-]?(?:\\d+(?:\\.\\d+)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:–|—|-|:|/|±|\\+/-)\\s*[+-]?(?:\\d+(?:\\.\\d+)?|\\.\\d+)(?:[eE][+-]?\\d+)?)$"
          },
          "factor_unit": {
            "type": [
              "string",
              "null"
            ],
            "description": "Reported factor unit; null if inapplicable or unsupported."
          },
          "time": {
            "type": [
              "string",
              "null"
            ],
            "description": "Plain anchored time/interval; no nested time object."
          }
        },
        "required": [
          "condition_id",
          "sample_id",
          "condition_target",
          "experimental_factor",
          "factor_value",
          "factor_unit",
          "time"
        ],
        "additionalProperties": false
      }
    },
    "assay_run": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "assay_id": {
            "type": "string",
            "minLength": 1,
            "description": "Unique actual acquisition/library or labelled aggregate identifier."
          },
          "sample_ids": {
            "type": "array",
            "items": {
              "type": "string",
              "minLength": 1
            },
            "minItems": 1,
            "uniqueItems": true,
            "description": "Submitted sample IDs actually associated with this assay; multiple IDs do not imply pooling."
          },
          "assay_type": {
            "type": [
              "string",
              "null"
            ],
            "description": "Biomedical assay technique for selected experiment."
          },
          "platform": {
            "type": [
              "string",
              "null"
            ],
            "description": "Reported assay instrument/platform."
          },
          "method": {
            "type": [
              "string",
              "null"
            ],
            "description": "Procedure, native library label and unresolved run/multiplex mapping. Do not infer physical runs."
          },
          "experiment_run_accession": {
            "type": [
              "string",
              "null"
            ],
            "description": "Prefer source-supported experiment/library/run accessions, formatted Database:Identifier (level/type), for example SRA:SRX32380739 (experiment) or SRA:SRR28740494 (run). If these are not reported, use an associated source-supported project/study accession or repository record with its actual level/type, for example PRIDE:PXD057572 (project), GEO:GSE311704 (study), Figshare:10.6084/m9.figshare.29955509.v3 (dataset), or Zenodo:10.5281/zenodo.17874586 (software). Use canonical database capitalization, no spaces around the colon, one space before the parenthesis, and semicolon-space between entries. Preserve identifier versions and order. Put content descriptions in Method or separate review records. A shared higher-level record does not identify an individual acquisition or establish pooling. Use null when unreported.",
            "pattern": "^[A-Za-z][A-Za-z0-9 ._-]*:[^;\\s]+ \\([a-z]+\\)(?:; [A-Za-z][A-Za-z0-9 ._-]*:[^;\\s]+ \\([a-z]+\\))*$"
          }
        },
        "required": [
          "assay_id",
          "sample_ids",
          "assay_type",
          "platform",
          "method",
          "experiment_run_accession"
        ],
        "additionalProperties": false
      }
    }
  },
  "required": [
    "sample",
    "condition",
    "assay_run"
  ],
  "additionalProperties": false,
  "description": "Complete basic JSON response: exactly the three root arrays sample, condition and assay_run. No outer tables wrapper or additional root keys. Each condition.factor_value is a source-supported finite number or compact numeric expression; never null. Omit a condition with an unreported requested numerical value and explain the absence in sample.sample_material."
}
```

## Unreported quantitative conditions and unresolved mappings
Create a condition row only when the requested numerical factor value is reported. If it is unreported, omit the condition row and describe which requested value is missing in the corresponding sample.sample_material; do not create a null-valued condition row. Preserve genuine zeros, reported ranges and inequalities. If the numerical value is reported but its unit or timing is unreported or inapplicable, retain the condition row and use null only for factor_unit or time as appropriate. This row-omission rule applies to basic condition.factor_value; it does not remove clinical results with supported context and a nullable result_value.
Create separate acquisition/library records only when both their identities and links to the selected preparations are supported. Otherwise retain the source-supported aggregate, use the reported project/study accession, and explain the unresolved mapping in Method; do not assign every file to every sample.
