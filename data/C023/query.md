# C023 — Clinical trial curation

Paper: Pamidronate is ineffective for inflammatory-like low back pain associated with Modic type 1 changes: A double-blind, randomised controlled trial
DOI: 10.1016/j.ocarto.2026.100851

## Objective
The primary pamidronate efficacy comparison in inflammatory-like chronic low back pain.

## Included scope
- Population: Participants with inflammatory-like chronic low back pain and MRI-confirmed Modic type 1 changes in the primary efficacy comparison.
- Measures: VAS low-back-pain intensity; Roland–Morris disability score; Dallas pain/disability score as reported
- Time: Baseline to month 3.

## Requested statistics
- Baseline and D90 arm summaries, reported median changes and age/sex-adjusted contrasts for pain/Roland-Morris/Dallas. Keep table-row available denominators. Exclude unadjusted contrasts, other visits and unrelated mobility measures.

## Excluded scope
- 6-week/month-6 and pain-responder results
- Inflammatory characteristics, flexibility, analgesic consumption, other questionnaires and safety

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
