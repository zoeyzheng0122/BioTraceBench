# Reproducing the paper

## Three operations

| Operation | Inputs | Output |
| --- | --- | --- |
| Replay published evaluation | Frozen materials and scientific judgments | Recomputed counts, analyses and verification report |
| Evaluate a new output | Task, reference, submitted database and completed review | New field/record metrics with provenance |
| Generate a new answer | Task materials, model profile, tariff and approved budget | Archived native conversation and submitted database |

## Offline replay

Install the analysis extra, verify the external package, then run:

```sh
python scripts/verify_materials.py --artifact-root MATERIALS_DIR
python scripts/reproduce_paper.py \
  --artifact-root MATERIALS_DIR --out OUTPUT_DIR --figures
```

Use an unused output directory outside the materials package. The replay disables outbound socket connections and runs analysis code shipped in this repository. It reads external evidence without executing Python files from the material package.

`verification.json` reports coverage, numerical checks, runtime and status. Successful reproduction checks all 1,200 positions, including 1,190 scored judgments and ten assigned zeros. It also replays 731 controlled databases, with 696 eligible comparisons and 35 exclusions, and the original 1,153-database structural cohort. Each analysis preserves its own frozen inclusion set.

Typical execution takes about one minute on a recent laptop with local storage; disk speed and processor affect elapsed time. Existing scientific judgments are replayed, while new judgments require the review procedure in [evaluation.md](evaluation.md).

## Figure and table mapping

| Paper item | External inputs | Shipped implementation | Recomputed output |
| --- | --- | --- | --- |
| Benchmark workload | Task/source manifests and reference inventories | `publication.workload` | `tables/workload.json` |
| Field/record quality | Scientific judgments, eligibility and analysis parameters | `publication.scoring`, `publication.statistics` | `projection/scores.csv`, `quality-analysis/` |
| Controlled evaluation | Control registry, databases and eligibility evidence | `publication.controlled`, `publication.comparator` | `controlled-results.csv`, `controlled-summary.csv` |
| Figure 3 | Quality scores and plotting inputs | `publication.statistics`, `publication.plot` | Quality summaries and statistical SVG |
| Figure 4 | Object mapping, field judgments and attribution eligibility | `publication.attribution` | `efe-actual/` and attribution SVG |
| Figure 5 | Frozen error classifications | `publication.replay.diagnostic_incidence` | `diagnostic-summary.csv` and error SVG |
| Figure 6 | Record labels, widths, reference links and judgments | `publication.record_analysis`, `publication.attribution` | Width/source/relation tables and SVG |
| Figure 7 | Request usage, tariff records and currency conversion | `publication.statistics`, `publication.replay.resources` | `resource-summary.json` and cost SVG |
| Human agreement | Independent returns and scientific identity mapping | `publication.human`, `publication.human_converter` | `human-agreement/` |
| Structural checks | Original databases, schema and field dictionary | `publication.structure` | `structure-recomputed.json` |

Figures 1 and 2 are conceptual diagrams. Supplementary figures provide the study/model heatmap and synthetic scoring illustration. The checked-in PNG/SVG files preserve the manuscript artwork byte for byte. `--figures` generates statistical SVGs from external plot data; a source checkout also copies the original manuscript layouts into `figures/manuscript-layout/` in the output directory.

## Statistical parameters

The quality bootstrap reads its seed, resampling count and weights from the external analysis-parameter file. The record-structure and relationship analyses preserve the publication implementation's 10,000 study resamples and seed 20261110, retaining within-study model observations. Source-composition comparisons match study, model, type and exact width before their specified averaging. Resource summaries retain the published accounting and currency-conversion inputs.

Replay validates all six quality metrics and saved confidence-interval endpoints to numerical tolerance 1e-12. Exact categorical evidence, eligibility, and assigned-zero decisions are retained. A discrepancy stops the run with a validation error and leaves outputs available for diagnosis.

## Review provenance

The original independent human assessments and subsequent Codex source adjudications are separate inputs in the material package. Agreement replay describes the original reviewers under their audit reference. Final scientific judgments apply the publication reference and eligibility decisions. The package records the reference reconciliation and preserves historical calibration results with their original scope.
