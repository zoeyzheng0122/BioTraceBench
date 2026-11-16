# Evaluation protocol

EFE evaluates experimental fidelity through a shared scientific correspondence between submitted and reference objects. Local identifiers and row order locate records. Identity follows the experimental entity or analysis context described by the task and supplied sources.

## New-output review

`score_output.py prepare` binds the submission, task, source manifest, fixed reference, field dictionary, and eligibility file. The field roles come from the shipped scoring policy, independently of historical model judgments. The resulting `packet.json` contains the full row/cell inventory, reviewer instructions, and response schema. `binding.json` records the packet identity.

The reviewer supplies exactly `records`, `cells`, and `reference_issues` in a JSON judgment file. Every inventory row appears exactly once in a one-to-one record disposition. Every inventory cell appears exactly once in the corresponding same-field judgment. Reasons identify the scientific facts and source evidence used. An unmatched submitted row is extra; an unmatched reference row is missing.

Keep the reference fixed during a review. Record suspected defects in `reference_issues` for separate adjudication. Resolve uncertain object identities or scientific fields before finalization. `finalize` verifies the packet, reference and eligibility hashes, rejects incomplete or unresolved judgments, then records the actual reviewer and judgment hash with the metrics.

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
