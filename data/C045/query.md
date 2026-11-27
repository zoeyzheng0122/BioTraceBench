# C045 — Clinical trial curation

Paper: Effects of lemborexant and zolpidem on sleep electroencephalography in older adults with insomnia: a randomized trial
DOI: 10.1093/sleepadvances/zpag017

## Objective
The selected NREM comparison of lemborexant 10 mg and extended-release zolpidem 6.25 mg.

## Included scope
- Population: The analyzable EEG subgroup of older adults with insomnia in this report, using source-supported PSG/EEG assessment denominators.
- Measures: NREM slow-oscillation spectral power; NREM alpha spectral power; NREM theta spectral power
- Time: Change from acute nights 1–2 to chronic nights 29–30.

## Requested statistics
- NREM acute-to-chronic paragraph: numerical within-arm t tests and associated df/P/d for SO/alpha/theta in the selected two arms. Include a direct between-arm acute-to-chronic estimate only if explicitly reported. Exclude duplicate qualitative descriptions, baseline-referenced electrode comparisons and plot digitization.

## Excluded scope
- Baseline-referenced contrasts, REM, other bands, LEM5/placebo and omnibus tests over excluded arms
- ISI correlations, subgroups and independent EEG reanalysis

## Case-specific application
- For the selected within-arm NREM acute-to-chronic t tests, use the dedicated one-sample-test paragraph over conflicting general statistical-method wording. Recover its adjustment method from that paragraph and preserve the reported P values.
- Retain the source-reported change definitions, transformation and temporal interpretation; do not construct an unprinted composite formula. Apply the shared endpoint-denominator rules.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
