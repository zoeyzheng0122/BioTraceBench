# C010 — Clinical trial curation

Paper: MONETTE: A Randomized Phase II Study of Ceralasertib plus Durvalumab or Ceralasertib Monotherapy in Patients with Advanced Melanoma Resistant to PD-(L)1 Inhibition Ceralasertib ± Durvalumab in PD-(L)1–Resistant Melanoma
DOI: 10.1158/1078-0432.CCR-25-3951

## Objective
The primary MONETTE efficacy comparison.

## Included scope
- Population: The full analysis set of anti–PD-(L)1-resistant advanced melanoma patients in MONETTE.
- Measures: BICR-confirmed objective response rate per RECIST v1.1; BICR-assessed progression-free survival; Overall survival
- Time: The main full-analysis-set results at the article’s reported data cutoff.

## Requested statistics
- Full-analysis-set BICR ORR arm counts/proportions and adjusted OR; PFS/OS arm medians and primary HRs. Exclude safety-set/investigator responses, subgroups, event counts and landmark survival rates.

## Excluded scope
- Investigator-assessed response, best-response categories, duration/time to response
- Biomarker subsets, exploratory biomarkers and safety

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
