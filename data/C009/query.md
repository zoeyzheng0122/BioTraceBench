# C009 — Clinical trial curation

Paper: Datopotamab–deruxtecan in early-stage breast cancer: the sequential multiple assignment randomized I-SPY2.2 phase 2 trial
DOI: 10.1038/s41591-024-03266-2

## Objective
The subtype-specific Dato-DXd I-SPY2.2 strategy analysis across Blocks A–C and its reported dynamic-control comparison.

## Included scope
- Population: The HR-negative/HER2-negative/Immune-negative/DRD-negative subtype in the Dato-DXd I-SPY2.2 arm.
- Measures: Pathological complete response across the treatment strategy; Residual Cancer Burden (RCB) class distribution at surgery
- Time: Surgery after the complete treatment strategy or protocol-directed early surgery, in the primary strategy analysis.

## Requested statistics
- For the specified RPS subtype and complete treatment strategy: modeled pCR and observed pCR count/proportion; dynamic-control modeled pCR; P(>DC); and observed RCB class counts/proportions in the RCB-evaluable subset. Exclude pCR timing by treatment block, combined pCR/RCB-I summaries, alternate candidate historical regimens and sensitivity strategies.

## Excluded scope
- Block-A-only efficacy and every other subtype
- preRCB-adherent sensitivities, toxicity, and the separate Dato-DXd plus durvalumab arm

## Case-specific application
- Use Supplementary Figure 2 for the requested labelled RCB class counts. Apply the shared rules for distinct statistical targets and unlabelled values.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
