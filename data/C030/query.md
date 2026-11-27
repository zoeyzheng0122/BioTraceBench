# C030 — Clinical trial curation

Paper: Physiotherapy with integrated virtual reality for patients with severe chronic low back pain: cluster-randomized controlled trial (VARIETY)
DOI: 10.1186/s12891-026-09873-z

## Objective
The contemporaneous randomized VARIETY comparison involving home VR.

## Included scope
- Population: Patients in the contemporaneous VARIETY cluster-randomized trial arms; retain practice-level clustering separately from participant counts.
- Measures: Oswestry Disability Index; Numeric Pain Rating Scale; Pain Catastrophizing Scale
- Time: Baseline to month 3.

## Requested statistics
- Table 6 observed T0/T3 arm means/SD and T3 observed n; main Table 3 contrasts explicitly labelled three months; directly reported within-arm ODI improvement in Results. Preserve Table 3/Table 6 discrepancies in separate review records. Exclude external/pooled controls, overall-trajectory contrasts and other visits.

## Excluded scope
- Historical/augmented total controls and month-1 analyses
- Other questionnaires and feasibility results

## Case-specific application
- Use Table 6 for requested observed T0/T3 summaries and Table 3 rows explicitly labelled three months for adjusted contrasts. Observed and adjusted results are distinct statistical targets. Do not substitute T1 data for T3 to reconcile table differences.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
