# Offline regression tests

Run `PYTHONPATH=src:tests python -B -m unittest discover -s tests -p 'test_*.py'` after installing the test extra. All scientific values and provider responses in this suite are synthetic. Source and extracted-package suites run sequentially to avoid shared worker-lock contention.

Publication tests cover whole-field counts, eligibility, fixed policy independence, identity-preserving changes, missing/duplicate judgments, numerical lexemes and complete native conversation recovery. The broader runtime suite exercises provider capabilities, budgets, immutable receipts, paired native histories and independent model-client distributions.
