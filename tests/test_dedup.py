"""Dedup tests: exact repeats collapse; conflicting content never resolves itself."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime

from insmart_api.ingestion.dedup import (
    DuplicateDetector,
    content_fingerprint,
    differing_fields,
    row_content,
    stored_content_from_payload,
)
from insmart_api.ingestion.parsing import WorkOrderRow


def _wo(work_order_id: str = "WO-1", **overrides: str) -> WorkOrderRow:
    """A fully valid parsed row, with per-field overrides."""
    fields = {
        "work_order_id": work_order_id,
        "created_at": "2025-01-15T08:30:00",
        "completed_at": "2025-01-15T11:45:00",
        "site": "Harborview",
        "asset_tag": "AHU-1",
        "summary": "No cooling",
        "technician": "J. Rivera",
        "notes": "Compressor draws high amps.",
        "resolution": "Replaced capacitor",
        "labor_hours": "2.5",
        "priority": "P2",
    }
    fields.update(overrides)
    return WorkOrderRow(
        row_number=1,
        work_order_id=work_order_id,
        created_at=datetime.fromisoformat(fields["created_at"]),
        completed_at=(
            datetime.fromisoformat(fields["completed_at"])
            if fields["completed_at"]
            else None
        ),
        asset_tag=fields["asset_tag"],
        labor_hours=float(fields["labor_hours"]),
        fields=fields,
    )


def test_first_row_is_accepted() -> None:
    assert DuplicateDetector().classify(_wo(), "AHU-1").status == "accepted"


def test_exact_repeat_is_collapsed() -> None:
    detector = DuplicateDetector()
    detector.classify(_wo(), "AHU-1")
    assert detector.classify(_wo(), "AHU-1").status == "collapsed"


def test_raw_tag_spelling_does_not_change_identity() -> None:
    # Entity resolution already picked the asset; 'ahu-1' vs 'AHU-1' in the
    # raw export is provenance, not a content conflict.
    detector = DuplicateDetector()
    detector.classify(_wo(), "AHU-1")
    variant = replace(_wo(), fields={**_wo().fields, "asset_tag": "ahu-1"})
    assert detector.classify(variant, "AHU-1").status == "collapsed"


def test_conflicting_content_lists_the_differing_fields() -> None:
    detector = DuplicateDetector()
    detector.classify(_wo(notes="Original notes."), "AHU-1")
    verdict = detector.classify(_wo(notes="Different notes."), "AHU-1")
    assert verdict.status == "conflict"
    assert verdict.differing_fields == ("notes",)


def test_conflicting_content_names_every_differing_field() -> None:
    detector = DuplicateDetector()
    detector.classify(_wo(summary="A", priority="P2"), "AHU-1")
    verdict = detector.classify(_wo(summary="B", priority="P1"), "AHU-1")
    assert verdict.status == "conflict"
    assert set(verdict.differing_fields) == {"summary", "priority"}


def test_differing_completion_time_is_a_conflict() -> None:
    # completed_at describes the work order itself — a changed value means
    # the records disagree, and only a human may resolve that.
    detector = DuplicateDetector()
    detector.classify(_wo(completed_at="2025-01-15T11:45:00"), "AHU-1")
    verdict = detector.classify(_wo(completed_at="2025-01-16T09:00:00"), "AHU-1")
    assert verdict.status == "conflict"
    assert verdict.differing_fields == ("completed_at",)


def test_differing_resolved_asset_is_a_conflict() -> None:
    detector = DuplicateDetector()
    detector.classify(_wo(), "AHU-1")
    verdict = detector.classify(_wo(), "RTU-3")
    assert verdict.status == "conflict"
    assert verdict.differing_fields == ("asset_id",)


def test_differing_fields_is_empty_for_identical_rows() -> None:
    assert differing_fields(row_content(_wo(), "AHU-1"), row_content(_wo(), "AHU-1")) == ()


def test_stored_observations_seed_cross_run_dedup() -> None:
    row = _wo()
    content = row_content(row, "AHU-1")
    detector = DuplicateDetector(
        stored_hashes={row.work_order_id: content_fingerprint(content)},
        stored_content={row.work_order_id: content},
    )
    assert detector.classify(row, "AHU-1").status == "collapsed"


def test_stored_conflicts_are_detected_across_runs() -> None:
    row = _wo(notes="Original notes.")
    content = row_content(row, "AHU-1")
    detector = DuplicateDetector(
        stored_hashes={row.work_order_id: content_fingerprint(content)},
        stored_content={row.work_order_id: content},
    )
    verdict = detector.classify(_wo(notes="Different notes."), "AHU-1")
    assert verdict.status == "conflict"


def test_stored_content_round_trips_through_the_payload() -> None:
    # The payload the pipeline persists: raw CSV cells with canonical typed
    # fields and provenance layered on top.
    row = _wo()
    payload = {
        **row.fields,
        "asset_id": "AHU-1",
        "recorded_at": row.created_at.isoformat(),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "labor_hours": row.labor_hours,
        "source_file": "corpus.csv",
        "source_row": 3,
    }
    assert stored_content_from_payload(json.dumps(payload)) == row_content(row, "AHU-1")
