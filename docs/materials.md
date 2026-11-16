# External materials interface

Supply the publication materials directory through `--artifact-root`. The same code works when that directory is moved. Scientific sources, reference answers, outputs, judgments, reviewer returns, results, and run records remain in that separate package.

The reproduction interface reads these relative paths:

```text
02_Figures/02_Plot_Data/
03_Benchmark_Data/
  01_Task_Materials/
    tasks/ materials/ schemas/ metadata/
  02_Model_Outputs/
04_Reproducibility/
  02_Published_Evaluation/
    projection/references/
    projection/judgments/
    projection/scores.csv
    projection/analysis-parameters.json
    source-dispositions.json
    diagnostic-dispositions.csv
    controlled-dispositions.json
    source-record-labels.csv
    current-result-contract.json
  03_Experiments/inputs/
    baseline/
    status/
    package/
    currency-conversion.json
  04_Human_Review/01_Analysis/inputs/
    reviewer_A.json
    reviewer_B.json
    bundles.json
```

These names are the external package's existing interface. Native historical keys remain inside its records to preserve exact replay. The versioned contract in the package determines the scientific reference and inclusion sets.

New-output scoring reads the selected task, reference, source manifest and global source dispositions. Its field-role definitions and counting implementation are shipped here; previous model scores and judgments are unnecessary.

Paper reproduction also reads frozen output status, scientific judgments, source labels, transformation registry and original control databases, accounting records, and expected numerical tables. Expected tables verify newly computed values; scientific labels serve as explicit experimental inputs. Source documents and third-party data follow the provenance and redistribution records in the external package.

All commands write to a new output directory outside the material package. Set provider credentials in the execution environment or an approved secret store when generating new answers. Credentials never belong in configuration files or study packages.

## Integrity verification

```sh
python scripts/verify_materials.py --artifact-root MATERIALS_DIR
```

The command uses the same validation core as `04_Reproducibility/verify_bundle.py` in the delivered package. It verifies the checksum anchor, every mandatory manifest entry, task/model coverage, original-answer availability, database-to-inventory correspondence, source/reference identities, human-review sample coverage and current navigation. Missing files, wrong hashes and incomplete coverage cause a nonzero exit status. `--out REPORT.json` saves the validation result.

The active manuscript directory contains the main Word document. The supplementary Word document is retained in the historical archive and excluded from manuscript submission. The plain historical supplementary Word file is outside the active release inventory. Validation follows the versioned inventory: every explicitly listed file is mandatory, including listed historical evidence.
