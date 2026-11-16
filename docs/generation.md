# Generating model outputs

The publication command prepares one database-construction phase. Source preparation and generation use `biotracebench`, `model_api` and `model_conversation`; they do not import scoring modules or read reference answers.

## Prepare and bind a run

```sh
python scripts/generate.py prepare \
  --dataset TASK_MATERIALS_DIR --case CASE_ID --out PREPARED_DIR

python scripts/generate.py draft \
  --prepared PREPARED_DIR --dataset TASK_MATERIALS_DIR \
  --template configs/models/biotracebench-run-template.json \
  --profile MODEL_PROFILE.json --out DRAFT.json

python scripts/generate.py freeze --draft DRAFT.json --out MANIFEST.json
```

Set the model endpoint, provider capabilities, exact model name, limits, tariff, cost ceiling and parameter basis in the profile/draft before freezing. The shipped template leaves financial inputs unset so the run can be bound to actual provider terms. Model credentials are referenced through environment-variable names. Document/PDF preparation uses the `generation` extra and may require a local office converter for specific source formats.

## Execute and recover

```sh
python scripts/generate.py run --manifest MANIFEST.json --out RUN_DIR --execute
python scripts/generate.py recover --manifest MANIFEST.json --out RUN_DIR
python scripts/generate.py export --run RUN_DIR --out EXPORT_DIR
```

`run --execute` can send paid requests under the frozen budget. Recovery replays saved receipts and native snapshots offline. Requests, raw responses, continuation events, token accounting, normalized submissions and content hashes remain in the run archive. Immutable identities reject changed runtime inputs or altered receipts.

The default template scopes execution to generation. Compatibility modules preserve earlier conversation protocols and paired-history tests so archived runs remain readable. The paper's default workflow uses the single construction phase.
