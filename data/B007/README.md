# B007

Post-replicative chromatin accessibility predicts cell fate change

[Basic research](../../docs/BASIC_RESEARCH.md) · [Study DOI](https://doi.org/10.1016/j.stemcr.2026.102821) · [Target schema](../../src/biotracebench/publication_configs/schemas/basic-research.schema.json) · [Dataset guide](../../docs/DATASET.md)

## Task files

| File | Purpose |
| --- | --- |
| [Query](query.md) | Study instructions and scope |
| [Generation prompt](generation-prompt.md) | Full instructions and schema for the model |
| [Task definition](task.json) | Structured case information |
| [Input manifest](inputs.json) | File paths and source information for 16 inputs |
| [Source licenses](LICENSES.txt) | Terms for the study sources |
| [Reference database](../../reference/basic-research/B007.json) | Final reference for scoring |

The [frozen inputs archive](../../docs/TASK_MATERIALS.md) contains every source under `benchmark/materials/basic/B007/`.

See the [materials guide](../../docs/MATERIALS.md) for source access and redistribution.

## Saved outputs

Paths below are relative to the extracted [reproduction archive](../../docs/REPRODUCTION.md).

| Model configuration | Status | Archived output |
| --- | --- | --- |
| `claude-haiku-5-5` | Parseable database | `outputs/claude-haiku-5-5/B007/database.json` |
| `claude-opus-5-5` | Parseable database | `outputs/claude-opus-5-5/B007/database.json` |
| `claude-sonnet-5-5` | Parseable database | `outputs/claude-sonnet-5-5/B007/database.json` |
| `deepseek` | Parseable database | `outputs/deepseek/B007/database.json` |
| `gemini-3.1-pro-preview` | Parseable database | `outputs/gemini-3.1-pro-preview/B007/database.json` |
| `gemini-3.8-flash` | Parseable database | `outputs/gemini-3.8-flash/B007/database.json` |
| `glm` | Parseable database | `outputs/glm/B007/database.json` |
| `gpt-6-astra` | Parseable database | `outputs/gpt-6-astra/B007/database.json` |
| `gpt-6.1-sol` | Parseable database | `outputs/gpt-6.1-sol/B007/database.json` |
| `grok-4.7` | Parseable database | `outputs/grok-4.7/B007/database.json` |
| `kimi` | Parseable database | `outputs/kimi/B007/database.json` |
| `qwen` | Parseable database | `outputs/qwen/B007/database.json` |

[All cases](../README.md) · [Evaluation guide](../../docs/EVALUATION.md)
