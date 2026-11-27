# C013 — Clinical trial curation

Paper: Efficacy of antihypertensive treatment for target organ protection in patients with masked hypertension (ANTI-MASK): a multicentre, double-blind, placebo-controlled trial
DOI: 10.1016/j.eclinm.2024.102736

## Objective
The primary ANTI-MASK efficacy comparison.

## Included scope
- Population: The randomized ANTI-MASK ITT population with masked hypertension and baseline target organ damage.
- Measures: Composite target-organ-damage improvement; Brachial-ankle pulse wave velocity (continuous baPWV); Urinary albumin-to-creatinine ratio (continuous ACR)
- Time: Baseline to the primary 48-week/final follow-up assessment.

## Requested statistics
- Composite improvement counts/proportions and main comparison; main Table 3 baseline summaries, adjusted arm changes and treatment contrasts for baPWV/ACR. Exclude separate responder endpoints for composite components.

## Excluded scope
- Individual LVH outcomes, separate component responder categories and intermediate visits
- Blood pressure, per-protocol analyses, quality of life and safety

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
