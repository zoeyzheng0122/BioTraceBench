# C004 — Clinical trial curation

Paper: BRUIN CLL-313: Randomized Phase III Trial of Pirtobrutinib Versus Bendamustine Plus Rituximab in Untreated Patients With Chronic Lymphocytic Leukemia/Small Lymphocytic Lymphoma
DOI: 10.1200/JCO-25-02380

## Objective
The primary BRUIN CLL-313 efficacy comparison.

## Included scope
- Population: Treatment-naïve CLL/SLL participants without del(17p) in the BRUIN CLL-313 ITT population.
- Measures: IRC-assessed progression-free survival; Overall survival; IRC-assessed overall response rate
- Time: The final PFS and corresponding interim OS analysis in this article; include only the explicitly requested 24-month PFS landmark.

## Requested statistics
- IRC PFS: arm medians, 24-month rates, rate difference and HR. OS: arm medians and primary HR. IRC ORR: arm responder count/proportion and independent CMH test. Exclude investigator/subgroup/sensitivity results.

## Excluded scope
- Investigator-assessed efficacy, individual best-response categories and other survival landmarks
- Crossover-only subsets, subgroup/sensitivity analyses and safety

## Case-specific application
- Retain the reported difference in 24-month PFS rates and its own CI. Apply the shared rules for recovering comparison direction from explicit source evidence.

## Shared table rules and output
Use [the shared clinical rules](../shared/clinical-rules.md) with the supplied scientific materials. Apply the case scope and source-selection rules above. Return JSON only with the four top-level arrays `population`, `measure`, `result` and `population_relation`.
