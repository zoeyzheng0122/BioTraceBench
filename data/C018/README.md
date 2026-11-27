# C018

Bimagrumab plus semaglutide alone or in combination for the treatment of obesity: a randomized phase 2 trial

[Clinical research](../../docs/CLINICAL_TRIALS.md) · [Study DOI](https://doi.org/10.1038/s41591-026-04204-0) · [Target schema](../../src/biotracebench/publication_configs/schemas/clinical-trials.schema.json) · [Dataset guide](../../docs/DATASET.md)

## Task files

| File | Purpose |
| --- | --- |
| [Query](query.md) | Study instructions and scope |
| [Generation prompt](generation-prompt.md) | Full instructions and schema for the model |
| [Task definition](task.json) | Structured case information |
| [Input manifest](inputs.json) | File paths and source information for 57 inputs |
| [Source licenses](LICENSES.txt) | Terms for the study sources |
| [Reference database](../../reference/clinical-trials/C018.json) | Final reference for scoring |

The [frozen inputs archive](../../docs/TASK_MATERIALS.md) contains every source under `benchmark/materials/clinical/C018/`.

The [inputs directory](inputs/) contains 1 source files from the archive.

See the [materials guide](../../docs/MATERIALS.md) for source access and redistribution.

## Saved outputs

Paths below are relative to the extracted [reproduction archive](../../docs/REPRODUCTION.md).

| Model configuration | Status | Archived output |
| --- | --- | --- |
| `claude-haiku-5-5` | Parseable database | `outputs/claude-haiku-5-5/C018/database.json` |
| `claude-opus-5-5` | Parseable database | `outputs/claude-opus-5-5/C018/database.json` |
| `claude-sonnet-5-5` | Parseable database | `outputs/claude-sonnet-5-5/C018/database.json` |
| `deepseek` | Parseable database | `outputs/deepseek/C018/database.json` |
| `gemini-3.1-pro-preview` | Parseable database | `outputs/gemini-3.1-pro-preview/C018/database.json` |
| `gemini-3.8-flash` | Parseable database | `outputs/gemini-3.8-flash/C018/database.json` |
| `glm` | Parseable database | `outputs/glm/C018/database.json` |
| `gpt-6-astra` | Parseable database | `outputs/gpt-6-astra/C018/database.json` |
| `gpt-6.1-sol` | Parseable database | `outputs/gpt-6.1-sol/C018/database.json` |
| `grok-4.7` | Parseable database | `outputs/grok-4.7/C018/database.json` |
| `kimi` | Parseable database | `outputs/kimi/C018/database.json` |
| `qwen` | Parseable database | `outputs/qwen/C018/database.json` |

[All cases](../README.md) · [Evaluation guide](../../docs/EVALUATION.md)
