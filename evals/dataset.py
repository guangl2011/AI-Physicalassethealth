"""Dataset loading: the committed seed corpus and its adjudicated labels.

Everything the harness evaluates against ships in ``seed/`` (synthetic corpus,
fixed seed 42; human-adjudicated ground truth — see ``docs/testing-plan.md``).
The store is built in-process through the real ingestion routes so the harness
measures exactly what a deployment would run.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from insmart_api.app import create_app

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
CORPUS_PATH = SEED_DIR / "corpus.csv"
LABELS_PATH = SEED_DIR / "labels.json"

# The diagnostic moment: after the corpus's last completed_at (2025-10) and
# inside the 545-day staleness window, so rich assets rank on real evidence.
AS_OF = "2026-07-01T12:00:00"


def load_labels() -> dict[str, Any]:
    """The committed adjudicated labels."""
    labels: dict[str, Any] = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    return labels


def load_corpus_csv() -> str:
    """The committed seed corpus, exactly as shipped."""
    return CORPUS_PATH.read_text(encoding="utf-8")


def assets_by_id(labels: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Labels keyed by asset id — the ground-truth catalogue."""
    return {asset["asset_id"]: asset for asset in labels["assets"]}


def session_factory(client: TestClient) -> Callable[[], Any]:
    """The app's session factory (``TestClient.app`` is typed as a bare ASGI app)."""
    factory: Callable[[], Any] = cast(Any, client.app).state.session_factory
    return factory


def build_store(db_path: Path) -> TestClient:
    """A fresh store with only the asset inventory registered (no corpus yet)."""
    labels = load_labels()
    client = TestClient(create_app(f"sqlite:///{db_path}"))
    response = client.post(
        "/ingest/assets",
        json=[
            {
                "asset_id": asset["asset_id"],
                "site": asset["site"],
                "equipment_type": asset["equipment_type"],
                "installed_year": asset["installed_year"],
            }
            for asset in labels["assets"]
        ],
    )
    assert response.status_code == 200, response.text
    return client


def ingest_seed_corpus(client: TestClient) -> dict[str, Any]:
    """Upload the seed corpus through the real route; return the ingest report."""
    response = client.post(
        "/ingest/work-orders",
        files={"file": ("corpus.csv", load_corpus_csv().encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200, response.text
    report: dict[str, Any] = response.json()
    return report


def build_ingested_store(db_path: Path) -> TestClient:
    """A fresh store with the asset inventory and full seed corpus ingested.

    Uses the real HTTP routes (register assets, upload the CSV) so the
    harness evaluates the same pipeline a deployment runs.
    """
    client = build_store(db_path)
    ingest_seed_corpus(client)
    return client
