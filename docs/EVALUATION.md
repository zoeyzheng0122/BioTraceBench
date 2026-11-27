# Evaluate a database

Experimental Fidelity Evaluation aligns submitted and reference records by the experimental objects they describe. Field F1 measures recovery of scientific fields. Record F1 measures recovery of complete records, including required fields, links, and applicable reporting states.

## Score B008

Extract the reproduction archive as `BioTraceBench-artifact`. It includes the B008 inputs. The commands below use the database from the B008 agent workspace. Set `--database` to the path of your submission if you saved it elsewhere. [B008 case index](../data/B008/README.md) · [Download and extract](REPRODUCTION.md#replay-the-reported-results) · [Agent workspace](AGENT_INTEGRATION.md#prepare-b008)

**1. Prepare a review packet.**

The model submits `database.json` with the case's three or four schema-defined tables. Curators and reviewers record source locations and reporting states separately in the evaluation materials. The reviewer supplies `judgment.json` for scoring.

```sh
biotracebench-review prepare \
  --artifact-root BioTraceBench-artifact \
  --case B008 --database outputs/agent-runs/B008/database.json --out review-plan
```

Open `review-plan/packet.json`. Use its response schema to write `judgment.json`. Align the submissions with the scientific objects they describe, cite supporting evidence, and judge whole fields and relationships. Record applicable reporting states and resolve uncertainties that affect the score.

**2. Compute the scores.**

```sh
biotracebench-review finalize \
  --artifact-root BioTraceBench-artifact \
  --plan review-plan --judgment judgment.json --actor "Reviewer name" \
  --out scored-output
```

Open `scored-output/score.json` for both scores and their underlying counts. Use a new output directory for each run.

## Score format and paper notation

Final scores are under `metrics.field` and `metrics.record` in `score.json`.
Both objects use the same keys:

| Paper notation | JSON key | Meaning |
| --- | --- | --- |
| M | `tp` | Integer count of matched fields or complete records |
| P | `predicted` | Integer count of eligible predictions |
| G | `gold` | Integer count of eligible reference targets |
| Precision | `precision` | M / P |
| Recall | `recall` | M / G |
| F1 | `f1` | 2M / (P + G) |

JSON stores metrics on the 0–1 scale. The paper displays percentages; for
example, `0.8756` is `87.56%`. If G is zero, all three metrics are `null`.
If G is positive and P is zero, all three metrics are zero. Field and record
eligibility are assessed separately.

Within a study, counts are pooled across its tables before computing the six
metrics. Paper summaries average each study-level metric over eligible studies
within each domain, then give the basic and clinical domain means equal weight.
Undefined metrics are omitted from the corresponding average. Assigned-zero
outputs remain included when the reference targets are eligible. Overall F1 is
the average of study F1 values under these weights, not a new F1 calculated from
averaged precision and recall.

The installed command, `scripts/score_output.py`, and the paper replay all use
`biotracebench_analysis.replay.scoring.projected` for final counting.
`mark_all()` validates judgment coverage and returns diagnostics before
eligibility and reporting-state checks. Use `finalize` and its `metrics` object
when reporting results.

## Scoring rules

- Field F1 counts nonempty scientific fields. Record F1 requires all applicable fields, reporting states, and relationships to agree.
- Extra records and duplicate predictions count toward the prediction denominator. Study eligibility rules govern source conflicts, excluded targets, and optional answers.
- For continuous values, check equality first. A finer prediction can be rounded to precision supported by the reference source. Counts, denominators, identifiers, and values with unknown source precision require exact agreement.

See the [materials guide](MATERIALS.md#human-review-and-calibration) for the independent review and paired calibration. The [reproduction guide](REPRODUCTION.md) explains how to replay the paper from saved judgments.

## Review method

An LLM-based judge supplies record, field and link judgments against the fixed
reference and task rules. Disputed judgments are reviewed against the study sources. Independent review and calibration are described in the materials guide.
Offline replay uses the saved final judgments and applicability decisions.
For a new submission, `--actor` records the reviewer of the supplied `judgment.json`.

The installed workflow reads its rules from `review_configs/scoring/` in the
`biotracebench` package. Protocol identifiers are frozen format-version labels;
`publication` is their protocol namespace.

`biotracebench-review` and `biotracebench-score` provide the same `prepare` and
`finalize` commands. `--legacy-plan` is available for reproduction only.
