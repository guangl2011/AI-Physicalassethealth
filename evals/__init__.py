"""Evaluation harness for Insmart AI against the adjudicated seed corpus.

D3 deliverable (spec art_N0ARICWR). The harness compares extractor and
ranker output against ``seed/labels.json`` — the human-adjudicated ground
truth over the synthetic seed corpus — and reports:

- extraction precision/recall (threshold 0.8 / 0.8),
- diagnosis hit@3 vs. the frequency-only baseline (must strictly beat it),
- abstention correctness (thin-history assets abstain; unresolved
  contradiction pairs yield contested).

The same evaluation is asserted in CI by ``tests/test_evals.py`` and runs
standalone via ``python -m evals.run_eval``.
"""
