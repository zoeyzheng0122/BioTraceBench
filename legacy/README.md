# Historical heuristic scorers

`heuristic-scoring/` preserves `evaluation.score`, `score_v2`, and their six dedicated
test modules from commit `0e2220d9f4345cfd17ab52075c6d2e4046cf703a`, byte for byte.
It is excluded from installed packages, source distributions and the main CI suite.
The files record the earlier algorithm and are not a standalone runnable package;
use that commit in a separate checkout to reproduce its historical tests.

The supported scoring interface is `biotracebench-review prepare` followed by
`biotracebench-review finalize`. It consumes an explicit scientific judgment and
uses `biotracebench_analysis.replay.scoring.projected` for final counts.
See the [evaluation guide](../docs/EVALUATION.md).

Shared identity, field-role and review utilities remain under `src/` where the
supported workflow needs them. Pre-eligibility diagnostics use the unchanged
historical arithmetic in `review_counts.py`; they are not final paper scores.
