"""Shared fixtures: the committed seed corpus and API test clients."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from insmart_api.app import create_app

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
CORPUS_PATH = SEED_DIR / "corpus.csv"
LABELS_PATH = SEED_DIR / "labels.json"


@pytest.fixture(scope="session")
def corpus_csv() -> str:
    """The committed seed corpus, exactly as shipped."""
    return CORPUS_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def labels() -> dict[str, Any]:
    """The adjudicated label schema for the seed corpus."""
    return json.loads(LABELS_PATH.read_text(encoding="utf-8"))


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[TestClient]:
    """A client bound to a fresh SQLite database per test."""
    with TestClient(create_app(f"sqlite:///{tmp_path / 'test.db'}")) as test_client:
        yield test_client


@pytest.fixture()
def registered(client: TestClient, labels: dict[str, Any]) -> TestClient:
    """A client whose asset inventory matches the adjudicated labels."""
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


@pytest.fixture()
def ingested(registered: TestClient, corpus_csv: str) -> tuple[TestClient, dict[str, Any]]:
    """A client after one full corpus upload, plus the ingestion report."""
    response = registered.post(
        "/ingest/work-orders",
        files={"file": ("corpus.csv", corpus_csv.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200, response.text
    return registered, response.json()


@pytest.fixture()
def db_session(ingested: tuple[TestClient, dict[str, Any]]) -> Iterator[Any]:
    """A DB session over the ingested store, closed on teardown."""
    client, _ = ingested
    session = client.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()
