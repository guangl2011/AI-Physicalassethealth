"""API tests: ingestion accounting, review reasons, and provenance reads."""

from __future__ import annotations

import csv
import io
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from insmart_api.ingestion.parsing import COLUMNS
from insmart_api.models import IngestRun, Observation, ReviewItem


def _corpus_ids(corpus_csv: str) -> set[str]:
    rows = list(csv.reader(io.StringIO(corpus_csv)))
    return {row[0] for row in rows[1:]}


def _db(client: TestClient) -> Session:
    session: Session = client.app.state.session_factory()
    return session


# --- registration --------------------------------------------------------------


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_registration_rejects_non_canonical_ids(client: TestClient) -> None:
    response = client.post(
        "/ingest/assets",
        json=[
            {
                "asset_id": "boiler 1",
                "site": "Harborview",
                "equipment_type": "Boiler",
            }
        ],
    )
    assert response.status_code == 422
    assert "expected the form" in response.json()["detail"]


def test_duplicate_registration_is_a_409(client: TestClient, labels: dict[str, Any]) -> None:
    asset = labels["assets"][0]
    entry = {
        "asset_id": asset["asset_id"],
        "site": asset["site"],
        "equipment_type": asset["equipment_type"],
        "installed_year": asset["installed_year"],
    }
    assert client.post("/ingest/assets", json=[entry]).status_code == 200
    again = client.post("/ingest/assets", json=[entry])
    assert again.status_code == 409
    assert "already registered" in again.json()["detail"]


def test_upload_before_registration_is_rejected(client: TestClient, corpus_csv: str) -> None:
    response = client.post(
        "/ingest/work-orders",
        files={"file": ("corpus.csv", corpus_csv.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 422
    assert "no assets registered" in response.json()["detail"]


# --- accounting: zero silent drops ---------------------------------------------


def test_report_accounts_for_every_row(ingested: tuple[TestClient, dict[str, Any]]) -> None:
    _, report = ingested
    assert report["rows_total"] == 150
    assert (
        report["rows_ingested"] + report["rows_deduplicated"] + report["rows_reviewed"]
        == report["rows_total"]
    )
    assert report["rows_reviewed"] == len(report["review"])


def test_every_corpus_id_lands_somewhere(
    ingested: tuple[TestClient, dict[str, Any]], corpus_csv: str
) -> None:
    client, _ = ingested
    session = _db(client)
    try:
        observation_ids = set(session.scalars(select(Observation.id)).all())
        review_items = session.scalars(select(ReviewItem)).all()
    finally:
        session.close()
    review_ids = {item.external_id for item in review_items}
    dropped = _corpus_ids(corpus_csv) - observation_ids - review_ids
    assert not dropped, f"silently dropped work orders: {sorted(dropped)}"


def test_persisted_run_counts_match_the_report(
    ingested: tuple[TestClient, dict[str, Any]],
) -> None:
    client, report = ingested
    session = _db(client)
    try:
        run = session.get(IngestRun, report["run_id"])
        assert run is not None
        assert run.source_name == "corpus.csv"
        assert run.rows_total == report["rows_total"]
        assert run.rows_ingested == report["rows_ingested"]
        assert run.rows_deduplicated == report["rows_deduplicated"]
        assert run.rows_reviewed == report["rows_reviewed"]
        observation_count = len(session.scalars(select(Observation.id)).all())
        assert observation_count == report["rows_ingested"]
    finally:
        session.close()


# --- review list ----------------------------------------------------------------


def test_review_items_carry_reasons(ingested: tuple[TestClient, dict[str, Any]]) -> None:
    client, report = ingested
    response = client.get("/review")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == report["rows_reviewed"]
    for item in payload["items"]:
        assert item["reason"], "review item without a reason"
        assert item["raw_row"], "review item without the raw row"
        assert item["source_name"] == "corpus.csv"
        assert item["run_id"] == report["run_id"]


def test_known_malformed_rows_land_in_review_with_reasons(
    ingested: tuple[TestClient, dict[str, Any]],
) -> None:
    _, report = ingested
    reasons = {item["external_id"]: item["reason"] for item in report["review"]}
    assert set(reasons) >= {
        "WO-0011",  # ragged row (10 columns)
        "WO-0021",  # missing created_at
        "WO-BAD-0001",  # month 13
        "WO-BAD-0002",  # not a date
        "WO-BAD-0003",  # impossible calendar day
        "WO-0017",  # ambiguous tag
        "WO-0020",  # ambiguous tag
        "WO-0042",  # conflicting duplicate
        "WO-GHOST-0001",  # unresolvable asset ref
        "WO-GHOST-0002",  # unparseable tag
    }
    assert "columns" in reasons["WO-0011"]
    assert "created_at" in reasons["WO-0021"]
    for bad_date_id in ("WO-BAD-0001", "WO-BAD-0002", "WO-BAD-0003"):
        assert "ISO-8601" in reasons[bad_date_id]
    for ambiguous_id in ("WO-0017", "WO-0020"):
        assert "ambiguous" in reasons[ambiguous_id]
        assert "AHU-3" in reasons[ambiguous_id]
        assert "RTU-3" in reasons[ambiguous_id]
    assert "conflicting duplicate" in reasons["WO-0042"]
    assert "notes" in reasons["WO-0042"]
    assert "matches no asset" in reasons["WO-GHOST-0001"]
    assert "does not match" in reasons["WO-GHOST-0002"]


def test_ambiguous_rows_are_never_guessed(
    ingested: tuple[TestClient, dict[str, Any]],
) -> None:
    client, _ = ingested
    session = _db(client)
    try:
        assert session.get(Observation, "WO-0017") is None
        assert session.get(Observation, "WO-0020") is None
        assert session.get(Observation, "WO-0083") is None
        assert session.get(Observation, "WO-0086") is None
    finally:
        session.close()


# --- dedup over the API ---------------------------------------------------------


def test_reupload_is_idempotent(
    registered: TestClient, corpus_csv: str, labels: dict[str, Any]
) -> None:
    first = registered.post(
        "/ingest/work-orders",
        files={"file": ("corpus.csv", corpus_csv.encode("utf-8"), "text/csv")},
    )
    assert first.status_code == 200
    second = registered.post(
        "/ingest/work-orders",
        files={"file": ("corpus-copy.csv", corpus_csv.encode("utf-8"), "text/csv")},
    )
    assert second.status_code == 200
    report = second.json()
    assert report["rows_ingested"] == 0
    assert report["rows_deduplicated"] == 138
    assert report["rows_reviewed"] == 12

    expected = {
        str(asset["asset_id"]): int(asset["work_order_count"])
        for asset in labels["assets"]
    }
    counts = {
        asset["asset_id"]: asset["observation_count"]
        for asset in registered.get("/assets").json()
    }
    assert counts == expected


def test_same_id_with_differing_notes_is_a_conflict(registered: TestClient) -> None:
    def csv_row(work_order_id: str, notes: str) -> str:
        fields = {
            "work_order_id": work_order_id,
            "created_at": "2025-02-01T08:00:00",
            "completed_at": "",
            "site": "Harborview",
            "asset_tag": "AHU-1",
            "summary": "No cooling",
            "technician": "J. Rivera",
            "notes": notes,
            "resolution": "Replaced capacitor",
            "labor_hours": "2.5",
            "priority": "P2",
        }
        return ",".join(fields[column] for column in COLUMNS)

    header = ",".join(COLUMNS)
    body = (
        f"{header}\n{csv_row('WO-9001', 'Original notes.')}"
        f"\n{csv_row('WO-9001', 'Different notes.')}\n"
    )
    response = registered.post(
        "/ingest/work-orders",
        files={"file": ("dupe.csv", body.encode(), "text/csv")},
    )
    assert response.status_code == 200
    report = response.json()
    assert report["rows_ingested"] == 1
    assert report["rows_deduplicated"] == 0
    assert report["rows_reviewed"] == 1
    assert "notes" in report["review"][0]["reason"]


# --- timelines -------------------------------------------------------------------


def test_timeline_entries_cite_their_source_records(
    ingested: tuple[TestClient, dict[str, Any]],
) -> None:
    client, _ = ingested
    response = client.get("/assets/RTU-2/timeline")
    assert response.status_code == 200
    timeline = response.json()
    assert timeline["asset_id"] == "RTU-2"
    assert timeline["equipment_type"]
    entries = timeline["entries"]
    assert entries
    stamps = [entry["recorded_at"] for entry in entries]
    assert stamps == sorted(stamps)
    for entry in entries:
        assert entry["kind"] == "observed"
        assert entry["source_ref"].startswith("work-order:")
        assert entry["source_file"] == "corpus.csv"
        assert entry["source_row"] > 0
        assert entry["payload"]["work_order_id"] == entry["observation_id"]
        assert entry["text"]


def test_timeline_unknown_asset_is_a_404(client: TestClient) -> None:
    assert client.get("/assets/NOPE-1/timeline").status_code == 404


def test_asset_list_reports_observation_counts(
    registered: TestClient, labels: dict[str, Any]
) -> None:
    empty = registered.get("/assets").json()
    assert len(empty) == 20
    assert all(asset["observation_count"] == 0 for asset in empty)


# --- upload validation -----------------------------------------------------------


def test_upload_rejects_a_bad_header(registered: TestClient) -> None:
    body = "work_order_id,created_at\nWO-1,2025-01-01T00:00:00"
    response = registered.post(
        "/ingest/work-orders", files={"file": ("bad.csv", body.encode(), "text/csv")}
    )
    assert response.status_code == 422
    assert "missing required columns" in response.json()["detail"]


def test_upload_rejects_an_empty_file(registered: TestClient) -> None:
    response = registered.post(
        "/ingest/work-orders", files={"file": ("empty.csv", b"", "text/csv")}
    )
    assert response.status_code == 422
    assert "empty" in response.json()["detail"]


def test_upload_rejects_non_utf8_bytes(registered: TestClient) -> None:
    response = registered.post(
        "/ingest/work-orders", files={"file": ("bin.csv", b"\xff\xfe\x00bad", "text/csv")}
    )
    assert response.status_code == 422
    assert "UTF-8" in response.json()["detail"]
