# C039 — Clinical trial curation

Paper: Vagus nerve-mediated neuroimmune modulation for rheumatoid arthritis: a pivotal randomized controlled trial
DOI: 10.1038/s41591-025-04114-7

## Objective
The blinded RESET-RA efficacy comparison.

## Included scope
- Population: The main randomized efficacy population of RESET-RA.
- Measures: ACR20 response referenced to consent baseline; DAS28-CRP EULAR good/moderate response; HAQ-DI minimum clinically important improvement
- Time: Month 3 before open-label stimulation, using each endpoint’s actual baseline and threshold.

## Requested statistics
- Blinded month-three primary ITT responder count/proportion and one treatment difference/CI/test for each criterion. Keep consent baseline and labeled multiplicity adjustment. Exclude duplicate registry/article representations, later open-label outcomes and alternative responder thresholds.

## Excluded scope
- ACR20 referenced to day-0 randomization, other thresholds and open-label follow-up
- All-completer, subgroup and safety analyses

## Case-specific application
- Use the requested consent-baseline blinded month-three responder endpoints; exclude day-zero-randomization ACR20. Recover the HAQ-DI MCID criterion and direction from the original source. Apply the shared rules for unreported inequality boundaries and use the supplementary instrument scoring rules.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
