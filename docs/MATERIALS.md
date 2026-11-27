# Materials and access

The reproduction archive contains the tasks, reference databases, saved submissions and judgments, and code for replaying the results. [Reproduction guide](REPRODUCTION.md)

## Human review and calibration

Two medical students independently reviewed 48 model outputs from 24 studies, with model identities and automated scores hidden. Among items both could judge, agreement was 99.94% for fields and 99.66% for complete records. On the same outputs, we compared pipeline scores with source-adjudicated scores. Across four ways of judging two fields about whether a proteomics protocol also applied to a second cell line, mean Field F1 differed by less than 0.03 percentage points. Record F1 and model rankings for both metrics were identical on this sample.

For reviewer counts and uncertain items, see `reproduce/inputs/review-validation/reviewer-agreement.csv` in the archive. The four calibration scenarios and model ranks are under `reproduce/expected/`.

## Study sources

The frozen inputs archive contains all 2,028 files listed in the case manifests. Source files retain their original terms. [Frozen inputs](TASK_MATERIALS.md)

