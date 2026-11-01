.PHONY: demo eval test check

# Demo runbook: ingest the seed corpus through the real HTTP routes, then
# show one ranked diagnosis with citations, one abstention, and one
# feedback round-trip. See docs/testing-plan.md §4.
demo:
	python -m evals.demo

# Evaluation harness: extraction P/R, diagnosis hit@3 vs. the frequency
# baseline, abstention correctness — against the adjudicated seed labels.
# Exits nonzero on any missed threshold. See docs/testing-plan.md §3.
eval:
	python -m evals.run_eval

test:
	python -m pytest -q

check:
	ruff check src tests evals
	mypy src evals
	python -m pytest -q
