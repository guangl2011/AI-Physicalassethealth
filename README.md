# Insmart AI — Physical Asset Health

Insmart AI estimates the health and failure risk of physical assets (starting
with commercial HVAC equipment) from sparse maintenance records, technician
notes, and limited building-automation data. It produces cited asset
timelines, ranked diagnostic triage, and evidence-backed inspection
recommendations, with calibrated uncertainty and explicit abstention when the
evidence is insufficient.

## Quickstart

Four commands, from the repo root — they ingest the synthetic seed corpus
and run the evaluation harness against its adjudicated labels (all data is
synthetic; see `docs/testing-plan.md`):

```bash
pip install -e '.[dev]'   # 1. install the backend + dev tools
make demo                 # 2. ingest the seed corpus, then show a ranked
                          #    diagnosis with citations, an abstention,
                          #    and a feedback round-trip
make eval                 # 3. extraction P/R, diagnosis hit@3 vs. the
                          #    frequency baseline, abstention correctness
pytest -q                 # 4. the full test suite (the same thresholds CI runs)
```

`make demo` and `make eval` are the demo runbook and evaluation harness
from `docs/testing-plan.md` (§4 and §3).

## Stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy, SQLite
- **Frontend:** React, Vite (TypeScript)
- **CI:** GitHub Actions — ruff + mypy + pytest (backend), lint + build (frontend)

## Development setup

> Placeholder — to be filled in as the project grows.

```bash
# Backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest

# Frontend
cd frontend
npm install
npm run dev
```
