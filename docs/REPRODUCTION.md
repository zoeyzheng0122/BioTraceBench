# Reproduction

The repository package and reproduction artifact are version **1.1.1**.
The public download keeps the stable filename `BioTraceBench-reproduction.tar.gz`;
inside it, `manifest.json` and `code/pyproject.toml` record the same version.

## Replay the reported results

Download the reproduction archive into the repository root and extract it. The archive contains the evaluation code, saved submissions, judgments, and inputs for the B008 example. [Reproduction archive](https://github.com/zoeyzheng0122/BioTraceBench/releases/download/benchmark/BioTraceBench-reproduction.tar.gz)

```sh
tar -xzf BioTraceBench-reproduction.tar.gz
```

Use Python 3.12 with NumPy 2.3.5 to run the paper replay. Choose a new output directory.

```sh
python -m pip install 'numpy==2.3.5'
python BioTraceBench-artifact/code/scripts/reproduce_paper.py \
  --artifact-root BioTraceBench-artifact --out paper-results --figures --verify
```

The replay covers all 1,200 model–study combinations using saved submissions, judgments, and zero-score statuses. It regenerates scores, tables, figures, SQL results, and the review analyses without model credentials. `paper-results/verification.json` records the checks.

The complete replay implementation is shipped in the Release archive under
`code/`, including `code/scripts/reproduce_paper.py`. The repository's installed
package provides the new-submission scoring interface. The final counting
implementation is shared with the archived replay; the archive also contains
the statistical analysis and figure-generation modules.

| Archive path | Contents |
| --- | --- |
| `outputs/<model>/<case>/database.json` | Saved databases |
| `evaluation/projection/judgments/` | Field and record judgments |
| `outputs/status.json` | Output statuses, including failures assigned zero |
| `evaluation/resource-summary.json` | Token usage and generation cost summaries |
| `evaluation/projection/analysis-parameters.json` | Frozen paper aggregation and bootstrap parameters |
| `reproduce/expected/` | Expected replay outputs used by `--verify` |
| `code/src/biotracebench_analysis/replay/comparison.py` | Output comparisons, including the numeric tolerance of `1e-12` |

The paper analysis uses 10,000 bootstrap samples with seed `20261110`, resampling
studies within each domain with the same draws across models. Basic and clinical
domain means receive weights of 0.5 each. Intervals use quantiles 0.025 and 0.975
with linear interpolation, as specified in the analysis-parameters file above.

## Run a new submission

Use the included B008 inputs for a first run. For the full set of 100 studies, extract the frozen inputs archive into `BioTraceBench-artifact`. The reproduction archive README gives the model configurations and commands used for generation. [Frozen inputs](TASK_MATERIALS.md) · [Agent integration](AGENT_INTEGRATION.md) · [Evaluation](EVALUATION.md)

See the materials guide for source terms and the review calibration. [Materials](MATERIALS.md)
