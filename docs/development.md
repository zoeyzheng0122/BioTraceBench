# Code structure and verification

| Package | Responsibility |
| --- | --- |
| `biotracebench` | Source preparation, generation, immutable run archive and recovery |
| `model_api` | Provider-neutral HTTP and capability handling |
| `model_conversation` | Native histories, lossless archives and submission extraction |
| `biotracebench_scoring` | Scientific inventory, judgments, policies and exhaustive coverage |
| `biotracebench_analysis.publication` | Paper-bound counting, statistics, controls and plotting |

Generation remains independent of scoring and references. Publication-specific scientific decisions enter through external data files. Generic compatibility modules retain their original protocol identifiers; the documented publication entry points select the fixed whole-field protocol.

## Offline checks

```sh
python -m pip install -e '.[test]'
PYTHONPATH=src:tests python -B -m unittest discover -s tests -p 'test_*.py'
python scripts/check_repository.py
python scripts/demo.py --out /tmp/biotracebench-demo-check
python scripts/build_source.py --out /tmp/biotracebench-package
```

Tests use synthetic values and mocked providers. They cover identity, merges, duplicates, numerical precision, units, nulls, eligibility, whole-field and complete-record counting, association paths, complete judgment coverage, native histories, immutable archives, recovery and budgets. Run source and extracted-package suites sequentially because account-worker tests share a lock location.

The source builder uses an explicit path allowlist and embeds SHA-256 checksums. The repository checker rejects undeclared files, study results, personal absolute paths, credentials, symlinks and mismatches between packaged and checkout scoring configurations. The small client-component builder is a separate compatibility test for provider isolation.

CI installs declared test dependencies and runs offline tests, help/import checks, the synthetic demo, source packaging and wheel packaging. It performs no provider requests. Full paper replay additionally requires the separate materials package and writes its numerical verification report outside Git.

Keep contributions scoped to the paper interfaces, document scientific rule changes, and add synthetic positive and negative regression cases. Preserve raw source evidence and historical scientific judgments in their external archives.
