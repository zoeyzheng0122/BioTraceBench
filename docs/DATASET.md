# Dataset

BioTraceBench contains 100 tasks from published studies. Each task asks for a JSON database that preserves the experimental design described by a fixed set of study materials.

| Domain | Studies | Schema | Browse |
| --- | ---: | --- | --- |
| Basic research | 50 | [Sample, condition, assay run](../src/biotracebench/review_configs/schemas/basic-research.schema.json) | [Basic studies](../data/README.md#basic-research) |
| Clinical research | 50 | [Population, measure, result, population relation](../src/biotracebench/review_configs/schemas/clinical-trials.schema.json) | [Clinical studies](../data/README.md#clinical-research) |

## Find the files for a study

Open the [study index](../data/README.md) and select a case, such as [B008](../data/B008/README.md) or [C008](../data/C008/README.md). Each case directory contains `query.md`, `generation-prompt.md`, `task.json`, `inputs.json`, and its source license notices. Each case page links to its final reference database and lists the saved model outputs available in the paper reproduction archive. [Reference databases](../reference/README.md) · [Reproduction guide](REPRODUCTION.md)

The frozen inputs archive contains all 2,028 study files. Each case page gives the path for its inputs. [Task materials guide](TASK_MATERIALS.md)

For a new submission, use the study instructions, listed source files, and target schema. The reference database and saved outputs support evaluation and paper replay. See the [evaluation guide](EVALUATION.md) to score a JSON database and the [materials guide](MATERIALS.md) for input downloads and human review.

See the [agent integration guide](AGENT_INTEGRATION.md) for a B008 workspace example and the files to supply to a model runner.
