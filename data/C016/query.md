# C016 — Clinical trial curation

Paper: The NPR1 agonist antibody XXB750 in heart failure: a phase 2 randomized trial
DOI: 10.1038/s41591-026-04313-w

## Objective
The XXB750 120-mg comparison with matching placebo within the ACEi/ARB background stratum.

## Included scope
- Population: Participants on background ACE inhibitor or ARB therapy in the XXB750 trial, preserving the actual biomarker and safety analysis populations for the specified arms.
- Measures: NT-proBNP; Plasma cGMP; Occurrence of worsening heart failure
- Time: Biomarkers at baseline/week 16; worsening-HF occurrence over the article-defined safety observation period, recorded separately.

## Requested statistics
- Table 3 selected background-therapy stratum: baseline/week-16 biomarker levels and week-16-to-baseline ratios; worsening-HF patient counts/proportions. Exclude other strata/doses, weeks 4/8, episodes, hospital-only events, death composite and protocol-planned populations.

## Excluded scope
- Other background strata, the 60-mg/pooled-dose groups and open-label sacubitril/valsartan
- Urinary biomarkers, other safety endpoints and interim biomarker visits

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
