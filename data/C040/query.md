# C040 — Clinical trial curation

Paper: Outcomes of tofacitinib dose reduction in patients with ulcerative colitis in stable remission: a long-term follow-up of the randomized RIVETING trial
DOI: 10.1093/crocol/otag093

## Objective
The RIVETING comparison of dose reduction to tofacitinib 5 mg twice daily and continuation of 10 mg twice daily.

## Included scope
- Population: The full analysis set under original randomized dose assignment in RIVETING, using the reported non-responder-imputation strategy.
- Measures: Modified Mayo score remission; Endoscopic improvement; Clinical response based on total Mayo score
- Time: Month 30 only, with the original source-defined reference for clinical response.

## Requested statistics
- Month-30 primary-imputed responder count/proportion and one CMH-weighted treatment difference/CI for each criterion. State dose direction; do not invent P values. Exclude dose-escalation response analyses and other visits.

## Excluded scope
- Total-Mayo remission as a separate variant, months 6/18, subgroups and alternative Dose Group analyses
- Dose-escalation remission recapture, biomarkers, time-to-event and safety

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
