# Insmart AI — Physical Asset Health

Insmart AI estimates the health and failure risk of physical assets (starting
with commercial HVAC equipment) from sparse maintenance records, technician
notes, and limited building-automation data. It produces cited asset
timelines, ranked diagnostic triage, and evidence-backed inspection
recommendations, with calibrated uncertainty and explicit abstention when the
evidence is insufficient.

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
