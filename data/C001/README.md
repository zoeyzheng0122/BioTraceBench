# C001

Adjuvant icotinib for resected EGFR-mutated stage II–IIIA non-small-cell lung cancer (ICTAN, GASTO1002): a randomized comparison study

[Clinical research](../../docs/CLINICAL_TRIALS.md) · [Study DOI](https://doi.org/10.1038/s41392-025-02358-w) · [Target schema](../../src/biotracebench/publication_configs/schemas/clinical-trials.schema.json) · [Dataset guide](../../docs/DATASET.md)

## Task files

| File | Purpose |
| --- | --- |
| [Query](query.md) | Study instructions and scope |
| [Generation prompt](generation-prompt.md) | Full instructions and schema for the model |
| [Task definition](task.json) | Structured case information |
| [Input manifest](inputs.json) | File paths and source information for 48 inputs |
| [Source licenses](LICENSES.txt) | Terms for the study sources |
| [Reference database](../../reference/clinical-trials/C001.json) | Final reference for scoring |

The [frozen inputs archive](../../docs/TASK_MATERIALS.md) contains every source under `benchmark/materials/clinical/C001/`.

The [inputs directory](inputs/) contains 1 source files from the archive.

See the [materials guide](../../docs/MATERIALS.md) for source access and redistribution.

## Saved outputs

Paths below are relative to the extracted [reproduction archive](../../docs/REPRODUCTION.md).

| Model configuration | Status | Archived output |
| --- | --- | --- |
| `claude-haiku-5-5` | Parseable database | `outputs/claude-haiku-5-5/C001/database.json` |
| `claude-opus-5-5` | Parseable database | `outputs/claude-opus-5-5/C001/database.json` |
| `claude-sonnet-5-5` | Parseable database | `outputs/claude-sonnet-5-5/C001/database.json` |
| `deepseek` | Parseable database | `outputs/deepseek/C001/database.json` |
| `gemini-3.1-pro-preview` | Parseable database | `outputs/gemini-3.1-pro-preview/C001/database.json` |
| `gemini-3.8-flash` | Parseable database | `outputs/gemini-3.8-flash/C001/database.json` |
| `glm` | Parseable database | `outputs/glm/C001/database.json` |
| `gpt-6-astra` | Parseable database | `outputs/gpt-6-astra/C001/database.json` |
| `gpt-6.1-sol` | Parseable database | `outputs/gpt-6.1-sol/C001/database.json` |
| `grok-4.7` | Parseable database | `outputs/grok-4.7/C001/database.json` |
| `kimi` | Parseable database | `outputs/kimi/C001/database.json` |
| `qwen` | Parseable database | `outputs/qwen/C001/database.json` |

[All cases](../README.md) · [Evaluation guide](../../docs/EVALUATION.md)
