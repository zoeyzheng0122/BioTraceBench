# Evaluation protocol

EFE evaluates experimental fidelity through a shared scientific correspondence between submitted and reference objects. Local identifiers and row order locate records. Identity follows the experimental entity or analysis context described by the task and supplied sources.

## New-output review

`score_output.py prepare` binds the submission, task, source manifest, fixed reference, field dictionary, and eligibility file. The field roles come from the shipped scoring policy, independently of historical model judgments. The resulting `packet.json` contains the full row/cell inventory, source-file identities, source information states, eligibility dispositions, complete submitted/reference JSON (including annotation context), reviewer instructions, and response schema. Blank reference values retain an unspecified state unless a source annotation explicitly provides another state; annotations preserve the frozen scoring targets. `binding.json` records the packet identity.

The reviewer supplies exactly `records`, `cells`, `reference_issues`, and `identity_evidence` in a JSON judgment file. Every inventory row appears exactly once in a one-to-one record disposition. Every inventory cell appears exactly once in the corresponding same-field judgment. Reasons identify the scientific facts and source evidence used. An unmatched submitted row is extra; an unmatched reference row is missing. Each row disposition also has a structured scientific basis and source/locator evidence. Matched rows cite supporting submitted and reference cells; local primary IDs and result values alone cannot establish identity. Task or declared source evidence supplements weak attributes and link pointers. Evidence locations are validated before counting; the scientific reviewer establishes their meaning.

Keep the reference fixed during a review. Record suspected defects in `reference_issues` for separate adjudication. Resolve uncertain identities, applicable fields and active identity dependencies before finalization. An excluded uncertainty is retained in the output and permits counting when it has no downstream scoring or identity effect. Exclusion from complete-record scoring can retain supported fields, whose judgments and identity evidence remain required. `finalize` verifies task, source, packet, reference, annotation and eligibility identities, checks structured identity evidence and complete coverage, then records the actual reviewer and judgment hash with the metrics. Historical three-section packets require the explicit `--legacy-plan` option; their replay is distinct from validation of a new review.

## Field and record counts

A whole scientific field is one scoring item. Necessary facts, correct attribution, numerical precision, units, time, direction, and scientific state must satisfy the task and fixed field policy. Equivalent wording can express the same fact. An erroneous assertion or required omission makes the submitted field incorrect. Identifiers and provenance support alignment without earning scientific-field credit.

The published contract evaluates each named physical field. Logical-field policies supported by compatibility modules are separate protocols; the publication entry points bind the paper's whole-field contract.

For each level, let M be correct matches, P submitted items, and G reference targets:

```text
precision = M / P
recall    = M / G
F1        = 2M / (P + G)
```

Duplicate and surplus records remain submitted items. A complete record requires all applicable scientific fields and necessary links to be correct under the same object mapping. External source-adjudication dispositions define field and complete-record eligibility independently. Zero-target cases retain undefined metrics where the contract requires them; assigned-zero positions retain their recorded status.

A bare null or blank value supplies no scientific content. Explicitly reported states such as NR or NE, zero, and false are meaningful content. Preserve numerical lexemes so precision decisions remain auditable. Unit equivalence and rounding follow `configs/scoring/policy.json` and the supplied scientific evidence.

## Judgment and counting responsibilities

A human or direct scientific reviewer establishes identity and semantic equivalence. The counting program validates coverage and calculates scores. The synthetic controlled-experiment comparator tests predefined transformations using literal scientific signatures; it is a diagnostic baseline rather than the reviewer for new scientific outputs.

The preparation interface accepts readable JSON databases, including the `database` wrapper. Preserve original text and use the separately reviewed partial-inventory process for malformed outputs; the interface reports malformed fragments instead of inventing a repair.

## Publication review evidence

Two reviewers independently checked sampled model outputs against study materials for field correctness and record completeness. Subsequent Codex source adjudications resolved source-dependent matches and values. Programs checked complete judgment coverage and counted the final metrics. Original reviews, source adjudications and the final published judgments remain distinct provenance layers in the external materials.

## Reviewed diagnostic annotations

```sh
python scripts/summarize_diagnostics.py --artifact-root MATERIALS_DIR --out OUTPUT_DIR
```

The external package supplies event-level subtype decisions, task capability labels, their operational codebook and input hashes. One primary subtype is assigned to each original binding event; output-level subtype counts overlap. Exact intersections recover the frozen answer union. Original decision notes preserve qualifications for missing context, unrecovered objects and reference-relative additions.

Capability groups are overlapping task requirements derived from task/source evidence. The report gives study counts and all six existing scores by model and domain, retaining assigned zeros and metric-specific undefined counts. Overall subgroup means give represented domains equal weight and studies equal weight within domain. Group comparisons are descriptive. Real annotations and model scores remain outside this repository.
