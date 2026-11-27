# Agent Integration

Use your own agent or model runner to produce a database for each study. Give the agent a workspace with the case prompt, target schema, and frozen source files. The evaluation files belong with the evaluator. [Study index](../data/README.md) · [Evaluation guide](EVALUATION.md)

## Prepare B008

From the repository root, extract the reproduction archive as `BioTraceBench-artifact`. It contains all 15 B008 inputs under `benchmark/materials/basic/B008/`. [B008 input manifest](../data/B008/inputs.json) · [Download and extract](REPRODUCTION.md#replay-the-reported-results)

Use a fresh directory for each run.

```sh
mkdir -p outputs/agent-runs
mkdir outputs/agent-runs/B008
cp data/B008/generation-prompt.md outputs/agent-runs/B008/
cp src/biotracebench/review_configs/schemas/basic-research.schema.json \
  outputs/agent-runs/B008/
cp -R BioTraceBench-artifact/benchmark/materials/basic/B008 \
  outputs/agent-runs/B008/inputs
```

Set `outputs/agent-runs/B008/` as the agent's working directory and scope its file access to that directory. Ask it to read `generation-prompt.md`, `basic-research.schema.json`, and `inputs/`, then save the final JSON object as `database.json` at the workspace root.

```text
outputs/agent-runs/B008/
  generation-prompt.md
  basic-research.schema.json
  inputs/
  database.json
```

For other cases, use the schema linked from the case page and preserve the relative paths of the files marked `"input_use": "model"` in `inputs.json`.

## Evaluate the submission

From the repository root, pass the saved database to the evaluator.

```sh
biotracebench-review prepare --artifact-root BioTraceBench-artifact \
  --case B008 --database outputs/agent-runs/B008/database.json --out review-plan
```

Complete the review using `review-plan/packet.json` and pass the resulting judgment to `biotracebench-review finalize`. The evaluator uses the review and the submitted database to compute Field F1 and Record F1. [Review and scoring commands](EVALUATION.md#score-b008)

## Compare runs

Use the same cases, supplied inputs, and scoring rules across agents. Record each run's model version, input handling, available tools, and budgets. Set provider credentials in your runner's environment. To repeat the paper's generation procedure, use the model profiles and generation commands in the extracted archive's README. The paper's saved outputs and judgments can be replayed offline. [Reproduction guide](REPRODUCTION.md)
