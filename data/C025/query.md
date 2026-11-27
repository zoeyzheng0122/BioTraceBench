# C025 — Clinical trial curation

Paper: Effect of temporomandibular joint exercises on mechanical low back pain: a preliminary randomized controlled study
DOI: 10.1186/s12891-026-09657-5

## Objective
The randomized temporomandibular-exercise study in mechanical low back pain.

## Included scope
- Population: Participants with mechanical low back pain in the two randomized physiotherapy groups, using the reported pain-analysis population.
- Measures: Pain at rest; Pain during activity; Oswestry disability score (ODQ/ODI as labeled in the source)
- Time: Baseline to the end of 2 weeks.

## Requested statistics
- Literal Table 2 Group A/B baseline/post means, published changes and tests for resting pain, activity pain and disability. Use Methods treatment mapping; preserve contradictory narrative labels and unusual source values in separate review records without swapping groups or recalculating changes.

## Excluded scope
- Lumbar range-of-motion and other outcomes
- Any numerical/group-label correction inferred from inconsistencies

## Case-specific application
- Recover Group A/B treatment identities from the Methods, giving that source precedence over contradictory narrative labels. Preserve Table 2 values and their stated group labels; apply the shared rules for unreported calculation direction and unusual reported values.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
